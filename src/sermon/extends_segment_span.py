from __future__ import annotations

from dataclasses import dataclass, replace

from sermon.store import Store


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
        return self.store.saves(
            replace(
                segment,
                span_start_seconds=(
                    segment.span_start_seconds if start_seconds is None else start_seconds
                ),
                span_end_seconds=segment.span_end_seconds if end_seconds is None else end_seconds,
            )
        )
