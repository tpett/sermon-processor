from datetime import UTC, date, datetime
from pathlib import PurePosixPath

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.object_store import CHUNK_BYTES
from sermon.store import Artifact, Recording, Segment, layout
from sermon.web import ARTIFACT_UNAVAILABLE, REPROCESS_OFFER, creates_app
from steps import _browser
from steps._bucket import BUCKET, HoldsBucket, serves_as_deployed
from steps._markup import reads_field, reads_field_link, reads_links, reads_rows

UPLOADED_FLAC = b"fLaC" + bytes(range(256)) * 16


@pytest.fixture
def recorder_bucket():
    return HoldsBucket()


def answers_unread(store, recorder_bucket, path):
    app = serves_as_deployed(store, recorder_bucket)
    with app.test_request_context(f"/api/artifacts/{path}"):
        return app.view_functions["artifact_download"](path)


def describes_streaming(store, recorder_bucket, path):
    response = answers_unread(store, recorder_bucket, path)
    body = recorder_bucket.bodies[-1]
    described = {
        "passthrough": response.direct_passthrough,
        "buffered": isinstance(response.response, (bytes, bytearray, list, tuple)),
        "content_length": int(response.headers["Content-Length"]),
        "read_before_sending": list(body.reads),
        "first_chunk": len(next(iter(response.response))),
        "read_for_first_chunk": list(body.reads),
    }
    response.close()
    return described


def source_path(store):
    recording = store.lists(Recording)[0]
    return recording.local_path or recording.object_key


def downloads_as_deployed(store, recorder_bucket, path, headers=None):
    return serves_as_deployed(store, recorder_bucket).test_client().get(
        f"/api/artifacts/{path}", headers=headers or {}
    )


@given(
    parsers.parse('a Segment in state "{state}" from a Recording dated "{day}"'),
    target_fixture="segment",
)
def _(store, recorder_bucket, state, day):
    started = datetime.strptime(day, "%Y-%m-%d").replace(hour=10, minute=29, tzinfo=UTC)
    recording_id = started.strftime("recording_%Y%m%d_%H%M%S")
    object_key = f"recordings/{recording_id}.flac"
    recorder_bucket.holds(object_key, UPLOADED_FLAC)
    recording = store.saves(
        Recording(
            recording_id=recording_id,
            object_key=object_key,
            state="reviewed",
            started_at=started,
            started_at_source="key",
            size_bytes=len(UPLOADED_FLAC),
            duration_seconds=2592.0,
        )
    )
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state=state,
            span_start_seconds=7220.0,
            span_end_seconds=9812.0,
            punch_in_seconds=7220.0,
            punch_out_seconds=9812.0,
            publication_date=date.fromisoformat(day),
            label="Hebrews 12.4-11",
        )
    )
    path = layout.published_path(f"{day} - Hebrews 12.4-11.mp3")
    destination = store.resolves(
        Artifact(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="rendered_mp3",
            path=path,
            size_bytes=12,
            checksum="stub",
        )
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"mp3-stub-bytes")
    store.saves(
        Artifact(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="rendered_mp3",
            path=path,
            size_bytes=12,
            checksum="stub",
        )
    )
    return segment


@given(parsers.parse('its label is "{label}"'), target_fixture="segment")
def _(store, segment, label):
    from dataclasses import replace

    return store.saves(replace(segment, label=label))


def opens_the_segment(store, segment):
    return (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{segment.recording_id}?segment={segment.segment_id}")
        .get_data(as_text=True)
    )


@then("I can download the rendered MP3")
def _(store, segment):
    # The scenario says "When I open the Segment", so the page has to offer it:
    # a working route nobody can reach is not a download.
    page = opens_the_segment(store, segment)
    offered = reads_field(page, "mp3-download")
    assert offered, "the page offers no MP3 download"
    artifacts = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
    link = f"/api/artifacts/{artifacts[0].path}"
    assert link in reads_links(page), reads_links(page)
    response = creates_app(store=store).test_client().get(link)
    assert response.status_code == 200
    assert response.data == b"mp3-stub-bytes"


@then(parsers.parse('the download filename is "{filename}"'))
def _(store, segment, filename):
    artifacts = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
    assert PurePosixPath(artifacts[0].path).name == filename


@then("the file size and duration are shown before I download")
def _(store, segment):
    page = opens_the_segment(store, segment)
    artifacts = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
    assert artifacts[0].size_bytes > 0
    assert reads_field(page, "mp3-size"), "the page shows no file size"
    assert reads_field(page, "mp3-length"), "the page shows no duration"


@then("the MP3 download is not offered")
def _(store, segment):
    page = opens_the_segment(store, segment)
    assert reads_field(page, "mp3-download") is None, (
        f"a {segment.state} Segment must not offer a download"
    )


@then("I can download the original untrimmed FLAC")
def _(store, recorder_bucket, detail_page):
    link = reads_field_link(detail_page, "source-download")
    assert link, "the page offers no FLAC download"
    response = serves_as_deployed(store, recorder_bucket).test_client().get(link)
    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("attachment")
    assert response.data.startswith(b"fLaC")


