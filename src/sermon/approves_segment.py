from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.store import Job, Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class ReviewSession:
    waveform_editor_opened: bool = False

    def previews_punch_in(self, segment):
        return segment

    def previews_punch_out(self, segment):
        return segment


@dataclass(frozen=True)
class ApprovesSegment:
    store: Store
    clock: object = now

    def __call__(self, segment):
        approved = self.store.saves(replace(segment, state="approved", disposition_at=self.clock()))
        self.store.saves(
            Job(
                recording_id=approved.recording_id,
                segment_id=approved.segment_id,
                kind="render",
                state="queued",
                max_attempts=5,
                dedupe_key=f"render:{approved.segment_id}",
                queued_at=self.clock(),
            )
        )
        return approved
