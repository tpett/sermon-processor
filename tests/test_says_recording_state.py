import pytest

from dataclasses import replace
from datetime import UTC, datetime

from sermon.lists_recordings import ListsRecordings, says_state, says_state_alone
from sermon.store import Recording, Segment, opens_store


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def segment(state, intent=None):
    return Segment(
        recording_id="recording_20260913_090014",
        classification="sermon",
        state=state,
        intent=intent,
        span_start_seconds=0.0,
        span_end_seconds=10.0,
        punch_in_seconds=0.0,
        punch_out_seconds=10.0,
    )


@pytest.mark.parametrize(
    ("states", "label", "tone"),
    [
        (["complete"], "Published", "muted"),
        (["complete", "skipped"], "Published", "muted"),
        (["approved"], "Approved, waiting to render", "accent"),
        (["processing"], "Rendering", "accent"),
        (["approved", "skipped"], "Approved, waiting to render", "accent"),
        (["processing", "approved"], "Rendering", "accent"),
        (["processing_failed"], "Render failed", "bad"),
        (["processing_failed", "processing"], "Render failed", "bad"),
        (["skipped"], "Skipped", "muted"),
        (["skipped", "recut"], "Awaiting review", "warn"),
        (["recut"], "Awaiting review", "warn"),
        (["complete", "recut"], "Awaiting review", "warn"),
        (["complete", "proposed"], "Awaiting review", "warn"),
        ([], "Nothing to publish", "muted"),
    ],
)
def test_a_reviewed_recording_says_what_became_of_its_segments(states, label, tone):
    assert says_state("reviewed", [segment(state) for state in states]) == (label, tone)


def test_a_reviewed_recording_whose_complete_segments_are_all_archived_says_archived():
    assert says_state("reviewed", [segment("complete", intent="archive")]) == (
        "Archived",
        "muted",
    )


@pytest.mark.parametrize(
    ("state", "words"),
    [
        ("awaiting_review", "Awaiting review"),
        ("reviewed", "Reviewed"),
        ("analyzing", "Analysing"),
        ("analysis_failed", "Analysis failed"),
        ("some_new_state", "Some new state"),
    ],
)
def test_a_recording_state_reads_as_words_without_its_segments(state, words):
    assert says_state_alone(state) == words


def test_a_recut_segment_awaits_disposition_and_brings_its_recording_to_review(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="recording_20260913_090014.flac",
            state="reviewed",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=3600.0,
        )
    )
    store.saves(segment("recut"))

    page = ListsRecordings(store=store).paginates()

    assert page.awaiting == 1
    assert [row.recording_id for row in page.waiting] == [recording.recording_id]
    (row,) = page.rows
    assert (row.state_label, row.awaiting_disposition, row.needs_attention) == (
        "Awaiting review",
        1,
        True,
    )


@pytest.mark.parametrize(
    ("state", "duration_seconds", "duration", "undownloaded"),
    [
        ("discovered", None, "—", True),
        ("discovered", 0.0, "—", True),
        ("discovered", 3600.0, "1:00:00", False),
        ("reviewed", 3600.0, "1:00:00", False),
    ],
)
def test_a_recording_with_no_source_yet_reads_as_undownloaded_with_no_duration(
    store, state, duration_seconds, duration, undownloaded
):
    store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="recording_20260913_090014.flac",
            state=state,
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=duration_seconds,
        )
    )

    (row,) = ListsRecordings(store=store)()

    assert (row.duration, row.undownloaded) == (duration, undownloaded)


def test_each_segment_on_a_row_carries_its_own_label(store):
    store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="recording_20260913_090014.flac",
            state="reviewed",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=3600.0,
        )
    )
    store.saves(replace(segment("complete"), label="Hebrews 13.20-21"))
    store.saves(replace(segment("proposed"), classification="lesson"))

    (row,) = ListsRecordings(store=store)()

    assert sorted((item[0], item[3]) for item in row.segments) == [
        ("lesson", None),
        ("sermon", "Hebrews 13.20-21"),
    ]