@then("it is byte-identical to what the recorder uploaded")
def _(store, recorder_bucket, detail_page):
    recording = store.lists(Recording)[0]
    link = reads_field_link(detail_page, "source-download")
    response = serves_as_deployed(store, recorder_bucket).test_client().get(link)
    assert response.data == recorder_bucket.payload(recording.object_key)


@given(parsers.parse('two Segments from the same Recording are "{state}"'))
def _(store, segment, state):
    from dataclasses import replace

    other = store.saves(
        replace(
            segment,
            segment_id=None,
            classification="lesson",
            label="TEC",
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )
    store.saves(
        Artifact(
            recording_id=other.recording_id,
            segment_id=other.segment_id,
            kind="rendered_mp3",
            path=layout.published_path("2026-08-23 - TEC.mp3"),
            size_bytes=8,
            checksum="stub",
        )
    )


@then("each Segment offers its own MP3 download")
def _(store, detail_page):
    assert len(reads_rows(detail_page, "segment")) >= 1


@then("the filenames differ")
def _(store, segment):
    artifacts = store.lists(Artifact, recording_id=segment.recording_id, kind="rendered_mp3")
    names = {item.path for item in artifacts}
    assert len(names) >= 1


@given("I am using a phone", target_fixture="device")
def _():
    return _browser.PHONE


@when("I download the MP3")
def _(store, segment):
    artifacts = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
    store._downloaded = (
        creates_app(store=store).test_client().get(f"/api/artifacts/{artifacts[0].path}")
    )


@then("the download completes without the page timing out")
def _(store):
    assert store._downloaded.status_code == 200


@given(
    parsers.parse(
        'a Segment in state "{state}" with punch-in "{punch_in}" and punch-out "{punch_out}"'
    ),
    target_fixture="segment",
)
def _(store, state, punch_in, punch_out):
    from sermon.extends_segment_span import ReadsTimecode

    reads = ReadsTimecode()
    started = datetime(2026, 8, 23, 10, 29, tzinfo=UTC)
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_102900",
            object_key="recordings/recording_20260823_102900.flac",
            state="reviewed",
            started_at=started,
            started_at_source="key",
            size_bytes=1,
        )
    )
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state=state,
            span_start_seconds=reads(punch_in),
            span_end_seconds=reads(punch_out),
            punch_in_seconds=reads(punch_in),
            punch_out_seconds=reads(punch_out),
            publication_date=date(2026, 8, 23),
            label="Hebrews 12.4-11",
        )
    )


@then("the file is streamed")
def _(store, recorder_bucket):
    recording = store.lists(Recording)[0]
    described = describes_streaming(store, recorder_bucket, source_path(store))
    assert described["passthrough"] is True
    assert described["content_length"] == recorder_bucket.objects[recording.object_key].size_bytes


@then("the application does not load the whole file into memory")
def _(store, recorder_bucket):
    recording = store.lists(Recording)[0]
    described = describes_streaming(store, recorder_bucket, source_path(store))
    assert described["buffered"] is False
    assert described["read_before_sending"] == []
    assert described["read_for_first_chunk"] == [CHUNK_BYTES]
    assert described["first_chunk"] < recorder_bucket.objects[recording.object_key].size_bytes


@given(parsers.parse("a download was interrupted at {megabytes:d} MB"))
def _(store, recorder_bucket, megabytes):
    recording = store.lists(Recording)[0]
    whole = b"fLaC" + bytes(range(256)) * 16384
    recorder_bucket.holds(recording.object_key, whole)
    store._interrupted_at = min(megabytes * 1024 * 1024, len(whole) // 2)


@when("my browser resumes it")
def _(store, recorder_bucket):
    store._resumed = downloads_as_deployed(
        store,
        recorder_bucket,
        source_path(store),
        headers={"Range": f"bytes={store._interrupted_at}-"},
    )


@then("the download continues from where it stopped")
def _(store, recorder_bucket):
    whole = recorder_bucket.payload(store.lists(Recording)[0].object_key)
    offset = store._interrupted_at
    assert store._resumed.status_code == 206
    assert store._resumed.headers["Content-Range"] == (
        f"bytes {offset}-{len(whole) - 1}/{len(whole)}"
    )
    assert store._resumed.data == whole[offset:]


@given("the rendered MP3 file cannot be found")
def _(store, segment):
    for artifact in store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3"):
        store.resolves(artifact).unlink(missing_ok=True)


@then("I am told the artifact is unavailable")
def _(store):
    assert store._download_error.status_code == 404
    assert store._download_error.get_json()["error"] == ARTIFACT_UNAVAILABLE


@then("I am offered the option to re-process the Segment")
def _(store, segment):
    offered = store._download_error.get_json()
    assert offered["offered"] == REPROCESS_OFFER
    assert offered["segment_id"] == segment.segment_id


@then("it is streamed from the object store without being kept")
def _(store, recorder_bucket):
    recording = store.lists(Recording)[0]
    assert recorder_bucket.asked == [{"Bucket": BUCKET, "Key": recording.object_key}]
    assert not store.resolves(recording).exists()
    assert not store.resolves_path(layout.source_path(recording)).exists()


@then("the download still succeeds")
def _(store, recorder_bucket):
    recording = store.lists(Recording)[0]
    assert store._downloaded.status_code == 200
    assert store._downloaded.data == recorder_bucket.payload(recording.object_key)
