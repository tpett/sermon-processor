import time

from pytest_bdd import given, parsers, then, when

from sermon.analysis.io import reads_json
from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.generates_preview import GeneratesPreview
from sermon.pipeline import preview as rendition
from sermon.pipeline.render import probe_format
from sermon.shows_recording import PREVIEW_LEAD_SECONDS
from sermon.store import Artifact, Block, Recording, Segment, layout
from sermon.web import creates_app
from steps import _audio, _forms, _web
from steps._markup import reads_field, reads_role, reads_rows

READS = ReadsTimecode()
LONG_SECONDS = 3 * 3600.0
LEVEL_TOLERANCE_DB = 2.0
CBR_TOLERANCE = 0.02
STARTS_WITHIN_SECONDS = 2.0
FRAME_SYNC = 0xE0


def only_preview(store, recording_id):
    return store.lists(Artifact, recording_id=recording_id, kind="preview")


def fetches_range(store, path, first, last):
    client = creates_app(store=store).test_client()
    began = time.monotonic()
    response = client.get(f"/api/artifacts/{path}", headers={"Range": f"bytes={first}-{last}"})
    return response, time.monotonic() - began


@when("the preview stage runs")
def _(store, recording):
    GeneratesPreview(store=store)(_audio.local_source(store, recording))


@then("a preview rendition of the whole Recording is produced")
def _(store, recording):
    artifacts = only_preview(store, recording.recording_id)
    assert artifacts
    rendered = store.resolves(artifacts[0])
    assert rendered.is_file()
    settled = artifacts[0].render_settings or {}
    assert abs(settled["duration_seconds"] - _audio.SHORT_SECONDS) < 0.2


@then("it is derived from channel 1 only, like the final render")
def _(store, recording):
    artifact = only_preview(store, recording.recording_id)[0]
    rendered = store.resolves(artifact)
    source = store.resolves(store.loads(Recording, recording.recording_id))
    assert (artifact.render_settings or {}).get("source_channel") == 1
    assert probe_format(rendered)["channels"] == 1
    channel_one = _audio.mean_volume_db(source, ["pan=mono|c0=c0"])
    assert abs(_audio.mean_volume_db(rendered) - channel_one) < LEVEL_TOLERANCE_DB


@then("it is stored as an artifact of the Recording")
def _(store, recording):
    assert only_preview(store, recording.recording_id)


@then("it is available before any Segment is approved")
def _(store, recording):
    from sermon.store import Segment

    assert only_preview(store, recording.recording_id)
    assert all(
        item.state != "approved" for item in store.lists(Segment, recording_id=recording.recording_id)
    )


@then("the preview is never offered as a download")
def _(store, recording):
    artifact = only_preview(store, recording.recording_id)[0]
    served = creates_app(store=store).test_client().get(f"/api/artifacts/{artifact.path}")
    assert served.status_code == 200
    assert "attachment" not in served.headers.get("Content-Disposition", "")
    assert served.headers["Content-Type"].startswith(rendition.MEDIA_TYPE)


@then("the published MP3 is always rendered from the source FLAC, never from the preview")
def _(store, recording):
    artifacts = store.lists(Artifact, recording_id=recording.recording_id)
    previews = [item.path for item in artifacts if item.kind == "preview"]
    mp3s = [item.path for item in artifacts if item.kind == "rendered_mp3"]
    assert not set(previews) & set(mp3s)


@given(parsers.parse("a Recording {hours:d} hours long"))
def _(store, recording, hours):
    seconds = float(hours * 3600)
    source = _audio.local_source(store, recording, seconds)
    GeneratesPreview(store=store, encodes=_audio.cached_encoder(seconds))(source)


@when(parsers.parse('I seek to "{timecode}"'))
def _(store, recording, timecode):
    seconds = READS(timecode)
    client = creates_app(store=store).test_client()
    store._seek = client.post(
        f"/api/recordings/{recording.recording_id}/seek", json={"seconds": seconds}
    )
    artifact = only_preview(store, recording.recording_id)[0]
    first, last = rendition.byte_range(seconds, PREVIEW_LEAD_SECONDS * 2, artifact.size_bytes)
    store._wanted_range = (first, last)
    store._whole_preview_bytes = artifact.size_bytes
    store._ranged, store._ranged_seconds = fetches_range(store, artifact.path, first, last)


@then("only the audio around that point is fetched")
def _(store):
    first, last = store._wanted_range
    assert store._seek.status_code == 200
    assert store._ranged.status_code == 206
    assert store._ranged.headers["Content-Range"] == (
        f"bytes {first}-{last}/{store._whole_preview_bytes}"
    )


@then("playback begins within 2 seconds")
def _(store):
    assert store._ranged.status_code == 206
    assert store._ranged_seconds < STARTS_WITHIN_SECONDS


