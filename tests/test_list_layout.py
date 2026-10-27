from datetime import UTC, datetime

import pytest

from sermon.store import Block, Job, Recording, RecordingTitle, Segment, opens_store
from steps import _browser


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def saves_recording(store, stamp, **fields):
    held = {
        "object_key": f"{stamp}.flac",
        "state": "discovered",
        "started_at": datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
        "started_at_source": "key",
        "size_bytes": 1,
        "duration_seconds": 3600.0,
    } | fields
    return store.saves(Recording(recording_id=f"recording_{stamp}", **held))


def titles(store, recording, title):
    store.saves(RecordingTitle(recording_id=recording.recording_id, title=title))


def saves_awaiting(store, stamp, title):
    recording = saves_recording(
        store, stamp, state="awaiting_review", kind="service", duration_seconds=7200.0
    )
    titles(store, recording, title)
    block = store.saves(
        Block(
            recording_id=recording.recording_id,
            type="sermon",
            start_seconds=1000.0,
            end_seconds=3000.0,
        )
    )
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            seed_block_id=block.block_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=1000.0,
            span_end_seconds=3000.0,
            punch_in_seconds=1000.0,
            punch_out_seconds=3000.0,
        )
    )
    return recording


def test_clicking_ingest_on_a_discovered_row_posts_the_ingest_action(store):
    discovered = saves_recording(store, "20260913_090014")
    with _browser.opens_page(store) as page:
        page.goto("/")
        with page.expect_request(lambda request: request.method == "POST") as posted:
            page.locator('[data-field="row-ingest-control"]').click()

        assert posted.value.url.endswith(f"/recordings/{discovered.recording_id}/actions/ingest")
    assert store.lists(Job, recording_id=discovered.recording_id, kind="download")
