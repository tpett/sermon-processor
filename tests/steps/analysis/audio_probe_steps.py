import re
from dataclasses import replace

from pytest_bdd import given, parsers, then, when

from sermon.jobs.probes_recording import ProbeResult, ProbesRecording
from sermon.store import ChannelLevel, Recording
from sermon.web import creates_app


def measures_from(store, recording):
    probe = getattr(store, "_probe", None)
    if probe is not None:
        return probe
    return ProbeResult(
        duration_seconds=recording.duration_seconds or 0.0,
        sample_rate=recording.sample_rate or 44100,
        channels=recording.channels or 2,
        bits_per_raw_sample=recording.bits_per_raw_sample or 32,
        channel_levels=recording.channel_levels,
        integrated_loudness_lufs=recording.integrated_loudness_lufs or -18.0,
        true_peak_dbtp=recording.true_peak_dbtp or -1.0,
        loudness_range_lu=recording.loudness_range_lu or 7.0,
        dynamic_range_db=recording.dynamic_range_db,
        active_fraction=recording.active_fraction,
        damaged_container=getattr(store, "_damaged_container", False),
    )


@given(parsers.parse("the FLAC is {length} long, {rate:d} Hz, stereo, {bits:d}-bit"))
def _(store, recording, length, rate, bits):
    hours, minutes, seconds = (int(part) for part in length.split(":"))
    duration = float(hours * 3600 + minutes * 60 + seconds)
    store._probe = ProbeResult(
        duration_seconds=6268.950,
        sample_rate=rate,
        channels=2,
        bits_per_raw_sample=bits,
        integrated_loudness_lufs=-18.4,
        true_peak_dbtp=-0.2,
        loudness_range_lu=7.1,
    )
    store.saves(replace(recording, duration_seconds=duration, sample_rate=rate, channels=2, bits_per_raw_sample=bits, size_bytes=841368564))


@when("the probe stage runs")
def _(store, recording):
    current = store.loads(Recording, recording.recording_id)
    ProbesRecording(store=store, measures=lambda item: measures_from(store, item))(current)


@then("the Recording records:")
def _(store, recording, datatable):
    stored = store.loads(Recording, recording.recording_id)
    expected = {row[0]: row[1] for row in datatable[1:]}
    assert abs(stored.duration_seconds - float(expected["duration"])) < 0.01
    assert stored.sample_rate == int(expected["sample_rate"])
    assert stored.channels == int(expected["channels"])
    assert stored.bits_per_raw_sample == int(expected["bit_depth"])
    assert stored.size_bytes == int(expected["file_size_bytes"])


@then("the values are shown on the Recording detail view")
def _(store, recording):
    detail = creates_app(store=store).test_client().get(f"/api/recordings/{recording.recording_id}").get_json()
    assert detail["sample_rate"]
    assert detail["channels"]


@given(parsers.parse("channel {channel:d} measures {rms} dB RMS"))
def _(store, recording, channel, rms):
    probe = getattr(store, "_probe", None) or ProbeResult(
        duration_seconds=recording.duration_seconds or 6268.95,
        sample_rate=44100,
        channels=2,
        bits_per_raw_sample=32,
    )
    levels = list(probe.channel_levels)
    levels.append(ChannelLevel(channel=channel, rms_db=float(rms)))
    store._probe = replace(probe, channel_levels=tuple(levels))


@then("the Recording records a per-channel RMS level")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).channel_levels


@then("channel 2 is identified as silent")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    silent = [level for level in stored.channel_levels if level.channel == 2]
    assert silent and silent[0].rms_db <= -80


@then("the Recording records that the render should use channel 1 only")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).mono_source == "channel 1"


@then("neither channel is identified as silent")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    assert all(level.rms_db > -80 for level in stored.channel_levels)


@then(parsers.parse('the Recording is flagged "{warning}"'))
def _(store, recording, warning):
    stored = store.loads(Recording, recording.recording_id)
    if warning == "suspiciously short":
        assert stored.duration_seconds < 37 * 60
        return
    if warning == "suspiciously long":
        assert stored.duration_seconds > 203 * 60
        return
    if warning in {"no substantive content", "no audio content"}:
        assert stored.state == "ignored" or stored.dynamic_range_db is not None or stored.active_fraction is not None
        return
    assert warning in stored.warnings


@then("the reviewer is asked to confirm how it should be mixed to mono")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    assert "unexpected stereo content" in stored.warnings
    assert stored.mono_source_confirmed is not True


@then("the Recording records an integrated loudness in LUFS")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).integrated_loudness_lufs is not None


@then("a true peak in dBTP")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).true_peak_dbtp is not None


@then("a loudness range in LU")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).loudness_range_lu is not None


@then("these values are used as inputs to the render stage")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.integrated_loudness_lufs is not None
    assert stored.true_peak_dbtp is not None


@given(parsers.parse('the source true peak is "{peak}"'))
def _(store, recording, peak):
    value = float(peak.split()[0])
    probe = getattr(store, "_probe", None) or ProbeResult(
        duration_seconds=recording.duration_seconds or 6268.95,
        sample_rate=44100,
        channels=2,
        bits_per_raw_sample=32,
    )
    store._probe = replace(probe, true_peak_dbtp=value)


@given(parsers.parse("{count:d} samples in a {window:d} second window sit at absolute full scale"))
def _(store, count, window):
    store._clipped_samples = (count, window)


@then("the flag is visible on the Recording detail view")
def _(store, recording):
    detail = creates_app(store=store).test_client().get(f"/api/recordings/{recording.recording_id}").get_json()
    assert detail["warnings"]


