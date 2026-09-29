from __future__ import annotations

from dataclasses import dataclass, replace

from sermon.adjusts_punch_point import BoundaryOutsideSegment
from sermon.store import Segment, Store

PROPOSAL_MARGIN_SECONDS = 120.0
SPAN_EDGES = ("start", "end")
SPAN_STEPS = ("10 s", "1 min", "5 min")


class SpanWouldOverlapNeighbour(ValueError):
    def __init__(self):
        super().__init__("it would overlap the neighbouring Segment")


def overlaps(segment, neighbour):
    return (
        segment.span_start_seconds < neighbour.span_end_seconds
        and neighbour.span_start_seconds < segment.span_end_seconds
    )


def neighbours_of(store, segment):
    return tuple(
        other
        for other in store.lists(Segment, recording_id=segment.recording_id)
        if other.segment_id != segment.segment_id
    )


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
        if self._strands_a_punch_point(proposed):
            raise BoundaryOutsideSegment()
        if self._overlaps_a_neighbour(proposed):
            raise SpanWouldOverlapNeighbour()
        return self.store.saves(proposed)

    def _strands_a_punch_point(self, segment):
        return (
            segment.punch_in_seconds < segment.span_start_seconds
            or segment.punch_out_seconds > segment.span_end_seconds
        )

    def _overlaps_a_neighbour(self, segment):
        return any(
            overlaps(segment, neighbour) for neighbour in neighbours_of(self.store, segment)
        )


@dataclass(frozen=True)
class WidensProposedSpan:
    store: Store
    margin_seconds: float = PROPOSAL_MARGIN_SECONDS

    def __call__(self, segment, duration_seconds=None):
        neighbours = neighbours_of(self.store, segment)
        before = [
            one.span_end_seconds
            for one in neighbours
            if one.span_end_seconds <= segment.punch_in_seconds
        ]
        after = [
            one.span_start_seconds
            for one in neighbours
            if one.span_start_seconds >= segment.punch_out_seconds
        ]
        if duration_seconds:
            after.append(duration_seconds)
        roomy = replace(
            segment,
            span_start_seconds=max(
                [0.0, segment.punch_in_seconds - self.margin_seconds] + before
            ),
            span_end_seconds=min([segment.punch_out_seconds + self.margin_seconds] + after),
        )
        if any(overlaps(roomy, one) for one in neighbours):
            return segment
        return roomy
