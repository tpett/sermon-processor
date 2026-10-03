from datetime import UTC, datetime

import pytest

from sermon.store import Artifact, Notification, Reviewer, Segment, opens_store
from sermon.web import creates_app
from steps._markup import reads_field, reads_rows
from test_store import minimal_recording

RAISED_AT = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    opened.saves(Reviewer(actor="reviewer"))
    yield opened
    opened.close()


def raised(store, recording, *, kind="segment_proposed", state="pending", segment=None, minute=0):
    return store.saves(
        Notification(
            recording_id=recording.recording_id,
            segment_id=None if segment is None else segment.segment_id,
            kind=kind,
            recipient="reviewer",
            summary=f"{kind} at minute {minute}",
            created_at=RAISED_AT.replace(minute=minute),
            state=state,
        )
    )


def a_segment(store, recording):
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="complete",
            span_start_seconds=60.0,
            span_end_seconds=3000.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3000.0,
        )
    )


def page(store, url="/notifications"):
    return creates_app(store=store, clock=lambda: RAISED_AT).test_client().get(url).get_data(as_text=True)


def test_the_page_lists_every_notification_newest_first_with_its_state(store):
    recording = store.saves(minimal_recording())
    first = raised(store, recording, state="delivered", minute=1)
    second = raised(store, recording, kind="nothing_publishable", state="suppressed", minute=2)
    rows = reads_rows(page(store), "notification")
    assert [(int(row["id"]), row["state"]) for row in rows] == [
        (second.notification_id, "suppressed"),
        (first.notification_id, "delivered"),
    ]
    assert first.summary in rows[1]["text"]


def test_a_segment_notification_links_to_the_segment_and_a_render_to_its_download(store):
    recording = store.saves(minimal_recording())
    segment = a_segment(store, recording)
    store.saves(
        Artifact(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="rendered_mp3",
            path="published/2026-09-13 - Hebrews.mp3",
            size_bytes=1,
            checksum="x",
        )
    )
    raised(store, recording, kind="render_complete", segment=segment)
    [row] = reads_rows(page(store), "notification")
    assert f"/recordings/{recording.recording_id}?segment={segment.segment_id}" in row["links"]
    assert "/api/artifacts/published/2026-09-13 - Hebrews.mp3" in row["links"]


def test_the_recordings_list_counts_what_is_unread_and_opening_the_page_reads_it(store):
    recording = store.saves(minimal_recording())
    raised(store, recording, minute=1)
    raised(store, recording, minute=2)
    raised(store, recording, kind="nothing_publishable", state="suppressed", minute=3)
    assert reads_field(page(store, "/"), "unread-notifications") == "2"
    assert [row["unread"] for row in reads_rows(page(store), "notification")] == ["false", "true", "true"]
    assert reads_field(page(store, "/"), "unread-notifications") == "0"
    assert {row["unread"] for row in reads_rows(page(store), "notification")} == {"false"}


def test_the_reviewer_can_turn_notifications_off_and_on_again(store):
    client = creates_app(store=store, clock=lambda: RAISED_AT).test_client()
    off = client.post("/notifications/preference", data={"receives": "off"})
    assert off.status_code == 303
    assert store.loads(Reviewer, "reviewer").receives_notifications is False
    assert "not being sent" in reads_field(page(store), "preference")
    client.post("/notifications/preference", data={"receives": "on"})
    assert store.loads(Reviewer, "reviewer").receives_notifications is True


def test_the_api_lists_notifications_with_the_unread_count(store):
    recording = store.saves(minimal_recording())
    notification = raised(store, recording)
    body = creates_app(store=store).test_client().get("/api/notifications").get_json()
    assert body["unread"] == 1
    assert [(item["notification_id"], item["state"]) for item in body["notifications"]] == [
        (notification.notification_id, "pending")
    ]


def test_a_recording_with_no_notifications_shows_an_empty_page(store):
    assert reads_field(page(store), "empty") is not None
    assert reads_field(page(store, "/"), "unread-notifications") == "0"
