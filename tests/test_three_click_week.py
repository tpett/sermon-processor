from datetime import UTC, datetime

import pytest

from sermon.jobs.analyzes_recording import RunsAnalyzeJob
from sermon.jobs.downloads_recording import FetchesObject, ProbesAudio, RunsDownloadJob
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.jobs.runs_queued_jobs import RunsQueuedJobs
from sermon.sends_notification import SendsNotification
from sermon.store import Artifact, Reviewer, Segment, opens_store
from sermon.web import creates_app

FLAC_BYTES = b"fLaC" + bytes(64)
OBJECT_KEY = "recordings/recording_20260823_103015.flac"
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def queued_worker(store, fetches):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    return RunsQueuedJobs(
        store=store,
        downloads=RunsDownloadJob(
            store=store,
            fetches=fetches,
            probes=ProbesAudio(duration_seconds=11520.0, sample_rate=44100, channels=1),
            clock=lambda: FROZEN,
        ),
        analyzes=RunsAnalyzeJob(
            store=store,
            stages=lambda _name: None,
            notifies=SendsNotification(store=store),
            clock=lambda: FROZEN,
        ),
        renders=RunsRenderJob(
            store=store,
            steps=lambda _name: None,
            notifies=SendsNotification(store=store),
            clock=lambda: FROZEN,
        ),
    )


def test_webhook_to_named_mp3(store):
    fetches = FetchesObject()
    fetches.stores(OBJECT_KEY, FLAC_BYTES)
    client = creates_app(store=store, clock=lambda: FROZEN).test_client()
    announced = client.post(
        "/api/webhooks/recordings",
        json={"event": "recording.uploaded", "object_key": OBJECT_KEY, "size_bytes": len(FLAC_BYTES)},
    )
    assert announced.status_code == 202
    worker = queued_worker(store, fetches)
    worker()
    worker()
    listings = client.get("/api/recordings").get_json()["recordings"]
    assert listings[0]["state"] == "awaiting_review"
    recording_id = listings[0]["recording_id"]
    detail = client.get(f"/api/recordings/{recording_id}").get_json()
    sermon = next(segment for segment in detail["segments"] if segment["classification"] == "sermon")
    client.put(
        f"/api/segments/{sermon['segment_id']}/publication",
        json={"date": "2026-08-23", "label": "Hebrews 12.4-11"},
    )
    approved = client.post(f"/api/segments/{sermon['segment_id']}/approve")
    assert approved.status_code == 200
    worker()
    artifacts = store.lists(Artifact, kind="rendered_mp3")
    assert artifacts[0].path == "2026-08-23 - Hebrews 12.4-11.mp3"
    assert store.loads(Segment, sermon["segment_id"]).state == "complete"
