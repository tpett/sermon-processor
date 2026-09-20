from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.settles_recording import SettlesRecording
from sermon.store import Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class SkipsSegment:
    store: Store
    clock: object = now

    def __call__(self, segment):
        skipped = self.store.saves(
            replace(segment, state="skipped", disposition_at=self.clock())
        )
        SettlesRecording(self.store, clock=self.clock)(skipped.recording_id)
        return skipped
