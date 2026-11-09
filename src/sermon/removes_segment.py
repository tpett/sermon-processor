from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.settles_recording import SettlesRecording
from sermon.store import Artifact, Job, LogEntry, Notification, Proposal, Store

REMOVABLE = frozenset({"proposed", "skipped", "recut", "processing_failed"})
PUBLISHED = "a published segment cannot be removed"
IN_FLIGHT = "a segment that is rendering cannot be removed"


def now():
    return datetime.now(UTC)


class SegmentCannotBeRemoved(ValueError):
    pass


@dataclass(frozen=True)
class RemovesSegment:
    """Drop a segment that was never published. The source file is untouched."""

    store: Store
    clock: object = now

    def __call__(self, segment, *, actor="reviewer"):
        if self.store.lists(Artifact, segment_id=segment.segment_id):
            raise SegmentCannotBeRemoved(PUBLISHED)
        if segment.state not in REMOVABLE:
            raise SegmentCannotBeRemoved(IN_FLIGHT)
        occurred = self.clock()
        recording_id = segment.recording_id
        identity = segment.segment_id
        for entry in self.store.lists(LogEntry, segment_id=identity):
            self.store.saves(replace(entry, segment_id=None))
        for proposal in self.store.lists(Proposal, segment_id=identity):
            self.store.forgets(proposal)
        for job in self.store.lists(Job, segment_id=identity):
            self.store.forgets(job)
        for notice in self.store.lists(Notification, segment_id=identity):
            self.store.forgets(notice)
        self.store.forgets(segment)
        self.store.saves(
            LogEntry(
                recording_id=recording_id,
                kind="segment_removed",
                occurred_at=occurred,
                correlation_id=f"remove:{identity}",
                actor=actor,
                punch_in_seconds=segment.punch_in_seconds,
                punch_out_seconds=segment.punch_out_seconds,
            )
        )
        SettlesRecording(self.store, clock=self.clock)(recording_id)
        return identity
