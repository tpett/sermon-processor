from pytest_bdd import given, then, when

from sermon.jobs.generates_waveform_peaks import DETAIL_HZ, FULL_SCALE, GeneratesWaveformPeaks
from sermon.store import Artifact, Recording, Segment
from sermon.web import creates_app
from steps._peaks import TONE_AMPLITUDE, reads_peaks, signed, writes_tone

PLACEABLE_HZ = 10
STAGE_ARTIFACTS = ("waveform_peaks", "preview")
UNMEASURED = "No waveform has been generated"


@when("the waveform stage runs")
def _(store, recording):
    GeneratesWaveformPeaks(store=store)(writes_tone(store, recording))


@then("a peak file is produced for the Recording")
def _(store, recording):
    artifacts = store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")
    assert artifacts
    assert store.resolves(artifacts[0]).is_file()


@then("it contains min/max pairs at a fixed resolution")
def _(store, recording):
    detail = reads_peaks(store, recording)["resolutions"]["detail"]
    assert detail["bins"] > 8
    assert len(signed(detail["min"])) == detail["bins"]
    assert len(signed(detail["max"])) == detail["bins"]
    assert detail["seconds_per_bin"] == 1.0 / DETAIL_HZ


@then("it is small enough to load in the browser in under 2 seconds on a normal connection")
def _(store, recording):
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")[0]
    assert artifact.size_bytes == store.resolves(artifact).stat().st_size
    assert artifact.size_bytes < 2_000_000


@then("it is stored as an artifact of the Recording")
def _(store, recording):
    produced = [
        one
        for one in store.lists(Artifact, recording_id=recording.recording_id)
        if one.kind in STAGE_ARTIFACTS
    ]
    assert produced
    assert all(store.resolves(one).is_file() for one in produced)


@then("peak data is available at an overview resolution covering the whole recording")
def _(store, recording):
    overview = reads_peaks(store, recording)["resolutions"]["overview"]
    covered = overview["bins"] * overview["seconds_per_bin"]
    assert abs(covered - (recording.duration_seconds or 0.0)) < 1.0


@then("at a detail resolution suitable for placing a boundary within 100 ms")
def _(store, recording):
    detail = reads_peaks(store, recording)["resolutions"]["detail"]
    assert detail["hz"] >= PLACEABLE_HZ
    assert detail["seconds_per_bin"] <= 0.1


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
    page = (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{recording.recording_id}")
        .get_data(as_text=True)
    )
    assert UNMEASURED in page


@then("the reviewer can still adjust Segment boundaries using playback and the transcript")
def _(store, recording):
    assert store.lists(Segment, recording_id=recording.recording_id)


@then("the peaks span the full duration of the source recording")
def _(store, recording):
    payload = reads_peaks(store, recording)
    assert abs(payload["duration_seconds"] - (recording.duration_seconds or 0.0)) < 1.0


@then("no normalization has been applied to the peak data")
def _(store, recording):
    payload = reads_peaks(store, recording)
    loudest = max(signed(payload["resolutions"]["detail"]["max"]))
    assert payload["normalized"] is False
    assert abs(loudest / FULL_SCALE - TONE_AMPLITUDE) < 0.03