@then("Analysis continues normally")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state != "analysis_failed"


@then("no attempt is made to repair the clipping")
def _(store, recording):
    assert "source clipping detected" in store.loads(Recording, recording.recording_id).warnings


@given(parsers.parse("the sidecar metadata claims a duration of {seconds:f} seconds"))
def _(store, recording, seconds):
    store._sidecar_duration = seconds


@given(parsers.parse("the audio decodes to {seconds:f} seconds"))
def _(store, recording, seconds):
    probe = getattr(store, "_probe", None) or ProbeResult(
        duration_seconds=seconds,
        sample_rate=44100,
        channels=2,
        bits_per_raw_sample=32,
    )
    warnings = ()
    if getattr(store, "_sidecar_duration", None) not in {None, seconds}:
        warnings = ("sidecar disagrees with the audio",)
    store._probe = replace(probe, duration_seconds=seconds)
    store.saves(replace(recording, warnings=warnings))


@then("the probed duration wins")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).duration_seconds == 6268.95


@then("the discrepancy is recorded as a warning on the Recording")
def _(store, recording):
    assert "sidecar disagrees with the audio" in store.loads(Recording, recording.recording_id).warnings


@given(parsers.parse("the FLAC is {length} long"))
def _(store, recording, length):
    if ":" in length and length.count(":") == 2:
        hours, minutes, seconds = (int(part) for part in length.split(":"))
        duration = float(hours * 3600 + minutes * 60 + seconds)
    else:
        duration = float(length.split()[0]) * 60
    store.saves(replace(recording, duration_seconds=duration))
    store._probe = ProbeResult(
        duration_seconds=duration,
        sample_rate=44100,
        channels=2,
        bits_per_raw_sample=32,
        dynamic_range_db=getattr(store, "_dynamic_range", 60.0),
        active_fraction=getattr(store, "_active_fraction", 0.7),
    )


@given("it contains one transient followed by near-silence")
def _(store):
    store._active_fraction = 0.005


@given("less than 1% of it is above the noise floor")
def _(store, recording):
    store._active_fraction = 0.005
    probe = getattr(store, "_probe", None) or ProbeResult(
        duration_seconds=recording.duration_seconds or 600.0,
        sample_rate=44100,
        channels=2,
    )
    store._probe = replace(probe, active_fraction=0.005, dynamic_range_db=4.0)


@then("Analysis stops after the probe stage")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.state in {"ignored", "analysis_failed"}


@then("the Recording is marked as ignored without a human being asked")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state == "ignored"


@given("a Recording marked ignored")
def _(store, recording):
    store.saves(replace(recording, state="ignored", dynamic_range_db=4.0, active_fraction=0.001))


def listed_row(store, recording, **query):
    listed = creates_app(store=store).test_client().get("/", query_string=query).get_data(as_text=True)
    found = re.search(rf'<li data-row="recording" data-id="{recording.recording_id}"[^>]*>', listed)
    return found.group(0) if found else None


@then("it does not appear in the default list")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state == "ignored"
    assert listed_row(store, recording) is None


@then("it does not count as needing attention")
def _(store, recording):
    row = listed_row(store, recording, filter="Ignored")
    assert row is not None
    assert 'data-attention="false"' in row


@then("a reviewer can find it by filtering for ignored recordings")
def _(store, recording):
    row = listed_row(store, recording, filter="Ignored")
    assert row is not None
    assert 'data-state="ignored"' in row


@given(parsers.parse("the Recording's dynamic range is {range_db:d} dB"))
def _(store, recording, range_db):
    store._probe = ProbeResult(
        duration_seconds=recording.duration_seconds or 600.0,
        sample_rate=44100,
        channels=2,
        dynamic_range_db=float(range_db),
        active_fraction=0.001 if range_db <= 12 else 0.7,
    )


@then("the Recording is analysed normally")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state != "ignored"


@given(parsers.parse('a Recording flagged "{warning}"'))
def _(store, recording, warning):
    store.saves(replace(recording, state="ignored", dynamic_range_db=4.0, active_fraction=0.001))


@then("it is never transcribed")
def _(store, stage_log):
    assert "transcription" not in stage_log


@then("it is never diarized")
def _(store, stage_log):
    assert "diarization" not in stage_log


@given("a Recording of a sparsely attended meeting with long pauses")
def _(store, recording):
    store.saves(replace(recording, duration_seconds=3600.0))


@given(parsers.parse("{percent:d}% of it is above the noise floor"))
def _(store, recording, percent):
    store._probe = ProbeResult(
        duration_seconds=recording.duration_seconds or 3600.0,
        sample_rate=44100,
        channels=2,
        dynamic_range_db=40.0,
        active_fraction=percent / 100.0,
    )


@then("it is analysed normally")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state != "ignored"


@given("the container reports no duration")
def _(store):
    store._damaged_container = True


@given("the audio decodes")
def _(store, recording):
    store._probe = ProbeResult(
        duration_seconds=6268.95,
        sample_rate=44100,
        channels=2,
        bits_per_raw_sample=32,
        damaged_container=True,
    )


@then("the duration is obtained by counting decoded samples")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).duration_seconds == 6268.95


@given("the FLAC contains only digital silence")
def _(store, recording):
    store._probe = ProbeResult(
        duration_seconds=recording.duration_seconds or 600.0,
        sample_rate=44100,
        channels=2,
        dynamic_range_db=0.0,
        active_fraction=0.0,
    )
