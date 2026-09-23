from __future__ import annotations

from dataclasses import dataclass, replace

from sermon.adjusts_punch_point import MINIMUM_SPAN_SECONDS, SelectionTooShort
from sermon.store import Segment, Store


class SplitPointOutsideSegment(ValueError):
    def __init__(self):
        super().__init__("the split point must fall within the Segment")


class NothingToMerge(ValueError):
    def __init__(self):
        super().__init__("two adjacent Segments are needed to merge")


@dataclass(frozen=True)
class SplitsSegment:
    store: Store

    def __call__(self, segment, *, at_seconds):
        at = float(at_seconds)
        if not segment.punch_in_seconds < at < segment.punch_out_seconds:
            raise SplitPointOutsideSegment()
        if min(at - segment.punch_in_seconds, segment.punch_out_seconds - at) < MINIMUM_SPAN_SECONDS:
            raise SelectionTooShort()
        earlier = self.store.saves(
            replace(segment, span_end_seconds=at, punch_out_seconds=at)
        )
        later = self.store.saves(
            replace(
                segment,
                segment_id=None,
                span_start_seconds=at,
                punch_in_seconds=at,
                state="proposed",
                disposition_at=None,
                label=None,
                boundary_source="human",
            )
        )
        return (earlier, later)


@dataclass(frozen=True)
class MergesSegments:
    store: Store

    def __call__(self, earlier, later):
        if earlier.segment_id == later.segment_id:
            raise NothingToMerge()
        first, second = sorted((earlier, later), key=lambda one: one.punch_in_seconds)
        merged = self.store.saves(
            replace(
                first,
                span_start_seconds=min(first.span_start_seconds, second.span_start_seconds),
                span_end_seconds=max(first.span_end_seconds, second.span_end_seconds),
                punch_in_seconds=first.punch_in_seconds,
                punch_out_seconds=second.punch_out_seconds,
                boundary_source="human",
            )
        )
        self.store.saves(replace(second, state="recut", disposition_at=None))
        return merged


@dataclass(frozen=True)
class CreatesSegment:
    store: Store

    def __call__(self, recording, *, from_seconds, to_seconds, classification="sermon"):
        start = float(from_seconds)
        end = float(to_seconds)
        if end - start < MINIMUM_SPAN_SECONDS:
            raise SelectionTooShort()
        return self.store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification=classification,
                state="proposed",
                span_start_seconds=start,
                span_end_seconds=end,
                punch_in_seconds=start,
                punch_out_seconds=end,
                boundary_source="human",
            )
        )
