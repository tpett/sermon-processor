from datetime import UTC, datetime

import pytest

from sermon.store import Job, Proposal, Recording, Segment, opens_store
from sermon.web import creates_app


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def test_approve_via_http_queues_render(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_102900",
            object_key="recordings/recording_20260823_102900.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=7200.0,
            span_end_seconds=9900.0,
            punch_in_seconds=7200.0,
            punch_out_seconds=9900.0,
        )
    )
    store.saves(
        Proposal(
            segment_id=segment.segment_id,
            classification_confidence="high",
            boundary_confidence="high",
            punch_in_grade="easy",
            punch_out_grade="easy",
        )
    )
    client = creates_app(store=store).test_client()
    response = client.post(f"/api/segments/{segment.segment_id}/approve")
    assert response.status_code == 200
    body = response.get_json()
    assert body["segments"][0]["state"] == "approved"
    jobs = store.lists(Job, segment_id=segment.segment_id, kind="render")
    assert jobs[0].state == "queued"


def test_an_unknown_recording_id_is_not_found_on_the_html_route(store):
    client = creates_app(store=store).test_client()
    assert client.get("/recordings/recording_20260101_000000").status_code == 404


def test_an_unknown_recording_id_is_not_found_on_the_api_route(store):
    client = creates_app(store=store).test_client()
    response = client.get("/api/recordings/recording_20260101_000000")
    assert response.status_code == 404
    assert response.get_json() == {"error": "no such recording"}
