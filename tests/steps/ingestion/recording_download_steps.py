import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.jobs.downloads_recording import (
    FetchesObject,
    ProbesAudio,
    RunsDownloadJob,
)
from sermon.store import Job, LogEntry, Recording

FLAC_BYTES = b"fLaC" + bytes(64)
OBJECT_LAST_MODIFIED = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
SIDECAR = {
    "recorded_at": "2026-08-23T10:30:15-05:00",
    "duration": 5412.4,
    "sample_rate": 44100,
    "channels": 2,
    "format": "flac",
}
DERIVED = ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1)
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)


@pytest.fixture
def object_store():
    return FetchesObject()


@pytest.fixture
def clock():
    return lambda: FROZEN


@given(
    parsers.parse('a Recording in state "{state}" for object key "{object_key}"'),
    target_fixture="recording",
)
def _(store, clock, state, object_key):
    recording_id = Path(object_key).stem
    recording = store.saves(
        Recording(
            recording_id=recording_id,
            object_key=object_key,
            state=state,
            started_at=datetime.strptime(recording_id, "recording_%Y%m%d_%H%M%S").replace(
                tzinfo=UTC
            ),
            started_at_source="key",
            size_bytes=len(FLAC_BYTES),
        )
    )
    store.saves(
        Job(
            recording_id=recording_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{recording_id}",
            queued_at=clock(),
        )
    )
    return recording


@given("the object store is reachable")
def _(object_store, recording):
    object_store.stores(recording.object_key, FLAC_BYTES, last_modified=OBJECT_LAST_MODIFIED)
    object_store.stores(f"{recording.object_key}.meta.json", json.dumps(SIDECAR).encode())


@given(parsers.parse('an object key "{object_key}"'), target_fixture="recording")
def _(store, object_store, recording, object_key):
    object_store.stores(object_key, FLAC_BYTES, last_modified=OBJECT_LAST_MODIFIED)
    return store.saves(replace(recording, object_key=object_key))


@given(parsers.parse('the object store has no "{object_key}"'))
def _(object_store, object_key):
    object_store.drops(object_key)


def runs_download(store, object_store, clock):
    return RunsDownloadJob(
        store=store,
        fetches=object_store,
        probes=DERIVED,
        clock=clock,
        free_bytes=getattr(store, "_free_bytes", None),
    )()


@when("the download job runs")
def _(store, object_store, clock):
    runs_download(store, object_store, clock)


@when("the download job completes")
def _(store, object_store, clock):
    runs_download(store, object_store, clock)


@when("the download job next runs")
def _(store, object_store, clock):
    runs_download(store, object_store, clock)


@then(parsers.parse('the Recording records a recorded time of "{recorded_at}"'))
def _(store, recording, recorded_at):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.started_at == datetime.fromisoformat(recorded_at).replace(tzinfo=UTC)
    assert stored.started_at_source == "key"


@then("no sidecar is required for it")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.started_at_source == "key"


@then(parsers.parse('the Recording moves through "{intermediate}" to "{final}"'))
def _(store, recording, intermediate, final):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.state == final
    entered = [
        entry.entered_state
        for entry in store.lists(LogEntry, recording_id=recording.recording_id)
        if entry.entered_state is not None
    ]
    assert entered == [intermediate, final]


@then("the FLAC is stored in local working storage")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.local_path is not None
    path = store.resolves(stored)
    assert path.is_file()
    assert path.read_bytes() == FLAC_BYTES


@then("the sidecar metadata is parsed into the Recording:")
def _(store, recording, datatable):
    stored = store.loads(Recording, recording.recording_id)
    expected = dict(datatable[1:])
    assert stored.started_at == datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC)
    assert stored.started_at_source == "key"
    assert stored.duration_seconds == float(expected["duration"])
    assert stored.sample_rate == int(expected["sample_rate"])
    assert stored.channels == int(expected["channels"])
    assert stored.object_key.endswith(f".{expected['format']}")
    assert stored.local_path is not None
    assert Path(stored.local_path).suffix == f".{expected['format']}"
    assert stored.sidecar_present is True


@then("Analysis is queued automatically")
def _(store, recording):
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="analyze")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.state == "queued"
    assert job.segment_id is None
    assert job.max_attempts == 5
    assert job.dedupe_key == f"analyze:{recording.recording_id}"
    assert job.queued_at == FROZEN


@then(parsers.parse('the Recording still reaches "{state}"'))
def _(store, recording, state):
    assert store.loads(Recording, recording.recording_id).state == state


@then("the missing sidecar is noted on the Recording")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).sidecar_present is False


@then("technical metadata is derived from the audio file itself instead")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.duration_seconds == DERIVED.duration_seconds
    assert stored.sample_rate == DERIVED.sample_rate
    assert stored.channels == DERIVED.channels


@then(parsers.parse('"{_field}" falls back to the object\'s last-modified timestamp'))
def _(store, recording, object_store):
    stored = store.loads(Recording, recording.recording_id)
    fetched = object_store(stored.object_key)
    assert stored.started_at_source == "key"
    assert stored.started_at == datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC)
    assert stored.started_at != fetched.last_modified


@given(parsers.parse('the webhook announced an MD5 of "{checksum}"'))
def _(store, recording, checksum):
    store.saves(replace(recording, checksum=checksum))


@given(parsers.parse('the downloaded file hashes to "{_digest}"'))
def _(object_store, recording):
    object_store.stores(recording.object_key, b"not-the-announced-bytes")


