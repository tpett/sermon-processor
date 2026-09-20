from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.store import Job, LogEntry, Recording, Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class DiscardsRecording:
    store: Store
    clock: object = now

    def __call__(self, recording, *, reason=None, actor="reviewer"):
        occurred = self.clock()
        for job in self.store.lists(Job, recording_id=recording.recording_id):
            if job.state in {"queued", "running"}:
                self.store.saves(replace(job, state="cancelled"))
        discarded = self.store.saves(
            replace(recording, state="discarded", skip_reason=reason or recording.skip_reason)
        )
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="state_change",
                occurred_at=occurred,
                correlation_id=f"discard:{recording.recording_id}",
                actor=actor,
                entered_state="discarded",
                error=recording.state,
            )
        )
        return discarded


@dataclass(frozen=True)
class RestoresRecording:
    store: Store
    clock: object = now

    def __call__(self, recording):
        previous = "discovered"
        for entry in self.store.lists(LogEntry, recording_id=recording.recording_id):
            if entry.entered_state == "discarded" and entry.error:
                previous = entry.error
        restored = self.store.saves(replace(recording, state=previous, skip_reason=None))
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=f"restore:{recording.recording_id}",
                actor="reviewer",
                entered_state=previous,
            )
        )
        return restored
