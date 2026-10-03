from datetime import UTC, date, datetime

import pytest

from sermon.shows_recording import SEGMENT_ACTION_PATHS, SEGMENT_ACTIONS
from sermon.store import Job, LogEntry, Recording, Segment, opens_store
from sermon.web import creates_app

from steps._markup import reads_field

FROZEN = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
RECORDING_ID = "recording_20260913_090014"


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def failed_render(store, state="processing_failed"):
    store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=f"{RECORDING_ID}.flac",
            state="reviewed",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            duration_seconds=10990.0,
            size_bytes=1,
        )
    )
    segment = store.saves(
        Segment(
            recording_id=RECORDING_ID,
            classification="sermon",
            state=state,
            span_start_seconds=1.0,
            span_end_seconds=3500.0,
            punch_in_seconds=1.0,
            punch_out_seconds=3500.0,
            intent="publish",
            label="Hebrews 12.25-29",
            publication_date=date(2026, 9, 13),
            disposition_at=FROZEN,
        )
    )
    store.saves(
        Job(
            recording_id=RECORDING_ID,
            segment_id=segment.segment_id,
            kind="render",
            state="failed",
            attempts=5,
            max_attempts=5,
            failed_permanently=True,
            dedupe_key=f"render:{segment.segment_id}",
            queued_at=FROZEN,
            last_error="encode: ffmpeg exited 1",
        )
    )
    return segment


def acts(store, segment, action):
    client = creates_app(store=store, clock=lambda: FROZEN).test_client()
    response = client.post(f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/{action}")
    assert response.status_code == 303, response.status_code
    return client.get(response.headers["Location"]).get_data(as_text=True)


def queued_renders(store, segment):
    return [
        job
        for job in store.lists(Job, segment_id=segment.segment_id, kind="render")
        if job.state == "queued"
    ]


def test_a_failed_render_is_offered_a_retry_rather_than_a_reversal(store):
    assert SEGMENT_ACTIONS["processing_failed"] == ("Retry processing",)


def test_retrying_processing_queues_a_render_without_re_approving(store):
    segment = failed_render(store)
    page = acts(store, segment, "retry-processing")
    assert [job.attempts for job in queued_renders(store, segment)] == [0]
    kept = store.loads(Segment, segment.segment_id)
    assert (kept.intent, kept.label, kept.disposition_at) == (
        "publish",
        "Hebrews 12.25-29",
        FROZEN,
    )
    assert [entry.entered_state for entry in store.lists(LogEntry)] == []
    assert "render is queued" in reads_field(page, "action-notice")


def test_retrying_processing_twice_queues_one_render(store):
    segment = failed_render(store)
    acts(store, segment, "retry-processing")
    acts(store, segment, "retry-processing")
    assert len(queued_renders(store, segment)) == 1


def test_only_a_failed_render_can_be_retried(store):
    segment = failed_render(store, state="proposed")
    acts(store, segment, "retry-processing")
    assert queued_renders(store, segment) == []


@pytest.mark.parametrize("label", SEGMENT_ACTIONS["processing_failed"])
def test_every_action_offered_on_a_failed_render_succeeds(store, label):
    segment = failed_render(store)
    page = acts(store, segment, SEGMENT_ACTION_PATHS[label])
    assert "cannot" not in reads_field(page, "action-notice")
