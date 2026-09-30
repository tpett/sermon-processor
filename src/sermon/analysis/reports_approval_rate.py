from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sermon.adjusts_punch_point import MACHINE_SOURCES, reads_boundary_history
from sermon.store import Segment, Store

FOR_PUBLICATION = "publish"
PUBLISHED_STATES = frozenset({"approved", "processing", "complete"})
REVIEWER_MOVED = "human"


@dataclass(frozen=True)
class PublishedCut:
    recording_id: str
    segment_id: int
    classification: str
    published_on: date
    boundary_source: str | None
    punch_in_error_seconds: float | None = None
    punch_out_error_seconds: float | None = None

    @property
    def edited(self) -> bool:
        return self.boundary_source == REVIEWER_MOVED


@dataclass(frozen=True)
class ApprovalRate:
    since: date | None
    until: date | None
    cuts: tuple[PublishedCut, ...]

    @property
    def published(self) -> int:
        return len(self.cuts)

    @property
    def approved_with_no_edit(self) -> tuple[PublishedCut, ...]:
        return tuple(cut for cut in self.cuts if not cut.edited)

    @property
    def proportion(self) -> float | None:
        if not self.cuts:
            return None
        return len(self.approved_with_no_edit) / len(self.cuts)


@dataclass(frozen=True)
class ReportsApprovalRate:
    store: Store

    def __call__(self, since=None, until=None):
        return ApprovalRate(
            since=since,
            until=until,
            cuts=tuple(
                sorted(
                    (
                        self.reads(segment)
                        for segment in self.store.lists(Segment)
                        if self.published_between(segment, since, until)
                    ),
                    key=lambda cut: (cut.published_on, cut.segment_id),
                )
            ),
        )

    def published_between(self, segment, since, until):
        if segment.intent != FOR_PUBLICATION or segment.state not in PUBLISHED_STATES:
            return False
        if segment.publication_date is None:
            return False
        if since is not None and segment.publication_date < since:
            return False
        return until is None or segment.publication_date <= until

    def reads(self, segment):
        proposed = self.proposed_boundaries(segment) or (None, None)
        return PublishedCut(
            recording_id=segment.recording_id,
            segment_id=segment.segment_id,
            classification=segment.classification,
            published_on=segment.publication_date,
            boundary_source=segment.boundary_source,
            punch_in_error_seconds=measures_error(proposed[0], segment.punch_in_seconds),
            punch_out_error_seconds=measures_error(proposed[1], segment.punch_out_seconds),
        )

    def proposed_boundaries(self, segment):
        if segment.boundary_source != REVIEWER_MOVED:
            return None
        machine = [
            entry
            for entry in reads_boundary_history(self.store, segment.segment_id)
            if entry.boundary_source in MACHINE_SOURCES
        ]
        if not machine:
            return None
        return (machine[0].punch_in_seconds, machine[0].punch_out_seconds)


def measures_error(proposed, chosen):
    if proposed is None:
        return None
    return round(proposed - chosen, 3)
