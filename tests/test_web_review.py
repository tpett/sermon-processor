from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

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


PRODUCTION_SPAN = (3060.83, 5594.695)
PRODUCTION_PUNCHES = (3060.83, 5594.575)


def a_reviewable_segment(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260927_095721",
            object_key="recordings/recording_20260927_095721.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 27, 9, 57, 21, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=7200.0,
        )
    )
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=PRODUCTION_SPAN[0],
            span_end_seconds=PRODUCTION_SPAN[1],
            punch_in_seconds=PRODUCTION_PUNCHES[0],
            punch_out_seconds=PRODUCTION_PUNCHES[1],
        )
    )


def detail_of(client, segment, **query):
    asked = {"segment": segment.segment_id} | query
    return client.get(
        f"/recordings/{segment.recording_id}", query_string=asked
    ).get_data(as_text=True)


def test_the_rendered_playhead_starts_at_the_focused_boundary(store):
    segment = a_reviewable_segment(store)
    client = creates_app(store=store).test_client()
    page = detail_of(client, segment, focus="punch-out")
    assert f'data-role="detail-playhead" data-playhead-seconds="{PRODUCTION_PUNCHES[1]}"' in page


def test_the_rendered_playhead_falls_back_to_the_punch_in(store):
    segment = a_reviewable_segment(store)
    client = creates_app(store=store).test_client()
    page = detail_of(client, segment)
    assert f'data-role="detail-playhead" data-playhead-seconds="{PRODUCTION_PUNCHES[0]}"' in page


def test_punching_from_the_playhead_before_any_seek_is_not_a_refusal(store):
    segment = a_reviewable_segment(store)
    client = creates_app(store=store).test_client()
    posted = client.post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}"
        f"/boundaries/punch-out",
        data={"do": "playhead"},
    )
    notice = parse_qs(urlsplit(posted.headers["Location"]).query).get("notice", [""])[0]
    assert notice == "adjusted", notice
    assert store.loads(Segment, segment.segment_id).punch_out_seconds != 0.0


def test_the_punch_control_is_withheld_when_the_playhead_cannot_be_punched(store):
    segment = a_reviewable_segment(store)
    client = creates_app(store=store).test_client()
    client.post(
        f"/api/recordings/{segment.recording_id}/seek", json={"seconds": 10.0}
    )
    page = detail_of(client, segment)
    assert "the playhead is outside the Segment" in page
    assert 'data-role="punch-from-playhead" disabled' in page


def test_a_punch_in_reaches_earlier_than_the_detected_span_once_it_is_grown(store):
    segment = a_reviewable_segment(store)
    client = creates_app(store=store).test_client()
    client.post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}/span/start",
        data={"do": "set", "timecode": "3000.0"},
    )
    client.post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}"
        f"/boundaries/punch-in",
        data={"do": "set", "timecode": "3054.93"},
    )
    stored = store.loads(Segment, segment.segment_id)
    assert stored.span_start_seconds == 3000.0
    assert stored.punch_in_seconds == 3054.93
