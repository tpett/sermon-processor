from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.store import LogEntry, Store

MINIMUM_SPAN_SECONDS = 1.0
EXPECTED_SPAN_SECONDS = (1800.0, 4500.0)
QUIET_MARGIN_SECONDS = 0.25
NUDGE_STEPS = ("50 ms", "0.1 s", "1 s", "10 s")
NUDGE_UNITS = {"ms": 0.001, "s": 1.0}
EDITABLE_STATES = frozenset({"proposed", "skipped", "recut"})
MACHINE_SOURCES = frozenset({"model", "refined", "model-in/refined-out"})
BOUNDARY_CHANGE = "boundary_change"


def now():
    return datetime.now(UTC)


class BoundaryRejected(ValueError):
    pass


class PunchOutBeforePunchIn(BoundaryRejected):
    def __init__(self):
        super().__init__("the punch-out must be after the punch-in")


class BoundaryOutsideSegment(BoundaryRejected):
    def __init__(self):
        super().__init__("the boundary must fall within the Segment")


class SelectionTooShort(BoundaryRejected):
    def __init__(self):
        super().__init__("the selection is too short")


class BoundariesAreLocked(BoundaryRejected):
    def __init__(self):
        super().__init__("the boundaries cannot be changed once the Segment is approved")


class NoProposalToRevertTo(BoundaryRejected):
    def __init__(self):
        super().__init__("no machine proposal is recorded for this Segment")


def reads_nudge_amount(text):
    number, unit = str(text).split()
    return float(number) * NUDGE_UNITS[unit]


def warns_about_length(punch_in_seconds, punch_out_seconds):
    shortest, longest = EXPECTED_SPAN_SECONDS
    length = punch_out_seconds - punch_in_seconds
    if shortest <= length <= longest:
        return None
    return "the length is outside the expected range"


def records_boundary_change(
    store, occurred_at, segment, punch_in, punch_out, source, actor, correlation_id
):
    store.saves(
        LogEntry(
            recording_id=segment.recording_id,
            segment_id=segment.segment_id,
            kind=BOUNDARY_CHANGE,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            actor=actor,
            punch_in_seconds=punch_in,
            punch_out_seconds=punch_out,
            boundary_source=source,
        )
    )


def reads_boundary_history(store, segment_id):
    return [
        entry
        for entry in store.lists(LogEntry, segment_id=segment_id)
        if entry.kind == BOUNDARY_CHANGE
    ]


@dataclass(frozen=True)
class AdjustsPunchPoint:
    store: Store
    clock: object = now

    def __call__(
        self,
        segment,
        *,
        punch_in_seconds=None,
        punch_out_seconds=None,
        actor="reviewer",
    ):
        if segment.state not in EDITABLE_STATES:
            raise BoundariesAreLocked()
        punch_in = self._resolved(segment.punch_in_seconds, punch_in_seconds)
        punch_out = self._resolved(segment.punch_out_seconds, punch_out_seconds)
        if punch_in < segment.span_start_seconds or punch_out > segment.span_end_seconds:
            raise BoundaryOutsideSegment()
        if punch_out <= punch_in:
            raise PunchOutBeforePunchIn()
        if punch_out - punch_in < MINIMUM_SPAN_SECONDS:
            raise SelectionTooShort()
        self._remembers_the_proposal(segment)
        adjusted = self.store.saves(
            replace(
                segment,
                punch_in_seconds=punch_in,
                punch_out_seconds=punch_out,
                boundary_source="human",
            )
        )
        records_boundary_change(
            self.store,
            self.clock(),
            adjusted,
            punch_in,
            punch_out,
            "human",
            actor,
            f"adjust:{segment.segment_id}",
        )
        return adjusted

    def _resolved(self, held, offered):
        return held if offered is None else float(offered)

    def _remembers_the_proposal(self, segment):
        if reads_boundary_history(self.store, segment.segment_id):
            return
        source = segment.boundary_source if segment.boundary_source in MACHINE_SOURCES else "model"
        records_boundary_change(
            self.store,
            self.clock(),
            segment,
            segment.punch_in_seconds,
            segment.punch_out_seconds,
            source,
            "analysis",
            f"propose:{segment.segment_id}",
        )


@dataclass(frozen=True)
class RevertsToProposal:
    store: Store
    clock: object = now

    def __call__(self, segment, *, actor="reviewer"):
        if segment.state not in EDITABLE_STATES:
            raise BoundariesAreLocked()
        proposed = [
            entry
            for entry in reads_boundary_history(self.store, segment.segment_id)
            if entry.boundary_source in MACHINE_SOURCES
        ]
        if not proposed:
            raise NoProposalToRevertTo()
        machine = proposed[0]
        records_boundary_change(
            self.store,
            self.clock(),
            segment,
            segment.punch_in_seconds,
            segment.punch_out_seconds,
            "human",
            actor,
            f"revert:{segment.segment_id}",
        )
        return self.store.saves(
            replace(
                segment,
                punch_in_seconds=machine.punch_in_seconds,
                punch_out_seconds=machine.punch_out_seconds,
                boundary_source=machine.boundary_source,
            )
        )
