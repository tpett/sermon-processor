from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.recuts_segment import holds_published_render
from sermon.settles_recording import SettlesRecording
from sermon.store import Job, LogEntry, Store
from sermon.store.vocabularies import JOB_STATES_IN_FLIGHT

REOPENABLE_STATES = frozenset({"skipped", "approved", "processing", "recut"})


def now():
    return datetime.now(UTC)


class SegmentAlreadyRendered(ValueError):
    def __init__(self):
        super().__init__("a Segment that has already rendered cannot be reopened")


@dataclass(frozen=True)
class ReopensSegment:
    store: Store
    clock: object = now

    def __call__(self, segment, *, actor="reviewer"):
        if segment.state not in REOPENABLE_STATES:
            raise SegmentAlreadyRendered()
        occurred = self.clock()
        for job in self.store.lists(Job, segment_id=segment.segment_id):
            if job.state in JOB_STATES_IN_FLIGHT:
                self.store.saves(replace(job, state="cancelled"))
        returns_to = "recut" if holds_published_render(self.store, segment) else "proposed"
        reopened = self.store.saves(replace(segment, state=returns_to, disposition_at=None))
        self.store.saves(
            LogEntry(
                recording_id=reopened.recording_id,
                segment_id=reopened.segment_id,
                kind="state_change",
                occurred_at=occurred,
                correlation_id=f"reopen:{reopened.segment_id}",
                actor=actor,
                entered_state=returns_to,
                punch_in_seconds=reopened.punch_in_seconds,
                punch_out_seconds=reopened.punch_out_seconds,
                removed_spans=reopened.removed_spans,
            )
        )
        SettlesRecording(self.store, clock=self.clock)(reopened.recording_id)
        return reopened
