from datetime import UTC, datetime

import pytest

from sermon.jobs.generates_waveform_peaks import GeneratesWaveformPeaks
from sermon.store import Recording, opens_store

FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def test_peak_file_covers_the_recording_duration(store):
    recording = store.saves(
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
    artifact = GeneratesWaveformPeaks(store=store, clock=lambda: FROZEN)(recording)
    path = store.resolves(artifact)
    assert path.is_file()
    assert artifact.size_bytes == path.stat().st_size
    assert artifact.size_bytes < 2_000_000
    peaks = [float(value) for value in artifact.checksum.split(",") if value]
    assert len(peaks) >= 8
