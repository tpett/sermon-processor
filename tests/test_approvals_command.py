from datetime import UTC, date, datetime

from sermon.adjusts_punch_point import AdjustsPunchPoint
from sermon.approves_segment import ApprovesSegment
from sermon.cli import reports_approvals
from sermon.config import DATA_ROOT
from sermon.store import Recording, Segment, opens_store

FROZEN = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
MACHINE_CUT = (3060.0, 5594.5)
REVIEWER_CUT = (3055.0, 5597.3)


def settings(root):
    return {DATA_ROOT: str(root / "data")}


def store_for(root):
    return opens_store(data_root=root / "data")


def proposed(store, recording_id, published_on, **fields):
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
            **fields,
        )
    )


def publishes_untouched(store, recording_id, published_on):
    ApprovesSegment(store=store, clock=lambda: FROZEN)(
        proposed(store, recording_id, published_on)
    )


def publishes_edited(store, recording_id, published_on):
    moved = AdjustsPunchPoint(store=store, clock=lambda: FROZEN)(
        proposed(store, recording_id, published_on),
        punch_in_seconds=REVIEWER_CUT[0],
        punch_out_seconds=REVIEWER_CUT[1],
    )
    ApprovesSegment(store=store, clock=lambda: FROZEN)(moved)


def runs(root, *flags):
    collected = []
    code = reports_approvals(
        settings=settings(root), arguments=list(flags), prints=collected.append
    )
    return code, "\n".join(collected)


def test_the_command_reports_the_proportion_approved_with_no_boundary_edit(tmp_path):
    store = store_for(tmp_path)
    publishes_untouched(store, "recording_20260906_100000", date(2026, 9, 6))
    publishes_untouched(store, "recording_20260913_090014", date(2026, 9, 13))
    publishes_edited(store, "recording_20260927_095721", date(2026, 9, 27))
    store.close()
    code, printed = runs(tmp_path)
    assert code == 0
    assert "3 Segments published, 2 approved with no boundary edit: 67%" in printed


def test_the_period_defaults_to_all_time_and_the_output_names_it(tmp_path):
    store = store_for(tmp_path)
    publishes_untouched(store, "recording_20260412_102318", date(2026, 4, 12))
    store.close()
    code, printed = runs(tmp_path)
    assert code == 0
    assert "all time" in printed
    assert "1 Segment published, 1 approved with no boundary edit: 100%" in printed


def test_since_and_until_narrow_the_period_and_the_output_names_the_dates(tmp_path):
    store = store_for(tmp_path)
    publishes_untouched(store, "recording_20260830_102838", date(2026, 8, 30))
    publishes_edited(store, "recording_20260927_095721", date(2026, 9, 27))
    store.close()
    code, printed = runs(tmp_path, "--since", "2026-09-01", "--until", "2026-09-30")
    assert code == 0
    assert "2026-09-01 to 2026-09-30" in printed
    assert "recording_20260830_102838" not in printed
    assert "1 Segment published, 0 approved with no boundary edit: 0%" in printed


def test_an_edited_cut_carries_the_signed_error_of_what_the_machine_proposed(tmp_path):
    store = store_for(tmp_path)
    publishes_edited(store, "recording_20260927_095721", date(2026, 9, 27))
    store.close()
    code, printed = runs(tmp_path)
    assert code == 0
    assert "recording_20260927_095721  sermon   2026-09-27  edited" in printed
    assert "punch-in   error   +5.000 s" in printed
    assert "punch-out  error   -2.800 s" in printed


def test_an_untouched_cut_reports_no_error_figure_rather_than_zero(tmp_path):
    store = store_for(tmp_path)
    publishes_untouched(store, "recording_20260906_100000", date(2026, 9, 6))
    store.close()
    code, printed = runs(tmp_path)
    assert code == 0
    assert "recording_20260906_100000  sermon   2026-09-06  unedited" in printed
    assert "no error figure" in printed
    assert "0.000" not in printed


def test_a_period_in_which_nothing_was_published_reports_no_rate_and_exits_non_zero(tmp_path):
    store = store_for(tmp_path)
    publishes_untouched(store, "recording_20260830_102838", date(2026, 8, 30))
    store.close()
    code, printed = runs(tmp_path, "--since", "2026-09-01")
    assert code == 1
    assert "nothing was published in that period, so there is no rate to report" in printed
    assert "0%" not in printed


def test_a_published_segment_carrying_no_publication_date_is_counted_as_unplaced(tmp_path):
    store = store_for(tmp_path)
    publishes_untouched(store, "recording_20260920_094416", None)
    store.close()
    code, printed = runs(tmp_path)
    assert code == 1
    assert "1 published Segment carries no publication date and is in no period" in printed


def test_the_store_flag_reads_a_data_root_other_than_the_configured_one(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    store = opens_store(data_root=elsewhere)
    publishes_untouched(store, "recording_20260906_100000", date(2026, 9, 6))
    store.close()
    code, printed = runs(tmp_path, "--store", str(elsewhere))
    assert code == 0
    assert str(elsewhere) in printed
    assert "1 Segment published" in printed


def test_a_period_that_is_not_a_date_prints_the_usage(tmp_path):
    code, printed = runs(tmp_path, "--since", "last-sunday")
    assert code == 1
    assert "usage: sermon-approvals" in printed


def test_nothing_sets_the_data_root(tmp_path):
    collected = []
    code = reports_approvals(settings={}, arguments=[], prints=collected.append)
    assert code == 1
    assert "nothing sets SERMON_DATA_ROOT" in "\n".join(collected)
