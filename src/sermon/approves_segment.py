from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.store import Store


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
        return segment
