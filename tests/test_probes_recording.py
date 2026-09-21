import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from sermon.jobs.probes_recording import (
    SILENT_RMS_DB,
    AudioNotMeasurable,
    MeasuresRecordingAudio,
    ProbesRecording,
)
from sermon.store import Recording, opens_store

SAMPLE_RATE = 44100
SECONDS = 4.0
OBJECT_KEY = "recordings/recording_20260823_103015.flac"
QUIET = 0.02


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def speech_like(seconds, amplitude, seed=11):
    generator = np.random.default_rng(seed)
    samples = int(seconds * SAMPLE_RATE)
    noise = generator.standard_normal(samples).astype(np.float32)
    smoothed = np.convolve(noise, np.ones(24, dtype=np.float32) / 24, mode="same")
    spoken = np.ones(samples, dtype=np.float32)
    silence = int(0.4 * SAMPLE_RATE)
    for start in range(0, samples, SAMPLE_RATE):
        spoken[start:start + silence] = 0.0
    return smoothed * spoken * amplitude / max(float(np.abs(smoothed).max()), 1e-9)


def writes_flac(path, channels):
    frames = np.stack(channels, axis=1)
    raw = path.with_suffix(".raw")
    raw.write_bytes((frames * (2 ** 31 - 1)).astype(np.int32).tobytes())
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "s32le", "-ar", str(SAMPLE_RATE),
         "-ac", str(len(channels)), "-i", str(raw),
         "-c:a", "flac", "-sample_fmt", "s32", str(path)],
        check=True,
    )
    raw.unlink()
    return path


def one_live_channel(root):
    silent = np.zeros(int(SECONDS * SAMPLE_RATE), dtype=np.float32)
    return writes_flac(root / OBJECT_KEY, [speech_like(SECONDS, 0.5), silent])


def two_live_channels(root):
    return writes_flac(
        root / OBJECT_KEY,
        [speech_like(SECONDS, 0.5), speech_like(SECONDS, 0.4, seed=12)],
    )


def downloaded(store, tmp_path, writes=one_live_channel):
    (tmp_path / OBJECT_KEY).parent.mkdir(parents=True, exist_ok=True)
    writes(tmp_path)
    return store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key=OBJECT_KEY,
            state="downloaded",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=(tmp_path / OBJECT_KEY).stat().st_size,
            local_path=OBJECT_KEY,
        )
    )


def measures(store):
    return MeasuresRecordingAudio(resolves=store.resolves)


def test_the_probe_reads_the_duration_of_the_file_on_disk(store, tmp_path):
    measured = measures(store)(downloaded(store, tmp_path))
    assert measured.duration_seconds == pytest.approx(SECONDS, abs=0.05)


def test_the_probe_reads_the_sample_rate_and_channel_count(store, tmp_path):
    measured = measures(store)(downloaded(store, tmp_path))
    assert (measured.sample_rate, measured.channels) == (SAMPLE_RATE, 2)


def test_the_probe_reports_a_level_for_every_channel(store, tmp_path):
    measured = measures(store)(downloaded(store, tmp_path))
    assert [level.channel for level in measured.channel_levels] == [1, 2]


def test_the_probe_separates_the_channel_carrying_signal_from_the_silent_one(store, tmp_path):
    measured = measures(store)(downloaded(store, tmp_path))
    carrying, silent = measured.channel_levels
    assert carrying.rms_db > SILENT_RMS_DB
    assert silent.rms_db <= SILENT_RMS_DB


def test_the_probe_reports_a_level_above_the_silence_floor_for_both_live_channels(store, tmp_path):
    measured = measures(store)(downloaded(store, tmp_path, writes=two_live_channels))
    assert [level.rms_db > SILENT_RMS_DB for level in measured.channel_levels] == [True, True]


def test_the_probe_measures_the_loudness_of_the_source(store, tmp_path):
    measured = measures(store)(downloaded(store, tmp_path))
    assert -60.0 < measured.integrated_loudness_lufs < 0.0


def test_the_probe_measures_the_true_peak_and_the_loudness_range(store, tmp_path):
    measured = measures(store)(downloaded(store, tmp_path))
    assert measured.true_peak_dbtp < 0.0
    assert measured.loudness_range_lu > 0.0


def test_a_file_that_is_not_decodable_audio_is_refused_loudly(store, tmp_path):
    recording = downloaded(store, tmp_path)
    store.resolves(recording).write_bytes(b"not audio at all")
    with pytest.raises(AudioNotMeasurable):
        measures(store)(recording)


def test_a_probe_of_a_recording_with_no_local_file_is_refused_loudly(store, tmp_path):
    recording = downloaded(store, tmp_path)
    store.resolves(recording).unlink()
    with pytest.raises(AudioNotMeasurable):
        measures(store)(recording)


def test_probing_replaces_the_duration_the_detail_page_had_nothing_to_show(store, tmp_path):
    recording = downloaded(store, tmp_path)
    assert store.loads(Recording, recording.recording_id).duration_seconds is None
    ProbesRecording(store=store, measures=measures(store))(recording)
    stored = store.loads(Recording, recording.recording_id)
    assert stored.duration_seconds == pytest.approx(SECONDS, abs=0.05)


def test_probing_names_the_one_channel_that_carries_signal(store, tmp_path):
    recording = downloaded(store, tmp_path)
    ProbesRecording(store=store, measures=measures(store))(recording)
    assert store.loads(Recording, recording.recording_id).mono_source == "channel 1"


def test_probing_warns_when_both_channels_carry_signal(store, tmp_path):
    recording = downloaded(store, tmp_path, writes=two_live_channels)
    ProbesRecording(store=store, measures=measures(store))(recording)
    stored = store.loads(Recording, recording.recording_id)
    assert "unexpected stereo content" in stored.warnings
    assert stored.mono_source is None


def test_probing_records_what_a_render_normalizes_from(store, tmp_path):
    recording = downloaded(store, tmp_path)
    ProbesRecording(store=store, measures=measures(store))(recording)
    stored = store.loads(Recording, recording.recording_id)
    assert stored.integrated_loudness_lufs is not None
    assert stored.true_peak_dbtp is not None
    assert stored.loudness_range_lu is not None
    assert [level.channel for level in stored.channel_levels] == [1, 2]
