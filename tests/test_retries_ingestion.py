from datetime import UTC, datetime

import pytest

from sermon.jobs.downloads_recording import FetchesObject, ProbesAudio, RunsDownloadJob
from sermon.store import Job, Recording, opens_store
from sermon.web import creates_app

from steps._markup import reads_field

FLAC_BYTES = b"fLaC" + bytes(64)
FROZEN = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
RECORDING_ID = "recording_20260913_090014"
OBJECT_KEY = f"recordings/{RECORDING_ID}.flac"


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def failed(store):
    recording = store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=OBJECT_KEY,
            state="ingest_failed",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=len(FLAC_BYTES),
        )
    )
    store.saves(
        Job(
            recording_id=RECORDING_ID,
            kind="download",
            state="failed",
            attempts=5,
            max_attempts=5,
            failed_permanently=True,
            dedupe_key=f"download:{RECORDING_ID}",
            queued_at=FROZEN,
            last_error="connection reset",
        )
    )
    return recording


def retries(store, action="retry-ingestion"):
    client = creates_app(store=store, clock=lambda: FROZEN).test_client()
    response = client.post(f"/recordings/{RECORDING_ID}/actions/{action}")
    assert response.status_code == 303, response.status_code
    return client.get(response.headers["Location"]).get_data(as_text=True)


def in_flight(store):
    return [
        (job.kind, job.state)
        for job in store.lists(Job, recording_id=RECORDING_ID)
        if job.state in {"queued", "running"}
    ]


def test_retrying_ingestion_queues_a_download_not_an_analysis(store, failed):
    page = retries(store)
    assert in_flight(store) == [("download", "queued")]
    assert store.lists(Job, kind="analyze") == []
    queued = [job for job in store.lists(Job, kind="download") if job.state == "queued"]
    assert queued[0].attempts == 0
    assert "download is queued" in reads_field(page, "action-notice")


def test_retrying_ingestion_twice_queues_one_download(store, failed):
    retries(store)
    page = retries(store)
    assert in_flight(store) == [("download", "queued")]
    assert "download is queued" not in reads_field(page, "action-notice")


def test_the_retried_download_takes_the_recording_out_of_ingest_failed(store, failed):
    retries(store)
    assert store.loads(Recording, RECORDING_ID).state == "ingest_failed"
    fetches = FetchesObject()
    fetches.stores(OBJECT_KEY, FLAC_BYTES, last_modified=FROZEN)
    RunsDownloadJob(
        store=store,
        fetches=fetches,
        probes=ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1),
        clock=lambda: FROZEN,
    )()
    assert store.loads(Recording, RECORDING_ID).state == "downloaded"


def test_retrying_analysis_still_queues_an_analysis(store, failed):
    retries(store, "retry-analysis")
    assert in_flight(store) == [("analyze", "queued")]