@then("the earlier part of the recording is never downloaded")
def _(store):
    first, last = store._wanted_range
    assert first > 0
    assert len(store._ranged.data) == last - first + 1
    assert len(store._ranged.data) < first


@given(parsers.parse('a Block has a cue excerpt at "{timecode}"'))
def _(store, recording, timecode):
    at = READS(timecode)
    source = _audio.local_source(store, recording, LONG_SECONDS)
    GeneratesPreview(store=store, encodes=_audio.cached_encoder(LONG_SECONDS))(source)
    store.saves(
        Block(
            recording_id=recording.recording_id,
            start_seconds=at,
            end_seconds=at + 8.0,
            type="sermon",
            cue_start_seconds=at,
            cue_end_seconds=at + 8.0,
        )
    )


@when("I press Preview")
def _(store, recording):
    page = creates_app(store=store).test_client().get(
        f"/recordings/{recording.recording_id}"
    ).get_data(as_text=True)
    control = reads_role(page, "preview-cue-excerpt")
    artifact = only_preview(store, recording.recording_id)[0]
    first, last = rendition.byte_range(
        float(control["start"]),
        float(control["end"]) - float(control["start"]),
        artifact.size_bytes,
    )
    store._wanted_range = (first, last)
    store._whole_preview_bytes = artifact.size_bytes
    store._ranged, store._ranged_seconds = fetches_range(store, artifact.path, first, last)


@then("only the audio for that excerpt is fetched")
def _(store, recording):
    excerpt = store.lists(Block, recording_id=recording.recording_id)[0]
    first, last = store._wanted_range
    assert store._ranged.status_code == 206
    assert first == rendition.byte_offset(excerpt.cue_start_seconds, store._whole_preview_bytes)
    assert len(store._ranged.data) == last - first + 1


@then("playback begins almost immediately")
def _(store):
    assert store._ranged.status_code == 206
    assert store._ranged_seconds < STARTS_WITHIN_SECONDS


@when("I preview a punch-in")
def _(store, recording):
    source = _audio.local_source(store, recording)
    GeneratesPreview(store=store)(source)
    boundary = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=0.0,
            span_end_seconds=_audio.SHORT_SECONDS,
            punch_in_seconds=_audio.SHORT_SECONDS / 2,
            punch_out_seconds=_audio.SHORT_SECONDS,
        )
    )
    page = creates_app(store=store).test_client().get(
        f"/recordings/{recording.recording_id}?segment={boundary.segment_id}"
    ).get_data(as_text=True)
    control = reads_role(page, "preview-punch-in")
    store._audition = (float(control["start"]), float(control["end"]), boundary.punch_in_seconds)
    artifact = only_preview(store, recording.recording_id)[0]
    first, last = rendition.byte_range(
        store._audition[0], store._audition[1] - store._audition[0], artifact.size_bytes
    )
    store._wanted_range = (first, last)
    store._whole_preview_bytes = artifact.size_bytes
    store._ranged, store._ranged_seconds = fetches_range(store, artifact.path, first, last)


@then("only the seconds either side of the boundary are fetched")
def _(store):
    start, end, at = store._audition
    first, last = store._wanted_range
    assert (start, end) == (max(0.0, at - PREVIEW_LEAD_SECONDS), min(_audio.SHORT_SECONDS, at + PREVIEW_LEAD_SECONDS))
    assert store._ranged.status_code == 206
    assert len(store._ranged.data) == last - first + 1
    assert len(store._ranged.data) < store._whole_preview_bytes


@then("the preview is a constant-bitrate file")
def _(store, recording):
    artifact = only_preview(store, recording.recording_id)[0]
    settled = artifact.render_settings or {}
    assert artifact.path.endswith(rendition.SUFFIX)
    assert abs(settled["measured_kbps"] - rendition.KBPS) <= 1
    expected = settled["duration_seconds"] * rendition.BYTES_PER_SECOND
    assert abs(artifact.size_bytes - expected) / expected < CBR_TOLERANCE


@then("it is served with HTTP range request support")
def _(store, recording):
    artifact = only_preview(store, recording.recording_id)[0]
    response, _ = fetches_range(store, artifact.path, 0, 3)
    assert response.status_code == 206
    assert response.headers["Accept-Ranges"] == "bytes"
    assert response.headers["Content-Range"] == f"bytes 0-3/{artifact.size_bytes}"


@then("no seek index has to be parsed before the first seek")
def _(store, recording):
    artifact = only_preview(store, recording.recording_id)[0]
    first, last = rendition.byte_range(6.0, 1.0, artifact.size_bytes)
    response, _ = fetches_range(store, artifact.path, first, last)
    body = response.data
    assert response.status_code == 206
    syncs = [
        index
        for index in range(len(body) - 1)
        if body[index] == 0xFF and body[index + 1] & FRAME_SYNC == FRAME_SYNC
    ]
    assert syncs and syncs[0] < 1024


