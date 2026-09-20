from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.store import LogEntry, Recording, Segment, Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class SettlesRecording:
    store: Store
    clock: object = now

    def __call__(self, recording_id):
        remaining = [
            segment
            for segment in self.store.lists(Segment, recording_id=recording_id)
            if segment.state == "proposed"
        ]
        if remaining:
            return self.store.loads(Recording, recording_id)
        recording = self.store.loads(Recording, recording_id)
        reviewed = self.store.saves(replace(recording, state="reviewed"))
        self.store.saves(
            LogEntry(
                recording_id=recording_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=f"settle:{recording_id}",
                entered_state="reviewed",
            )
        )
        return reviewed
