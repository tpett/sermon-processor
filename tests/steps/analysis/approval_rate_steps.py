from datetime import UTC, date, datetime

from pytest_bdd import given, then, when

from sermon.adjusts_punch_point import AdjustsPunchPoint
from sermon.approves_segment import ApprovesSegment
from sermon.cli import reports_approvals
from sermon.config import DATA_ROOT
from sermon.store import CorpusPair, Recording, Segment

SINCE = date(2026, 9, 1)
UNTIL = date(2026, 9, 30)
FROZEN = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
MACHINE_CUT = (3060.0, 5594.5)
REVIEWER_CUT = (3055.0, 5597.3)


def surfaces(tmp_path, *period):
    collected = []
    reports_approvals(
        settings={DATA_ROOT: str(tmp_path)}, arguments=list(period), prints=collected.append
    )
    return "\n".join(collected)


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


def dispositioned(store):
    return [segment for segment in store.lists(Segment) if segment.state == "approved"]


@then("it counts toward the proportion approved with no edit")
def _(store, tmp_path):
    printed = surfaces(tmp_path)
    assert [segment.recording_id for segment in dispositioned(store)]
    for segment in dispositioned(store):
        assert f"{segment.recording_id}  {segment.classification:<8}" in printed
    assert "unedited" in printed
    assert "1 Segment published, 1 approved with no boundary edit: 100%" in printed


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


@given("a period in which one Segment was published untouched and one after a boundary edit")
def _(store):
    publishes_one_untouched_and_one_edited(store)


@when("the approval rate is reported for that period", target_fixture="printed")
def _(tmp_path):
    return surfaces(tmp_path, "--since", SINCE.isoformat(), "--until", UNTIL.isoformat())


@then(
    "the headline measure is the proportion of a period's published Segments "
    "approved with no boundary edit"
)
def _(printed):
    assert f"{SINCE.isoformat()} to {UNTIL.isoformat()}" in printed
    assert "2 Segments published, 1 approved with no boundary edit: 50%" in printed


@then("it is reported alongside the raw error figures, not replaced by them")
def _(printed):
    assert "2 Segments published, 1 approved with no boundary edit: 50%" in printed
    assert "punch-in   error   +5.000 s" in printed
    assert "punch-out  error   -2.800 s" in printed
    assert "no error figure" in printed
