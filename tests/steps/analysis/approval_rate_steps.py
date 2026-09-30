from datetime import UTC, date, datetime

import pytest
from pytest_bdd import then

from sermon.adjusts_punch_point import AdjustsPunchPoint
from sermon.analysis.reports_approval_rate import ReportsApprovalRate
from sermon.approves_segment import ApprovesSegment
from sermon.store import CorpusPair, Recording, Segment

SINCE = date(2026, 9, 1)
UNTIL = date(2026, 9, 30)
FROZEN = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
MACHINE_CUT = (3060.0, 5594.5)
REVIEWER_CUT = (3055.0, 5597.3)


def reports(store):
    return ReportsApprovalRate(store=store)(SINCE, UNTIL)


def proposes(store, recording_id, published_on):
    store.saves(
        Recording(
            recording_id=recording_id,
            object_key=f"recordings/{recording_id}.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 27, 9, 57, 21, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=6791.608,
        )
    )
    return store.saves(
        Segment(
            recording_id=recording_id,
            classification="sermon",
            state="proposed",
            intent="publish",
            label="Hebrews 13.7-8",
            publication_date=published_on,
            span_start_seconds=3000.0,
            span_end_seconds=5600.0,
            punch_in_seconds=MACHINE_CUT[0],
            punch_out_seconds=MACHINE_CUT[1],
            boundary_source="model",
        )
    )


def approves(store, segment):
    return ApprovesSegment(store=store, clock=lambda: FROZEN)(segment)


def publishes_one_untouched_and_one_edited(store):
    approves(store, proposes(store, "recording_20260906_100000", date(2026, 9, 6)))
    moved = AdjustsPunchPoint(store=store, clock=lambda: FROZEN)(
        proposes(store, "recording_20260927_095721", date(2026, 9, 27)),
        punch_in_seconds=REVIEWER_CUT[0],
        punch_out_seconds=REVIEWER_CUT[1],
    )
    approves(store, moved)


def published_period(store):
    if not reports(store).cuts:
        publishes_one_untouched_and_one_edited(store)
    return reports(store)


def dispositioned(store):
    return [segment for segment in store.lists(Segment) if segment.state == "approved"]


@then("it counts toward the proportion approved with no edit")
def _(store):
    rate = ReportsApprovalRate(store=store)()
    assert [cut.segment_id for cut in rate.cuts] == [
        segment.segment_id for segment in dispositioned(store)
    ]
    assert rate.approved_with_no_edit == rate.cuts
    assert rate.proportion == 1.0


@then("it does not become a labelled example")
def _(store):
    approved = [
        (segment.punch_in_seconds, segment.punch_out_seconds)
        for segment in dispositioned(store)
    ]
    labelled = [
        (pair.punch_in_seconds, pair.punch_out_seconds)
        for pair in store.lists(CorpusPair)
        if pair.labelled
    ]
    assert approved
    assert not set(approved) & set(labelled)


@then(
    "the headline measure is the proportion of Segments published in a period "
    "that were approved with no boundary edit"
)
def _(store):
    rate = published_period(store)
    assert (rate.since, rate.until) == (SINCE, UNTIL)
    assert rate.published == 2
    assert [cut.edited for cut in rate.cuts] == [False, True]
    assert rate.proportion == 0.5


@then("it is reported alongside the raw error figures, not replaced by them")
def _(store):
    rate = published_period(store)
    assert rate.proportion == 0.5
    assert [
        (cut.punch_in_error_seconds, cut.punch_out_error_seconds) for cut in rate.cuts
    ] == [
        (None, None),
        (
            pytest.approx(MACHINE_CUT[0] - REVIEWER_CUT[0]),
            pytest.approx(MACHINE_CUT[1] - REVIEWER_CUT[1]),
        ),
    ]
