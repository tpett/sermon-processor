from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.adjusts_punch_point import EDITABLE_STATES, BoundaryRejected, lies_inside
from sermon.store import LogEntry, RemovedSpan, Store

SPAN_REMOVED = "span_removed"
SPAN_RESTORED = "span_restored"
SAME_INSTANT_SECONDS = 0.0005


def now():
    return datetime.now(UTC)


class RemovedSpanRejected(BoundaryRejected):
    pass


class RemovedSpanOutsideTheCut(RemovedSpanRejected):
    def __init__(self):
        super().__init__("a removed span must lie inside the punch-in and punch-out")


class RemovedSpanHasNoLength(RemovedSpanRejected):
    def __init__(self):
        super().__init__("a removed span must have a length")


class RemovedSpansOverlap(RemovedSpanRejected):
    def __init__(self):
        super().__init__("it overlaps a span already removed")


class RemovedSpansAreLocked(RemovedSpanRejected):
    def __init__(self):
        super().__init__("the removed spans cannot be changed once the Segment is approved")


class NoSuchRemovedSpan(RemovedSpanRejected):
    def __init__(self):
        super().__init__("no such span is removed from this Segment")


class RemovalStartNotMarked(RemovedSpanRejected):
    def __init__(self):
        super().__init__("mark where the removal starts first")


def kept_pieces(start_seconds, end_seconds, removed_spans):
    """What is left of start to end once every removed span is taken out, in order."""
    pieces = []
    reached = start_seconds
    for span in sorted(removed_spans, key=lambda one: one.start_seconds):
        if span.start_seconds >= end_seconds:
            break
        if span.start_seconds > reached:
            pieces.append((reached, span.start_seconds))
        reached = max(reached, span.end_seconds)
    if reached < end_seconds:
        pieces.append((reached, end_seconds))
    return tuple(pieces)


def removed_seconds(segment):
    return sum(span.end_seconds - span.start_seconds for span in segment.removed_spans)


def kept_seconds(segment):
    return segment.punch_out_seconds - segment.punch_in_seconds - removed_seconds(segment)


def records_span_change(store, occurred_at, segment, kind, actor, correlation_id):
    store.saves(
        LogEntry(
            recording_id=segment.recording_id,
            segment_id=segment.segment_id,
            kind=kind,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            actor=actor,
            punch_in_seconds=segment.punch_in_seconds,
            punch_out_seconds=segment.punch_out_seconds,
            removed_spans=segment.removed_spans,
        )
    )


def same_instant(one, other):
    return abs(one - other) < SAME_INSTANT_SECONDS


@dataclass(frozen=True)
class RemovesSpan:
    store: Store
    clock: object = now

    def __call__(self, segment, *, start_seconds, end_seconds, actor="reviewer"):
        if segment.state not in EDITABLE_STATES:
            raise RemovedSpansAreLocked()
        span = RemovedSpan(start_seconds=float(start_seconds), end_seconds=float(end_seconds))
        if span.end_seconds <= span.start_seconds:
            raise RemovedSpanHasNoLength()
        if not lies_inside(span, segment.punch_in_seconds, segment.punch_out_seconds):
            raise RemovedSpanOutsideTheCut()
        if any(
            span.start_seconds <= held.end_seconds and held.start_seconds <= span.end_seconds
            for held in segment.removed_spans
        ):
            raise RemovedSpansOverlap()
        removed = self.store.saves(
            replace(
                segment,
                removed_spans=tuple(
                    sorted((*segment.removed_spans, span), key=lambda one: one.start_seconds)
                ),
            )
        )
        records_span_change(
            self.store,
            self.clock(),
            removed,
            SPAN_REMOVED,
            actor,
            f"remove-span:{segment.segment_id}",
        )
        return removed


@dataclass(frozen=True)
class RestoresSpan:
    store: Store
    clock: object = now

    def __call__(self, segment, *, start_seconds, end_seconds, actor="reviewer"):
        if segment.state not in EDITABLE_STATES:
            raise RemovedSpansAreLocked()
        kept = tuple(
            span
            for span in segment.removed_spans
            if not (
                same_instant(span.start_seconds, float(start_seconds))
                and same_instant(span.end_seconds, float(end_seconds))
            )
        )
        if len(kept) == len(segment.removed_spans):
            raise NoSuchRemovedSpan()
        restored = self.store.saves(replace(segment, removed_spans=kept))
        records_span_change(
            self.store,
            self.clock(),
            restored,
            SPAN_RESTORED,
            actor,
            f"restore-span:{segment.segment_id}",
        )
        return restored
