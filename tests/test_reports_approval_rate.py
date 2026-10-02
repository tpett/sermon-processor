from datetime import UTC, date, datetime

import pytest

from sermon.adjusts_punch_point import AdjustsPunchPoint
from sermon.analysis.reports_approval_rate import ReportsApprovalRate
from sermon.approves_segment import ApprovesSegment
from sermon.store import Recording, Segment, opens_store

FROZEN = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
SUNDAY = date(2026, 9, 27)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(data_root=tmp_path)
    yield opened
    opened.close()


def recording(store, recording_id):
    return store.saves(
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


def proposed(store, recording_id, published_on=SUNDAY, **fields):
    recording(store, recording_id)
    return store.saves(
        Segment(
            recording_id=recording_id,
            classification=fields.pop("classification", "sermon"),
            state="proposed",
            intent=fields.pop("intent", "publish"),
            label=fields.pop("label", "Hebrews 13.7-8"),
            publication_date=published_on,
            span_start_seconds=3000.0,
            span_end_seconds=5600.0,
            punch_in_seconds=fields.pop("punch_in_seconds", 3060.0),
            punch_out_seconds=fields.pop("punch_out_seconds", 5594.5),
            boundary_source=fields.pop("boundary_source", "model"),
            **fields,
        )
    )


def approves(store, segment):
    return ApprovesSegment(store=store, clock=lambda: FROZEN)(segment)


def adjusted(store, recording_id, published_on=SUNDAY, punch_in=3055.0, punch_out=5597.3):
    segment = proposed(store, recording_id, published_on)
    moved = AdjustsPunchPoint(store=store, clock=lambda: FROZEN)(
        segment, punch_in_seconds=punch_in, punch_out_seconds=punch_out
    )
    return approves(store, moved)


def test_the_headline_measure_is_the_fraction_published_with_no_boundary_edit(store):
    approves(store, proposed(store, "recording_20260906_100000", date(2026, 9, 6)))
    approves(store, proposed(store, "recording_20260913_100000", date(2026, 9, 13)))
    adjusted(store, "recording_20260927_095721")
    rate = ReportsApprovalRate(store=store)()
    assert [cut.published_on for cut in rate.cuts] == [
        date(2026, 9, 6),
        date(2026, 9, 13),
        date(2026, 9, 27),
    ]
    assert rate.published == 3
    assert len(rate.approved_with_no_edit) == 2
    assert rate.proportion == pytest.approx(2 / 3)


def test_only_what_was_published_inside_the_period_is_counted(store):
    approves(store, proposed(store, "recording_20260830_100000", date(2026, 8, 30)))
    adjusted(store, "recording_20260927_095721", date(2026, 9, 27))
    rate = ReportsApprovalRate(store=store)(
        since=date(2026, 9, 1), until=date(2026, 9, 30)
    )
    assert [cut.recording_id for cut in rate.cuts] == ["recording_20260927_095721"]
    assert rate.proportion == 0.0


def test_a_period_in_which_nothing_was_published_has_no_proportion(store):
    approves(store, proposed(store, "recording_20260830_100000", date(2026, 8, 30)))
    rate = ReportsApprovalRate(store=store)(
        since=date(2026, 9, 1), until=date(2026, 9, 30)
    )
    assert rate.published == 0
    assert rate.proportion is None


def test_a_segment_archived_rather_than_published_is_not_in_the_population(store):
    approves(
        store,
        proposed(
            store,
            "recording_20260628_130014",
            classification="meeting",
            intent="archive",
            label=None,
        ),
    )
    assert ReportsApprovalRate(store=store)().published == 0


def test_a_segment_nobody_has_dispositioned_is_not_a_publication(store):
    proposed(store, "recording_20260927_095721")
    assert ReportsApprovalRate(store=store)().published == 0


def test_the_signed_error_of_the_machines_cut_is_reported_beside_the_proportion(store):
    adjusted(store, "recording_20260927_095721", punch_in=3055.0, punch_out=5597.3)
    rate = ReportsApprovalRate(store=store)()
    assert rate.proportion == 0.0
    assert [cut.punch_in_error_seconds for cut in rate.cuts] == [pytest.approx(5.0)]
    assert [cut.punch_out_error_seconds for cut in rate.cuts] == [pytest.approx(-2.8)]


def test_an_untouched_cut_carries_no_error_figures_because_there_is_no_human_answer(store):
    approves(store, proposed(store, "recording_20260906_100000"))
    rate = ReportsApprovalRate(store=store)()
    assert rate.published == 1
    assert [cut.edited for cut in rate.cuts] == [False]
    assert [
        (cut.punch_in_error_seconds, cut.punch_out_error_seconds) for cut in rate.cuts
    ] == [(None, None)]


def test_a_published_segment_carrying_no_publication_date_falls_in_no_period(store):
    approves(store, proposed(store, "recording_20260920_094416", None))
    approves(store, proposed(store, "recording_20260913_090014", SUNDAY))
    rate = ReportsApprovalRate(store=store)()
    assert rate.published == 1
    assert rate.unplaced == 1
    assert rate.proportion == 1.0


def test_a_period_holding_only_unplaced_publications_still_has_no_proportion(store):
    approves(store, proposed(store, "recording_20260920_094416", None))
    rate = ReportsApprovalRate(store=store)()
    assert (rate.published, rate.unplaced) == (0, 1)
    assert rate.proportion is None


def test_a_segment_nobody_published_is_not_counted_as_unplaced(store):
    proposed(store, "recording_20260927_095721", None)
    assert ReportsApprovalRate(store=store)().unplaced == 0
