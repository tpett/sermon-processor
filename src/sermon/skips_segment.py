from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.settles_recording import SettlesRecording
from sermon.store import LogEntry, Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class SkipsSegment:
    store: Store
    clock: object = now

    def __call__(self, segment, *, actor="reviewer"):
        occurred = self.clock()
        skipped = self.store.saves(replace(segment, state="skipped", disposition_at=occurred))
        self.store.saves(
            LogEntry(
                recording_id=skipped.recording_id,
                segment_id=skipped.segment_id,
                kind="state_change",
                occurred_at=occurred,
                correlation_id=f"skip:{skipped.segment_id}",
                actor=actor,
                entered_state="skipped",
                punch_in_seconds=skipped.punch_in_seconds,
                punch_out_seconds=skipped.punch_out_seconds,
                removed_spans=skipped.removed_spans,
            )
        )
        SettlesRecording(self.store, clock=self.clock)(skipped.recording_id)
        return skipped
