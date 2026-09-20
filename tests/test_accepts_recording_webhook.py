from datetime import UTC, datetime

import pytest

from sermon.accepts_recording_webhook import AcceptsRecordingWebhook
from sermon.store import Discovery, Job, Recording, opens_store
from sermon.web import creates_app

PAYLOAD = {
    "event": "recording.uploaded",
    "bucket": "sermons",
    "object_key": "recordings/recording_20260823_102952.flac",
    "metadata_key": "recordings/recording_20260823_102952.flac.meta.json",
    "size_bytes": 841368564,
    "md5": "8f14e45fceea167a5a36dedd4bea2543",
    "recorded_at": "2026-08-23T10:29:52-05:00",
    "duration": 6268.95,
    "sample_rate": 44100,
    "channels": 2,
}

FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def test_queued_at_comes_from_the_injected_clock(store):
    client = creates_app(store=store, clock=lambda: FROZEN).test_client()
    response = client.post("/api/webhooks/recordings", json=PAYLOAD)
    assert response.status_code == 202
    assert store.lists(Job)[0].queued_at == FROZEN


def test_started_at_is_parsed_from_the_key_not_recorded_at(store):
    AcceptsRecordingWebhook(store=store, clock=lambda: FROZEN)(PAYLOAD)
    recording = store.loads(Recording, "recording_20260823_102952")
    assert recording.started_at == datetime(2026, 8, 23, 10, 29, 52, tzinfo=UTC)
    assert recording.started_at_source == "key"


def test_probe_fields_are_not_stored_from_the_webhook(store):
    AcceptsRecordingWebhook(store=store, clock=lambda: FROZEN)(PAYLOAD)
    recording = store.loads(Recording, "recording_20260823_102952")
    assert recording.duration_seconds is None
    assert recording.sample_rate is None
    assert recording.channels is None


def test_a_webhook_does_not_write_a_discovery(store):
    AcceptsRecordingWebhook(store=store, clock=lambda: FROZEN)(PAYLOAD)
    assert store.lists(Discovery) == []
