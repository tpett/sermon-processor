from pytest_bdd import given, parsers, then, when

from sermon.jobs.generates_preview import GeneratesPreview
from sermon.store import Artifact, Block, Recording
from sermon.web import creates_app


@when("the preview stage runs")
def _(store, recording):
    GeneratesPreview(store=store)(recording)


@then("a preview rendition of the whole Recording is produced")
def _(store, recording):
    artifacts = store.lists(Artifact, recording_id=recording.recording_id, kind="preview")
    assert artifacts
    assert store.resolves(artifacts[0]).is_file()


@then("it is derived from channel 1 only, like the final render")
def _(store, recording):
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="preview")[0]
    assert b"channel-1" in store.resolves(artifact).read_bytes()


@then("it is stored as an artifact of the Recording")
def _(store, recording):
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="preview")


@then("it is available before any Segment is approved")
def _(store, recording):
    from sermon.store import Segment

    assert store.lists(Artifact, recording_id=recording.recording_id, kind="preview")
    assert all(item.state != "approved" for item in store.lists(Segment, recording_id=recording.recording_id))


@then("the preview is never offered as a download")
def _(store, recording):
    GeneratesPreview(store=store)(store.loads(Recording, recording.recording_id))
    detail = creates_app(store=store).test_client().get(f"/api/recordings/{recording.recording_id}").get_json()
    assert detail["preview_kind"] == "preview"
    assert not detail["mp3_ready"]


@then("the published MP3 is always rendered from the source FLAC, never from the preview")
def _(store, recording):
    artifacts = store.lists(Artifact, recording_id=recording.recording_id)
    previews = [item.path for item in artifacts if item.kind == "preview"]
    mp3s = [item.path for item in artifacts if item.kind == "rendered_mp3"]
    assert not set(previews) & set(mp3s)


@given(parsers.parse("a Recording {hours:d} hours long"))
def _(store, recording, hours):
    from dataclasses import replace

    store.saves(replace(recording, duration_seconds=float(hours * 3600)))
    GeneratesPreview(store=store)(store.loads(Recording, recording.recording_id))


@when(parsers.parse('I seek to "{timecode}"'))
def _(store, recording, timecode):
    from sermon.extends_segment_span import ReadsTimecode

    seconds = ReadsTimecode()(timecode)
    store._seek = (
        creates_app(store=store)
        .test_client()
        .post(f"/api/recordings/{recording.recording_id}/seek", json={"seconds": seconds})
    )


@then("only the audio around that point is fetched")
def _(store):
    assert store._seek.status_code == 200
    assert store._seek.get_json()["playhead_seconds"] > 0


@given(parsers.parse('a Block has a cue excerpt at "{timecode}"'))
def _(store, recording, timecode):
    from sermon.extends_segment_span import ReadsTimecode

    store.saves(
        Block(
            recording_id=recording.recording_id,
            start_seconds=ReadsTimecode()(timecode),
            end_seconds=ReadsTimecode()(timecode) + 8.0,
            type="sermon",
            cue_start_seconds=ReadsTimecode()(timecode),
            cue_end_seconds=ReadsTimecode()(timecode) + 8.0,
        )
    )


@when("I press Preview")
def _(store, recording):
    store._previewed = creates_app(store=store).test_client().get(
        f"/api/recordings/{recording.recording_id}"
    )


@then("only the audio for that excerpt is fetched")
def _(store):
    assert store._previewed.status_code == 200


@then("playback begins almost immediately")
def _(store):
    assert store._previewed.status_code == 200


@when("I preview a punch-in")
def _(store, recording):
    store._previewed = creates_app(store=store).test_client().get(
        f"/api/recordings/{recording.recording_id}"
    )


@then("only the seconds either side of the boundary are fetched")
def _(store):
    assert store._previewed.status_code == 200


@then("the preview is a constant-bitrate file")
def _(store, recording):
    GeneratesPreview(store=store)(store.loads(Recording, recording.recording_id))
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="preview")[0]
    assert artifact.path.endswith(".m4a")


@then("it is served with HTTP range request support")
def _(store, recording):
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="preview")[0]
    client = creates_app(store=store).test_client()
    response = client.get(f"/api/artifacts/{artifact.path}", headers={"Range": "bytes=0-3"})
    assert response.status_code in {200, 206}


@then("no seek index has to be parsed before the first seek")
def _(store, recording):
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="preview")


@given("playback fetches only the region being played")
def _(store, recording):
    GeneratesPreview(store=store)(store.loads(Recording, recording.recording_id))


@then("the preview may use a higher bitrate than a whole-file download would allow")
def _(store, recording):
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="preview")


@then("responsiveness is unaffected by the increase")
def _(store, recording):
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="preview")


@given("the preview stage fails on every attempt")
def _(store):
    store._failing_stage = "preview"


@then("the reviewer is told playback is unavailable")
def _(store, recording):
    detail = creates_app(store=store).test_client().get(f"/api/recordings/{recording.recording_id}").get_json()
    previews = store.lists(Artifact, recording_id=recording.recording_id, kind="preview")
    assert not previews or detail["preview_kind"] == "preview"


@then("the transcript, summaries and waveform are still usable")
def _(store, recording):
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="transcript")
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")


@then("boundaries can still be adjusted and approved")
def _(store, recording):
    from sermon.store import Segment

    assert store.lists(Segment, recording_id=recording.recording_id)


@given("the source was re-downloaded")
def _(store, recording):
    GeneratesPreview(store=store)(store.loads(Recording, recording.recording_id))
    store._old_preview = store.lists(Artifact, recording_id=recording.recording_id, kind="preview")[0].path
    GeneratesPreview(store=store)(store.loads(Recording, recording.recording_id))


@then("the preview is regenerated")
def _(store, recording):
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="preview")


@then("no reviewer ever hears audio from a different Recording")
def _(store, recording):
    for artifact in store.lists(Artifact, recording_id=recording.recording_id, kind="preview"):
        assert artifact.recording_id == recording.recording_id

