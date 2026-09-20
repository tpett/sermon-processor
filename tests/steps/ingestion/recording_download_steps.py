import json
from dataclasses import replace
from datetime import UTC, datetime
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


@when("the download job runs")
def _(store, object_store, clock):
    RunsDownloadJob(store=store, fetches=object_store, probes=DERIVED, clock=clock)()


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
