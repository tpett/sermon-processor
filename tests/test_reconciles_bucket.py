from datetime import UTC, date, datetime, timedelta

import pytest

from sermon.jobs.downloads_recording import FetchesObject
from sermon.reconciles_bucket import ReconcilesBucket
from sermon.store import Discovery, Job, Recording, SkippedObject, opens_store

FLAC_BYTES = b"fLaC" + bytes(64)
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
SEEN = "recordings/recording_20260823_103015.flac"
UNSEEN = "recordings/recording_20260816_102958.flac"


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def reconciles(store, fetches, *, ingest_cutoff=date(2026, 1, 1)):
    return ReconcilesBucket(
        store=store,
        lists_objects=fetches.lists,
        clock=lambda: FROZEN,
        ingest_cutoff=ingest_cutoff,
    )


def test_scan_creates_a_recording_for_an_unseen_object(store):
    fetches = FetchesObject()
    fetches.stores(
        SEEN,
        FLAC_BYTES,
        last_modified=FROZEN - timedelta(hours=1),
        size_bytes=743829120,
    )
    fetches.stores(
        UNSEEN,
        FLAC_BYTES,
        last_modified=FROZEN - timedelta(hours=1),
        size_bytes=701244416,
    )
    store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key=SEEN,
            state="discovered",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=743829120,
        )
    )
    reconciles(store, fetches)()
    unseen = store.loads(Recording, "recording_20260816_102958")
    assert unseen.object_key == UNSEEN
    assert unseen.state == "discovered"
    assert unseen.size_bytes == 701244416
    jobs = store.lists(Job, recording_id=unseen.recording_id, kind="download")
    assert len(jobs) == 1
    assert jobs[0].state == "queued"
    assert [item.object_key for item in store.lists(Recording, object_key=SEEN)] == [SEEN]


def test_a_file_still_being_uploaded_is_left_for_the_next_scan(store):
    fetches = FetchesObject()
    fetches.stores(
        SEEN,
        FLAC_BYTES,
        last_modified=FROZEN - timedelta(seconds=4),
    )
    reconciles(store, fetches)()
    assert store.lists(Recording) == []
    assert store.lists(SkippedObject) == []


def test_non_recording_objects_are_skipped(store):
    fetches = FetchesObject()
    fetches.stores("recordings/README.txt", b"readme", last_modified=FROZEN - timedelta(hours=1))
    reconciles(store, fetches)()
    assert store.lists(Recording) == []
    skipped = store.lists(SkippedObject)
    assert skipped[0].object_key == "recordings/README.txt"
    assert skipped[0].reason == "not an audio object"


def test_objects_before_the_ingest_cutoff_are_skipped(store):
    fetches = FetchesObject()
    fetches.stores(
        "recordings/recording_20240107_101500.flac",
        FLAC_BYTES,
        last_modified=FROZEN - timedelta(hours=1),
    )
    reconciles(store, fetches, ingest_cutoff=date(2026, 6, 1))()
    assert store.lists(Recording) == []
    assert store.lists(SkippedObject)[0].reason == "before the ingest cutoff"


def test_a_failed_scan_writes_a_transient_discovery(store):
    fetches = FetchesObject()
    fetches.error = "connection"
    reconciles(store, fetches)()
    assert store.lists(Recording) == []
    discovery = store.lists(Discovery)[0]
    assert discovery.kind == "scan"
    assert discovery.failure == "transient"
    assert discovery.discovered_count == 0


def test_a_403_is_a_credential_failure(store):
    fetches = FetchesObject()
    fetches.error = "403 Forbidden"
    reconciles(store, fetches)()
    discovery = store.lists(Discovery)[0]
    assert discovery.failure == "credentials"


def test_manual_ingest_ignores_the_cutoff(store):
    recording = reconciles(store, FetchesObject(), ingest_cutoff=date(2026, 6, 1)).ingests(
        "recordings/recording_20240107_101500.flac"
    )
    assert recording.state == "discovered"
    assert store.lists(Job, kind="download")
