import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sermon.jobs.downloads_recording import (
    DownloadsRecording,
    FetchesObject,
    ProbesAudio,
    RunsDownloadJob,
)
from sermon.store import Job, Recording, opens_store

FLAC_BYTES = b"fLaC" + bytes(64)
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
SIDECAR_RECORDED_AT = "2026-08-23T10:30:15-05:00"
PROBE = ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1)
OBJECT_KEY = "recordings/recording_20260823_103015.flac"


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def discovered_recording():
    return Recording(
        recording_id="recording_20260823_103015",
        object_key=OBJECT_KEY,
        state="discovered",
        started_at=datetime(2020, 1, 1, tzinfo=UTC),
        started_at_source="key",
        size_bytes=len(FLAC_BYTES),
    )


def object_store(*, sidecar=True):
    fetches = FetchesObject()
    fetches.stores(
        OBJECT_KEY,
        FLAC_BYTES,
        last_modified=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )
    if sidecar:
        fetches.stores(
            f"{OBJECT_KEY}.meta.json",
            json.dumps(
                {
                    "recorded_at": SIDECAR_RECORDED_AT,
                    "duration": 5412.4,
                    "sample_rate": 44100,
                    "channels": 2,
                    "format": "flac",
                }
            ).encode(),
        )
    return fetches


def downloads(store, fetches):
    return DownloadsRecording(store=store, fetches=fetches, probes=PROBE, clock=lambda: FROZEN)


def test_download_updates_the_already_stored_recording(store):
    recording = store.saves(discovered_recording())
    downloads(store, object_store())(recording)
    stored = store.loads(Recording, recording.recording_id)
    assert stored.state == "downloaded"
    assert stored.local_path == OBJECT_KEY
    assert stored.sidecar_present is True
    assert stored.duration_seconds == 5412.4
    assert stored.sample_rate == 44100
    assert stored.channels == 2
    assert not hasattr(stored, "format")


def test_started_at_comes_from_the_key_not_the_sidecar(store):
    recording = store.saves(discovered_recording())
    downloads(store, object_store())(recording)
    stored = store.loads(Recording, recording.recording_id)
    assert stored.started_at == datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC)
    assert stored.started_at_source == "key"
    assert stored.started_at != datetime.fromisoformat(SIDECAR_RECORDED_AT).astimezone(UTC)


def test_analyze_job_is_queued_from_the_injected_clock(store):
    recording = store.saves(discovered_recording())
    downloads(store, object_store())(recording)
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="analyze")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.state == "queued"
    assert job.segment_id is None
    assert job.max_attempts == 5
    assert job.dedupe_key == f"analyze:{recording.recording_id}"
    assert job.queued_at == FROZEN


def test_analyze_job_is_queued_when_the_sidecar_is_missing(store):
    recording = store.saves(discovered_recording())
    downloads(store, object_store(sidecar=False))(recording)
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="analyze")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.state == "queued"
    assert job.kind == "analyze"
    assert job.segment_id is None
    assert job.max_attempts == 5
    assert job.dedupe_key == f"analyze:{recording.recording_id}"
    assert job.queued_at == FROZEN


def test_missing_sidecar_derives_technical_metadata_from_the_probe(store):
    recording = store.saves(discovered_recording())
    downloads(store, object_store(sidecar=False))(recording)
    stored = store.loads(Recording, recording.recording_id)
    assert stored.sidecar_present is False
    assert stored.duration_seconds == PROBE.duration_seconds
    assert stored.sample_rate == PROBE.sample_rate
    assert stored.channels == PROBE.channels
    assert stored.started_at_source == "key"


def test_a_parseable_key_is_not_replaced_by_last_modified(store):
    recording = store.saves(discovered_recording())
    fetches = object_store(sidecar=False)
    downloads(store, fetches)(recording)
    stored = store.loads(Recording, recording.recording_id)
    assert stored.started_at == datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC)
    assert stored.started_at != fetches(OBJECT_KEY).last_modified


def test_local_path_is_relative_and_holds_the_fetched_bytes(store):
    recording = store.saves(discovered_recording())
    downloads(store, object_store())(recording)
    stored = store.loads(Recording, recording.recording_id)
    assert not Path(stored.local_path).is_absolute()
    assert store.resolves(stored).read_bytes() == FLAC_BYTES


def test_a_missing_object_is_retried_and_does_not_fail_ingest_on_the_first_attempt(store):
    recording = store.saves(discovered_recording())
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{recording.recording_id}",
            queued_at=FROZEN,
        )
    )
    fetches = FetchesObject()
    RunsDownloadJob(store=store, fetches=fetches, probes=PROBE, clock=lambda: FROZEN)()
    job = store.lists(Job, kind="download")[0]
    stored = store.loads(Recording, recording.recording_id)
    assert stored.state != "ingest_failed"
    assert job.state == "queued"
    assert job.attempts == 1
    fetches.stores(OBJECT_KEY, FLAC_BYTES)
    RunsDownloadJob(store=store, fetches=fetches, probes=PROBE, clock=lambda: FROZEN)()
    assert store.loads(Recording, recording.recording_id).state == "downloaded"
    assert store.lists(Job, kind="download")[0].state == "succeeded"
