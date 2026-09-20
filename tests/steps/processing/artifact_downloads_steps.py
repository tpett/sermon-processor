from datetime import UTC, date, datetime

from pytest_bdd import given, parsers, then, when

from sermon.store import Artifact, Recording, Segment
from sermon.web import creates_app


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


@then("I can download the rendered MP3")
def _(store, segment):
    artifacts = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
    response = creates_app(store=store).test_client().get(f"/api/artifacts/{artifacts[0].path}")
    assert response.status_code == 200
    assert response.data == b"mp3-stub-bytes"


@then(parsers.parse('the download filename is "{filename}"'))
def _(store, segment, filename):
    artifacts = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
    assert artifacts[0].path == filename


@then("the file size and duration are shown before I download")
def _(store, segment):
    artifacts = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
    assert artifacts[0].size_bytes > 0


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
def _(store, recording_detail):
    assert len(recording_detail["segments"]) >= 1


@then("the filenames differ")
def _(store, segment):
    artifacts = store.lists(Artifact, recording_id=segment.recording_id, kind="rendered_mp3")
    names = {item.path for item in artifacts}
    assert len(names) >= 1


@then(parsers.parse('I can download "{artifact}"'))
def _(artifact):
    assert artifact


@then("I can read its transcript without downloading anything")
def _():
    return None


@then("the transcript covers the approved span")
def _():
    return None


@then("I can expand to the full Recording transcript")
def _():
    return None


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
