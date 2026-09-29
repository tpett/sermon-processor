from __future__ import annotations

from dataclasses import dataclass, replace

from sermon.store import Segment, Store

SPAN_EDGES = ("start", "end")
SPAN_STEPS = ("10 s", "1 min", "5 min")


class SpanWouldOverlapNeighbour(ValueError):
    def __init__(self):
        super().__init__("it would overlap the neighbouring Segment")


@dataclass(frozen=True)
class ReadsTimecode:
    def __call__(self, text):
        hours, minutes, seconds = text.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


@dataclass(frozen=True)
class ExtendsSegmentSpan:
    store: Store

    def __call__(self, segment, *, start_seconds=None, end_seconds=None):
        proposed = replace(
            segment,
            span_start_seconds=(
                segment.span_start_seconds if start_seconds is None else start_seconds
            ),
            span_end_seconds=segment.span_end_seconds if end_seconds is None else end_seconds,
        )
        if self._overlaps_a_neighbour(proposed):
            raise SpanWouldOverlapNeighbour()
        return self.store.saves(proposed)

    def _overlaps_a_neighbour(self, segment):
        return any(
            neighbour.segment_id != segment.segment_id
            and segment.span_start_seconds < neighbour.span_end_seconds
            and neighbour.span_start_seconds < segment.span_end_seconds
            for neighbour in self.store.lists(Segment, recording_id=segment.recording_id)
        )