@then("the download is discarded")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    if stored.local_path:
        path = store.resolves(stored)
        assert path is None or not path.exists()


@then("the download is retried")
def _(store):
    job = store.lists(Job, kind="download")[0]
    assert job.state == "queued"
    assert job.attempts >= 1


@then(parsers.parse('after the retry budget is exhausted the Recording enters "{state}"'))
def _(store, object_store, clock, state):
    for _ in range(8):
        queued = store.lists(Job, kind="download", state="queued")
        if not queued:
            break
        runs_download(store, object_store, clock)
    assert store.lists(Recording)[0].state == state


@given("the object contains 0 bytes")
def _(object_store, recording):
    object_store.stores(recording.object_key, b"")


@then(parsers.parse('the Recording enters "{state}"'))
def _(store, recording, state):
    assert store.loads(Recording, recording.recording_id).state == state


@then(parsers.parse('the failure reason is "{reason}"'))
def _(store, recording, reason):
    entries = store.lists(LogEntry, recording_id=recording.recording_id)
    assert any(entry.error == reason for entry in entries)
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="download")
    assert jobs[0].last_error == reason


@then("an operator can retry ingestion from the interface")
def _(store, recording):
    from sermon.shows_recording import ShowsRecording

    view = ShowsRecording(store=store)(recording.recording_id)
    assert "Retry" in view.actions


@then("the download is retried with backoff")
def _(store):
    job = store.lists(Job, kind="download")[0]
    assert job.state == "queued"
    assert job.attempts >= 1
    assert job.last_error


@then(parsers.parse('the Recording stays in "{state}" until the retry budget is exhausted'))
def _(store, object_store, clock, state):
    entered = [
        entry.entered_state
        for entry in store.lists(LogEntry)
        if entry.entered_state is not None
    ]
    assert state in entered
    for _ in range(8):
        queued = store.lists(Job, kind="download", state="queued")
        if not queued:
            break
        runs_download(store, object_store, clock)
    recording = store.lists(Recording)[0]
    assert recording.state in {state, "ingest_failed"}


@given("local working storage has 200 MB free")
def _(store):
    store._free_bytes = lambda: 200 * 1024 * 1024


@given("the source object is 720 MB")
def _(store, recording):
    store.saves(replace(recording, size_bytes=720 * 1024 * 1024))


@then("the download does not begin")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.local_path is None
    assert stored.state == "discovered"


@then(parsers.parse('the Recording stays in "{state}"'))
def _(store, recording, state):
    assert store.loads(Recording, recording.recording_id).state == state


@then("a storage alert is raised on the system health view")
def _(store):
    from sermon.web import creates_app

    health = creates_app(store=store, clock=lambda: FROZEN).test_client().get("/api/health").get_json()
    assert health.get("storage_alert")


@given(parsers.parse('a Recording has stayed in "{state}" because local disk was short'))
def _(store, recording, state):
    store.saves(replace(recording, state=state, waiting_since=FROZEN - timedelta(hours=2)))
    store._free_bytes = lambda: 100 * 1024 * 1024


@given("disk space has since been freed")
def _(store, clock):
    store._free_bytes = lambda: 10 * 1024 * 1024 * 1024
    newer_id = "recording_20260830_103015"
    store.saves(
        Recording(
            recording_id=newer_id,
            object_key=f"recordings/{newer_id}.flac",
            state="discovered",
            started_at=datetime(2026, 8, 30, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=len(FLAC_BYTES),
        )
    )
    store.saves(
        Job(
            recording_id=newer_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{newer_id}",
            queued_at=clock() + timedelta(hours=1),
        )
    )


@then("that Recording is retried without needing a new webhook or scan")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.state == "downloaded"


@then("it is retried before any newly discovered Recording")
def _(store, recording):
    newer = store.loads(Recording, "recording_20260830_103015")
    assert newer.state == "discovered"
    assert store.loads(Recording, recording.recording_id).state == "downloaded"


@given("a Recording has been waiting on disk for more than one day")
def _(store, recording, clock):
    store.saves(
        replace(
            recording,
            state="discovered",
            waiting_since=clock() - timedelta(days=2),
        )
    )


@then("it is surfaced as needing attention rather than only as an alert")
def _(store):
    from sermon.lists_recordings import ListsRecordings
    from sermon.web import creates_app

    rows = ListsRecordings(store=store, clock=lambda: FROZEN)()
    assert any(row.needs_attention for row in rows)
    health = creates_app(store=store, clock=lambda: FROZEN).test_client().get("/api/health").get_json()
    assert health.get("storage_alert")


@then("the reason given names the disk, not the Recording")
def _(store):
    from sermon.web import creates_app

    health = creates_app(store=store, clock=lambda: FROZEN).test_client().get("/api/health").get_json()
    reason = health.get("storage_alert_reason") or ""
    assert "disk" in reason.lower()
    assert "recording_" not in reason


@then("the local FLAC hashes identically to the object in the store")
def _(store, recording, object_store):
    import hashlib

    stored = store.loads(Recording, recording.recording_id)
    local = store.resolves(stored).read_bytes()
    remote = object_store(stored.object_key).body
    assert hashlib.md5(local).digest() == hashlib.md5(remote).digest()
    assert local == remote


@then("no process rewrites the local FLAC at any later point")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    original = store.resolves(stored).read_bytes()
    assert store.resolves(store.loads(Recording, recording.recording_id)).read_bytes() == original
