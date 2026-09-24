from datetime import UTC, date, datetime

from pytest_bdd import given, parsers, then, when

from sermon.store import Artifact, Recording, Segment
from sermon.web import ARTIFACT_UNAVAILABLE, REPROCESS_OFFER, creates_app
from steps._markup import reads_field, reads_links, reads_rows


def serves(store, path, headers=None):
    app = creates_app(store=store)
    with app.test_request_context(f"/api/artifacts/{path}", headers=headers or {}):
        return app.view_functions["artifact_download"](path)


def describes_streaming(store, path):
    response = serves(store, path)
    described = {
        "passthrough": response.direct_passthrough,
        "wrapper": type(response.response).__name__,
        "buffered": isinstance(response.response, (bytes, bytearray, list, tuple)),
        "content_length": int(response.headers["Content-Length"]),
    }
    response.close()
    return described


def source_path(store):
    recording = store.lists(Recording)[0]
    return recording.local_path or recording.object_key


@given(
    parsers.parse('a Segment in state "{state}" from a Recording dated "{day}"'),
    target_fixture="segment",
)
def _(store, state, day):
    started = datetime.strptime(day, "%Y-%m-%d").replace(hour=10, minute=29, tzinfo=UTC)
    recording_id = started.strftime("recording_%Y%m%d_%H%M%S")
    object_key = f"recordings/{recording_id}.flac"
    recording = store.saves(
        Recording(
            recording_id=recording_id,
            object_key=object_key,
            state="reviewed",
            started_at=started,
            started_at_source="key",
            size_bytes=14,
            duration_seconds=2592.0,
            local_path=object_key,
        )
    )
    flac = store.resolves(recording)
    flac.parent.mkdir(parents=True, exist_ok=True)
    flac.write_bytes(b"fLaC" + bytes(10))
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
    path = f"{day} - Hebrews 12.4-11.mp3"
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
    assert artifacts[0].path == filename


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
def _(store):
    recording = store.lists(Recording)[0]
    response = creates_app(store=store).test_client().get(f"/api/artifacts/{recording.local_path}")
    assert response.status_code == 200
    assert response.data.startswith(b"fLaC")


@then("it is byte-identical to what the recorder uploaded")
def _(store):
    recording = store.lists(Recording)[0]
    response = creates_app(store=store).test_client().get(f"/api/artifacts/{recording.local_path}")
    assert response.data == store.resolves(recording).read_bytes()


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
            path="2026-08-23 - TEC.mp3",
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


@given("I am using a phone")
def _():
    return None


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
    parsers.parse('an approved Segment with punch-in "{punch_in}" and punch-out "{punch_out}"'),
    target_fixture="segment",
)
def _(store, punch_in, punch_out):
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
            duration_seconds=11520.0,
        )
    )
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="approved",
            span_start_seconds=reads(punch_in),
            span_end_seconds=reads(punch_out),
            punch_in_seconds=reads(punch_in),
            punch_out_seconds=reads(punch_out),
            publication_date=date(2026, 8, 23),
            label="Hebrews 12.4-11",
        )
    )


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
def _(store):
    recording = store.lists(Recording)[0]
    described = describes_streaming(store, source_path(store))
    assert described["passthrough"] is True
    assert described["content_length"] == store.resolves(recording).stat().st_size


@then("the application does not load the whole file into memory")
def _(store):
    described = describes_streaming(store, source_path(store))
    assert described["buffered"] is False
    assert described["wrapper"] == "FileWrapper"


@given(parsers.parse("a download was interrupted at {megabytes:d} MB"))
def _(store, megabytes):
    recording = store.lists(Recording)[0]
    whole = store.resolves(recording)
    whole.write_bytes(b"fLaC" + bytes(range(256)) * 16384)
    store._interrupted_at = min(megabytes * 1024 * 1024, whole.stat().st_size // 2)


@when("my browser resumes it")
def _(store):
    store._resumed = creates_app(store=store).test_client().get(
        f"/api/artifacts/{source_path(store)}",
        headers={"Range": f"bytes={store._interrupted_at}-"},
    )


@then("the download continues from where it stopped")
def _(store):
    whole = store.resolves(store.lists(Recording)[0]).read_bytes()
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


@then("it is fetched from the object store")
def _(store):
    recording = store.lists(Recording)[0]
    assert store._objects.destinations
    assert store.loads(Recording, recording.recording_id).local_path == recording.object_key


@then("the download still succeeds")
def _(store):
    assert store._downloaded.status_code == 200
    assert store._downloaded.data.startswith(b"fLaC")
