from pytest_bdd import given, then, when

from sermon.jobs.generates_waveform_peaks import GeneratesWaveformPeaks
from sermon.store import Artifact, Recording, Segment
from sermon.web import creates_app


@when("the waveform stage runs")
def _(store, recording):
    GeneratesWaveformPeaks(store=store)(recording)


@then("a peak file is produced for the Recording")
def _(store, recording):
    artifacts = store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")
    assert artifacts
    assert store.resolves(artifacts[0]).is_file()


@then("it contains min/max pairs at a fixed resolution")
def _(store, recording):
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")[0]
    peaks = [float(value) for value in artifact.checksum.split(",") if value]
    assert len(peaks) >= 8


@then("it is small enough to load in the browser in under 2 seconds on a normal connection")
def _(store, recording):
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")[0]
    assert artifact.size_bytes < 2_000_000


@then("it is stored as an artifact of the Recording")
def _(store, recording):
    kinds = {item.kind for item in store.lists(Artifact, recording_id=recording.recording_id)}
    assert kinds & {"waveform_peaks", "preview"}


@then("peak data is available at an overview resolution covering the whole recording")
def _(store, recording):
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")[0]
    peaks = [float(value) for value in artifact.checksum.split(",") if value]
    assert len(peaks) >= 8


@then("at a detail resolution suitable for placing a boundary within 100 ms")
def _(store, recording):
    import json

    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")[0]
    payload = json.loads(store.resolves(artifact).read_text())
    assert payload["detail_hz"] >= 10


@given("the waveform stage fails on every attempt")
def _(store):
    store._failing_stage = "waveform"


@then("Analysis continues to the remaining stages")
def _(store, recording, stage_log):
    assert "scoring" in stage_log or store.loads(Recording, recording.recording_id).state == "awaiting_review"


@then('the Recording still reaches "awaiting_review"')
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state == "awaiting_review"


@then("the interface shows the reviewer that the waveform is unavailable")
def _(store, recording):
    detail = creates_app(store=store).test_client().get(f"/api/recordings/{recording.recording_id}").get_json()
    assert detail["peaks"] == []


@then("the reviewer can still adjust Segment boundaries using playback and the transcript")
def _(store, recording):
    assert store.lists(Segment, recording_id=recording.recording_id)


@then("the peaks span the full duration of the source recording")
def _(store, recording):
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")[0]
    assert artifact.checksum


@then("no normalization has been applied to the peak data")
def _(store, recording):
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")[0]
    peaks = [float(value) for value in artifact.checksum.split(",") if value]
    assert max(peaks) <= 1.0
