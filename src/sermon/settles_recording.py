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
        recording = self.store.loads(Recording, recording_id)
        if remaining:
            if recording.state != "reviewed":
                return recording
            return self._enters(recording, "awaiting_review")
        return self._enters(recording, "reviewed")

    def _enters(self, recording, state):
        entered = self.store.saves(replace(recording, state=state))
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=f"settle:{recording.recording_id}",
                entered_state=state,
            )
        )
        return entered
