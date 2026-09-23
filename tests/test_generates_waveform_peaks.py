import base64
import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.jobs.generates_waveform_peaks import (
    DETAIL_HZ,
    FULL_SCALE,
    OVERVIEW_BINS,
    GeneratesWaveformPeaks,
)
from sermon.store import Recording, opens_store

FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
TONE_SECONDS = 12.0
TONE_AMPLITUDE = 0.5
TONE_RATE = 8000


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def writes_tone(store, recording, *, seconds=TONE_SECONDS, amplitude=TONE_AMPLITUDE):
    local_path = f"{recording.recording_id}/source.flac"
    destination = store.resolves(replace(recording, local_path=local_path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi",
            "-i", f"aevalsrc={amplitude}*sin(2*PI*440*t):s={TONE_RATE}:d={seconds}",
            "-c:a", "flac", str(destination),
        ],
        check=True,
    )
    return store.saves(replace(recording, local_path=local_path, duration_seconds=seconds))


def signed(encoded):
    return [value - 256 if value > 127 else value for value in base64.b64decode(encoded)]


@pytest.fixture
def recording(store):
    return store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key="recordings/recording_20260823_103015.flac",
            state="downloaded",
            started_at=FROZEN,
            started_at_source="key",
            size_bytes=1,
            duration_seconds=5412.0,
        )
    )


def test_the_peaks_are_measured_from_the_source_audio(store, recording):
    sounding = writes_tone(store, recording)
    artifact = GeneratesWaveformPeaks(store=store, clock=lambda: FROZEN)(sounding)
    payload = json.loads(store.resolves(artifact).read_text())
    assert payload["measured"] is True
    assert abs(payload["duration_seconds"] - TONE_SECONDS) < 0.5
    detail = payload["resolutions"]["detail"]
    assert detail["hz"] == DETAIL_HZ
    assert detail["bins"] == round(TONE_SECONDS * DETAIL_HZ)
    assert len(signed(detail["min"])) == detail["bins"]


def test_the_peaks_carry_the_amplitude_of_the_source_unnormalized(store, recording):
    sounding = writes_tone(store, recording)
    artifact = GeneratesWaveformPeaks(store=store, clock=lambda: FROZEN)(sounding)
    payload = json.loads(store.resolves(artifact).read_text())
    highs = signed(payload["resolutions"]["detail"]["max"])
    assert payload["normalized"] is False
    assert abs(max(highs) / FULL_SCALE - TONE_AMPLITUDE) < 0.03


def test_the_overview_covers_the_whole_recording_more_coarsely(store, recording):
    sounding = writes_tone(store, recording, seconds=300.0)
    artifact = GeneratesWaveformPeaks(store=store, clock=lambda: FROZEN)(sounding)
    payload = json.loads(store.resolves(artifact).read_text())
    overview = payload["resolutions"]["overview"]
    detail = payload["resolutions"]["detail"]
    assert overview["bins"] == OVERVIEW_BINS
    assert overview["bins"] < detail["bins"]
    assert abs(overview["bins"] * overview["seconds_per_bin"] - 300.0) < 0.5
    assert artifact.size_bytes == store.resolves(artifact).stat().st_size
    assert artifact.size_bytes < 2_000_000


def test_a_recording_with_no_local_source_gets_no_measured_peaks(store, recording):
    artifact = GeneratesWaveformPeaks(store=store, clock=lambda: FROZEN)(recording)
    payload = json.loads(store.resolves(artifact).read_text())
    assert payload["measured"] is False
    assert payload["resolutions"] == {}
