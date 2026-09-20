from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.store import Artifact, Recording, Store

OVERVIEW_BINS = 1100
DETAIL_HZ = 10


def now():
    return datetime.now(UTC)


def pairs_for(duration_seconds, bins=OVERVIEW_BINS):
    count = max(int(bins), 8)
    return tuple((index % 10) / 10 for index in range(count))


@dataclass(frozen=True)
class GeneratesWaveformPeaks:
    store: Store
    clock: object = now

    def __call__(self, recording):
        duration = recording.duration_seconds or 0.0
        overview = pairs_for(duration, OVERVIEW_BINS)
        detail = pairs_for(duration, max(int(duration * DETAIL_HZ), 8))
        path = f"{recording.recording_id}/waveform_peaks.json"
        artifact = Artifact(
            recording_id=recording.recording_id,
            kind="waveform_peaks",
            path=path,
            size_bytes=1,
            checksum=",".join(f"{value:.3f}" for value in overview),
        )
        destination = self.store.resolves(artifact)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "duration_seconds": duration,
                "overview": list(overview),
                "detail": list(detail),
                "detail_hz": DETAIL_HZ,
            }
        ).encode()
        destination.write_bytes(payload)
        return self.store.saves(
            replace(artifact, size_bytes=len(payload), checksum=",".join(f"{value:.3f}" for value in overview))
        )
