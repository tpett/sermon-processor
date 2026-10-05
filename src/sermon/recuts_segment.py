from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.store import Artifact, LogEntry, Store

RECUT = "recut"


def now():
    return datetime.now(UTC)


class SegmentNotComplete(ValueError):
    def __init__(self):
        super().__init__("only a Segment that has finished rendering can be re-cut")


def current_renders(store, segment):
    return [
        item
        for item in store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
        if item.superseded_by is None
    ]


def holds_published_render(store, segment):
    if not current_renders(store, segment):
        return False
    return any(
        entry.entered_state == RECUT
        for entry in store.lists(LogEntry, segment_id=segment.segment_id)
    )


@dataclass(frozen=True)
class RecutsSegment:
    store: Store
    clock: object = now

    def __call__(self, segment, *, actor="reviewer"):
        if segment.state != "complete":
            raise SegmentNotComplete()
        recut = self.store.saves(replace(segment, state=RECUT, disposition_at=None))
        self.store.saves(
            LogEntry(
                recording_id=recut.recording_id,
                segment_id=recut.segment_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=f"recut:{recut.segment_id}",
                actor=actor,
                entered_state=RECUT,
                punch_in_seconds=recut.punch_in_seconds,
                punch_out_seconds=recut.punch_out_seconds,
                removed_spans=recut.removed_spans,
            )
        )
        return recut
