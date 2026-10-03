from datetime import UTC, datetime

import pytest
from botocore.exceptions import EndpointConnectionError

from sermon.object_store import StreamsBucketObject
from sermon.store import Recording, layout, opens_store
from sermon.web import SOURCE_NO_LONGER_AVAILABLE, creates_app
from steps._bucket import BUCKET, HoldsBucket

OBJECT_KEY = "2026/09/13/recording_20260913_090014.flac"
FLAC = b"fLaC" + bytes(range(256)) * 4


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def bucket():
    held = HoldsBucket()
    held.holds(OBJECT_KEY, FLAC)
    return held


def remote_recording(store, **fields):
    return store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key=OBJECT_KEY,
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=len(FLAC),
            **fields,
        )
    )


def client_for(store, bucket, chunk_bytes=64):
    streams = StreamsBucketObject(bucket=BUCKET, client=bucket, chunk_bytes=chunk_bytes)
    return creates_app(store=store, streams_object=streams).test_client()


def files_under(root):
    return sorted(path for path in root.rglob("*") if path.is_file())


def test_a_source_that_is_not_local_is_streamed_from_the_bucket(store, bucket):
    remote_recording(store)
    response = client_for(store, bucket).get(f"/api/artifacts/{OBJECT_KEY}")
    assert response.status_code == 200
    assert response.data == FLAC
    assert bucket.asked == [{"Bucket": BUCKET, "Key": OBJECT_KEY}]


def test_the_stream_is_described_by_the_object_metadata(store, bucket):
    remote_recording(store)
    response = client_for(store, bucket).get(f"/api/artifacts/{OBJECT_KEY}")
    assert response.headers["Content-Length"] == str(len(FLAC))
    assert response.headers["Content-Type"] == "audio/flac"
    assert response.headers["Content-Disposition"] == (
        "attachment; filename=recording_20260913_090014.flac"
    )
    assert response.headers["Accept-Ranges"] == "bytes"
    assert response.headers["ETag"] == bucket.get_object(Bucket=BUCKET, Key=OBJECT_KEY)["ETag"]


def test_an_object_with_no_stored_type_is_offered_as_bytes(store, bucket):
    bucket.holds(OBJECT_KEY, FLAC, content_type=None)
    remote_recording(store)
    response = client_for(store, bucket).get(f"/api/artifacts/{OBJECT_KEY}")
    assert response.headers["Content-Type"] == "application/octet-stream"


def test_the_response_is_passed_through_unbuffered(store, bucket):
    remote_recording(store)
    app = creates_app(
        store=store, streams_object=StreamsBucketObject(bucket=BUCKET, client=bucket, chunk_bytes=64)
    )
    with app.test_request_context(f"/api/artifacts/{OBJECT_KEY}"):
        response = app.view_functions["artifact_download"](OBJECT_KEY)
    assert response.direct_passthrough is True
    assert bucket.bodies[0].reads == []
    assert len(next(iter(response.response))) == 64
    response.close()
    assert bucket.bodies[0].closed is True


def test_streaming_writes_nothing_to_the_data_root_and_changes_no_row(store, bucket, tmp_path):
    recording = remote_recording(store)
    before = files_under(tmp_path)
    client_for(store, bucket).get(f"/api/artifacts/{OBJECT_KEY}")
    assert files_under(tmp_path) == before
    assert store.loads(Recording, recording.recording_id) == recording


def test_a_source_named_locally_but_missing_from_disk_is_streamed(store, bucket):
    recording = remote_recording(store, local_path="recordings/recording_20260913_090014/source.flac")
    response = client_for(store, bucket).get(f"/api/artifacts/{recording.local_path}")
    assert response.data == FLAC
    assert bucket.asked == [{"Bucket": BUCKET, "Key": OBJECT_KEY}]


def test_a_local_source_is_served_from_disk_without_asking_the_bucket(store, bucket):
    recording = remote_recording(store, local_path="recordings/recording_20260913_090014/source.flac")
    held = store.resolves(recording)
    held.parent.mkdir(parents=True)
    held.write_bytes(b"fLaC-local")
    response = client_for(store, bucket).get(f"/api/artifacts/{OBJECT_KEY}")
    assert response.data == b"fLaC-local"
    assert bucket.asked == []


