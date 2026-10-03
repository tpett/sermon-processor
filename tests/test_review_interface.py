from datetime import UTC, datetime

import pytest

from sermon.store import Recording, Segment, opens_store
from sermon.web import creates_app
from steps._markup import reads_role, reads_rows


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def recording(store):
    return store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="2026/09/13/recording_20260913_090014.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=3600.0,
        )
    )


def saves_segment(store, recording, **seconds):
    held = {
        "span_start_seconds": 1165.74,
        "span_end_seconds": 3000.0,
        "punch_in_seconds": 1165.74,
        "punch_out_seconds": 3000.0,
    } | seconds
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            **held,
        )
    )


def test_a_punch_in_just_before_its_span_does_not_open_the_page_with_dead_punch_controls(
    store, recording
):
    segment = saves_segment(store, recording, punch_in_seconds=1165.70)
    page = (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{recording.recording_id}?segment={segment.segment_id}")
        .get_data(as_text=True)
    )
    assert "disabled" not in page.split('data-role="punch"')[1].split("</ol>")[0]


def test_the_punch_controls_carry_the_span_the_client_judges_them_against(store, recording):
    segment = saves_segment(store, recording)
    page = (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{recording.recording_id}?segment={segment.segment_id}")
        .get_data(as_text=True)
    )
    punch = reads_role(page, "punch")
    assert float(punch["span-start-seconds"]) == segment.span_start_seconds
    assert float(punch["span-end-seconds"]) == segment.span_end_seconds
    assert punch["unavailable-reason"] == "the playhead is outside the Segment"
