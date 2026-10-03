from datetime import UTC, date, datetime, timedelta

import pytest

from sermon.jobs.downloads_recording import FetchesObject
from sermon.reconciles_bucket import ReconcilesBucket
from sermon.store import Discovery, Job, Recording, SkippedObject, opens_store
from sermon.web import creates_app

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
    assert store.lists(Job, recording_id=unseen.recording_id) == []
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


def test_manual_ingest_queues_the_download_the_scan_does_not(store):
    recording = reconciles(store, FetchesObject()).ingests(UNSEEN)
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="download")
    assert [(job.state, job.dedupe_key) for job in jobs] == [
        ("queued", f"download:{recording.recording_id}")
    ]


def ingests_over_http(store, body):
    client = creates_app(
        store=store, clock=lambda: FROZEN, lists_objects=FetchesObject().lists
    ).test_client()
    return client.post("/api/ingest", json=body)


def leaves_no_trace(store):
    assert store.lists(Recording) == []
    assert store.lists(Job) == []
    assert store.lists(Discovery) == []
    assert store.lists(SkippedObject) == []


@pytest.mark.parametrize(
    "object_key",
    [
        "recordings/not-a-recording.flac",
        "notes/readme.txt",
        "recordings/recording_20261399_250000.flac",
        "recordings/recording_20260823_102952.flac.meta.json",
        7,
    ],
)
def test_ingesting_a_key_that_names_no_recording_is_refused_without_side_effects(
    store, object_key
):
    response = ingests_over_http(store, {"object_key": object_key})
    assert response.status_code == 422
    assert response.get_json() == {"malformed": "object_key"}
    leaves_no_trace(store)


@pytest.mark.parametrize("body", [{}, {"object_key": ""}, None])
def test_ingesting_without_a_key_is_refused_without_side_effects(store, body):
    response = ingests_over_http(store, body)
    assert response.status_code == 422
    assert response.get_json() == {"missing": "object_key"}
    leaves_no_trace(store)


def test_ingesting_a_body_that_is_not_an_object_is_refused_without_side_effects(store):
    response = ingests_over_http(store, [UNSEEN])
    assert response.status_code == 422
    leaves_no_trace(store)


def test_ingesting_a_well_formed_key_before_the_cutoff_is_still_accepted(store):
    response = ingests_over_http(
        store, {"object_key": "recordings/recording_20240107_101500.flac"}
    )
    assert response.status_code == 202
    assert response.get_json()["recording_id"] == "recording_20240107_101500"


def test_a_key_with_an_impossible_date_is_skipped_rather_than_ending_the_scan(store):
    fetches = FetchesObject()
    fetches.stores(
        "recordings/recording_20261399_250000.flac",
        FLAC_BYTES,
        last_modified=FROZEN - timedelta(hours=1),
    )
    fetches.stores(UNSEEN, FLAC_BYTES, last_modified=FROZEN - timedelta(hours=1))
    reconciles(store, fetches)()
    assert [item.reason for item in store.lists(SkippedObject)] == [
        "key does not match the pattern"
    ]
    assert [item.object_key for item in store.lists(Recording)] == [UNSEEN]
    assert store.lists(Discovery)[0].discovered_count == 1