@given("playback fetches only the region being played")
def _(store, recording):
    GeneratesPreview(store=store)(_audio.local_source(store, recording))


@then("the preview may use a higher bitrate than a whole-file download would allow")
def _(store, recording):
    artifact = only_preview(store, recording.recording_id)[0]
    settled = artifact.render_settings or {}
    assert settled["bitrate_kbps"] == rendition.KBPS
    assert settled["constant_bitrate"] is True


@then("responsiveness is unaffected by the increase")
def _(store, recording):
    artifact = only_preview(store, recording.recording_id)[0]
    first, last = rendition.byte_range(6.0, 1.0, artifact.size_bytes)
    response, elapsed = fetches_range(store, artifact.path, first, last)
    assert response.status_code == 206
    assert elapsed < STARTS_WITHIN_SECONDS


@given("the preview stage fails on every attempt")
def _(store, recording):
    _audio.local_source(store, recording, recording.duration_seconds)
    store._failing_stage = "preview"


@then("the reviewer is told playback is unavailable")
def _(store, recording):
    page = creates_app(store=store).test_client().get(
        f"/recordings/{recording.recording_id}"
    ).get_data(as_text=True)
    assert not only_preview(store, recording.recording_id)
    assert 'data-field="preview-state"' in page
    assert "has not been rendered" in page


def reviewed_page(store, recording, **query):
    proposed = store.lists(Segment, recording_id=recording.recording_id, state="proposed")
    assert proposed, "analysis proposed no Segment to review"
    return proposed[0], _web.opens_detail(
        store, recording.recording_id, segment=proposed[0].segment_id, **query
    )


@then("the transcript, summaries and waveform are still usable")
def _(store, recording):
    _, page = reviewed_page(store, recording)
    spoken = reads_json(store, recording, "transcript")["utterances"]
    shown = [float(row["utterance-at-seconds"]) for row in reads_rows(page, "recording-utterance")]
    assert shown == [item["start"] for item in spoken], f"{len(shown)} of {len(spoken)} utterances shown"
    summarised = [block.summary or "" for block in sorted(store.lists(Block, recording_id=recording.recording_id), key=lambda one: one.start_seconds)]
    assert any(summarised), "analysis summarised no Block"
    shown = [row["block-summary"] for row in reads_rows(page, "block")]
    assert [" ".join(one.split()) for one in summarised] == shown, shown
    assert reads_field(page, "waveform-state") is None, reads_field(page, "waveform-state")
    assert 'data-role="waveform"' in page


@then("boundaries can still be adjusted and approved")
def _(store, recording):
    segment, page = reviewed_page(store, recording, mode="edit")
    assert [row["boundary"] for row in reads_rows(page, "boundary")] == ["punch-in", "punch-out"]
    _forms.submits(store, page, 'data-nudge="later ')
    moved = store.loads(Segment, segment.segment_id).punch_in_seconds
    assert moved > segment.punch_in_seconds, f"the punch-in stayed at {moved}"
    _, reviewing = reviewed_page(store, recording)
    approved = _forms.submits(store, reviewing, 'data-field="action-control">Approve')
    assert reads_field(approved, "action-notice") == "the Segment is approved and queued for processing"


@given("the source was re-downloaded")
def _(store, recording):
    generates = GeneratesPreview(store=store)
    source = _audio.local_source(store, recording)
    store._old_preview = generates(source)
    _audio.places(_audio.stereo_source(_audio.SHORT_SECONDS / 2), store.resolves(source))
    generates(store.loads(Recording, recording.recording_id))


@then("the preview is regenerated")
def _(store, recording):
    artifacts = only_preview(store, recording.recording_id)
    assert len(artifacts) == 1
    assert artifacts[0].path == store._old_preview.path
    assert artifacts[0].checksum != store._old_preview.checksum


@then("no reviewer ever hears audio from a different Recording")
def _(store, recording, tmp_path):
    page = _web.opens_detail(store, recording.recording_id)
    played = reads_field(page, "audio-source")
    assert played and played.startswith(f"/api/artifacts/{layout.recording_directory(recording.recording_id)}/"), played
    served = creates_app(store=store).test_client().get(played)
    assert served.status_code == 200, served.status_code
    heard = tmp_path / f"heard{rendition.SUFFIX}"
    heard.write_bytes(served.data)
    source = probe_format(store.resolves(store.loads(Recording, recording.recording_id)))["duration"]
    assert abs(probe_format(heard)["duration"] - source) < 0.2, "the preview played is not this source's audio"