def test_a_resumed_download_asks_the_bucket_for_the_rest(store, bucket):
    remote_recording(store)
    response = client_for(store, bucket).get(
        f"/api/artifacts/{OBJECT_KEY}", headers={"Range": "bytes=300-"}
    )
    assert response.status_code == 206
    assert response.headers["Content-Range"] == f"bytes 300-{len(FLAC) - 1}/{len(FLAC)}"
    assert response.headers["Content-Length"] == str(len(FLAC) - 300)
    assert response.data == FLAC[300:]
    assert bucket.asked == [{"Bucket": BUCKET, "Key": OBJECT_KEY, "Range": "bytes=300-"}]


def test_a_resume_against_a_matching_entity_tag_is_honoured(store, bucket):
    remote_recording(store)
    tag = bucket.get_object(Bucket=BUCKET, Key=OBJECT_KEY)["ETag"]
    response = client_for(store, bucket).get(
        f"/api/artifacts/{OBJECT_KEY}", headers={"Range": "bytes=300-", "If-Range": tag}
    )
    assert response.status_code == 206
    assert response.data == FLAC[300:]


def test_a_resume_against_a_changed_object_restarts_from_the_beginning(store, bucket):
    remote_recording(store)
    response = client_for(store, bucket).get(
        f"/api/artifacts/{OBJECT_KEY}", headers={"Range": "bytes=300-", "If-Range": '"stale"'}
    )
    assert response.status_code == 200
    assert response.data == FLAC
    assert bucket.bodies[0].closed is True


def test_a_resume_conditioned_on_a_date_restarts_from_the_beginning(store, bucket):
    remote_recording(store)
    response = client_for(store, bucket).get(
        f"/api/artifacts/{OBJECT_KEY}",
        headers={"Range": "bytes=300-", "If-Range": "Sun, 23 Aug 2026 16:05:00 GMT"},
    )
    assert response.status_code == 200
    assert response.data == FLAC


def test_several_ranges_at_once_are_answered_with_the_whole_object(store, bucket):
    remote_recording(store)
    response = client_for(store, bucket).get(
        f"/api/artifacts/{OBJECT_KEY}", headers={"Range": "bytes=0-9,20-29"}
    )
    assert response.status_code == 200
    assert response.data == FLAC
    assert bucket.asked == [{"Bucket": BUCKET, "Key": OBJECT_KEY}]


def test_a_range_past_the_end_is_refused(store, bucket):
    remote_recording(store)
    response = client_for(store, bucket).get(
        f"/api/artifacts/{OBJECT_KEY}", headers={"Range": f"bytes={len(FLAC)}-"}
    )
    assert response.status_code == 416
    assert response.headers["Content-Range"] == f"bytes */{len(FLAC)}"


def test_a_source_gone_from_the_bucket_says_so(store, bucket):
    recording = remote_recording(store)
    bucket.objects.clear()
    response = client_for(store, bucket).get(f"/api/artifacts/{OBJECT_KEY}")
    assert response.status_code == 404
    assert response.get_json() == {
        "error": SOURCE_NO_LONGER_AVAILABLE,
        "path": OBJECT_KEY,
        "recording_id": recording.recording_id,
    }


def test_an_unreachable_bucket_is_a_bad_gateway_not_a_missing_file(store, bucket):
    remote_recording(store)
    bucket.error = EndpointConnectionError(endpoint_url="https://s3.example.invalid")
    response = client_for(store, bucket).get(f"/api/artifacts/{OBJECT_KEY}")
    assert response.status_code == 502
    assert "a-secret" not in response.get_data(as_text=True)


def test_without_a_bucket_a_missing_source_is_still_unavailable(store):
    remote_recording(store)
    response = creates_app(store=store).test_client().get(f"/api/artifacts/{OBJECT_KEY}")
    assert response.status_code == 404


def test_a_missing_rendered_artifact_is_never_looked_for_in_the_bucket(store, bucket):
    from sermon.store import Artifact

    recording = remote_recording(store)
    path = layout.published_path("2026-09-13 - Hebrews 13.mp3")
    store.saves(
        Artifact(
            recording_id=recording.recording_id,
            kind="rendered_mp3",
            path=path,
            size_bytes=1,
            checksum="stub",
        )
    )
    response = client_for(store, bucket).get(f"/api/artifacts/{path}")
    assert response.status_code == 404
    assert bucket.asked == []


def test_a_local_source_resumes_from_disk(store, bucket):
    recording = remote_recording(store, local_path="recordings/recording_20260913_090014/source.flac")
    held = store.resolves(recording)
    held.parent.mkdir(parents=True)
    held.write_bytes(FLAC)
    response = client_for(store, bucket).get(
        f"/api/artifacts/{OBJECT_KEY}", headers={"Range": "bytes=300-"}
    )
    assert response.status_code == 206
    assert response.data == FLAC[300:]
    assert bucket.asked == []
