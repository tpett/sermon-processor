from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import numpy as np

from sermon.pipeline.render import probe_format
from sermon.store import Artifact, Store

OVERVIEW_BINS = 1100
DETAIL_HZ = 20.0
FULL_SCALE = 127
INT16_PER_STEP = 32767 / FULL_SCALE
CHUNK_BINS = 4096
CHANNEL_ONE = "pan=mono|c0=c0"


def now():
    return datetime.now(UTC)


class PeaksNotMeasurable(RuntimeError):
    pass


@dataclass(frozen=True)
class Resolution:
    bins: int
    seconds_per_bin: float
    lows: np.ndarray
    highs: np.ndarray

    @property
    def seconds(self):
        return self.bins * self.seconds_per_bin

    def sent(self):
        return {
            "bins": self.bins,
            "seconds_per_bin": self.seconds_per_bin,
            "hz": round(1.0 / self.seconds_per_bin, 6),
            "min": encodes(self.lows),
            "max": encodes(self.highs),
        }


def encodes(values):
    return base64.b64encode(values.astype(np.int8).tobytes()).decode()


def quantizes(lows, highs):
    floors = np.clip(np.floor(lows / INT16_PER_STEP), -FULL_SCALE, FULL_SCALE)
    ceilings = np.clip(np.ceil(highs / INT16_PER_STEP), -FULL_SCALE, FULL_SCALE)
    return floors.astype(np.int8), ceilings.astype(np.int8)


def folds(resolution, bins):
    if resolution.bins <= bins:
        return resolution
    edges = np.linspace(0, resolution.bins, bins + 1).astype(int)
    return Resolution(
        bins=bins,
        seconds_per_bin=resolution.seconds / bins,
        lows=np.minimum.reduceat(resolution.lows, edges[:-1]),
        highs=np.maximum.reduceat(resolution.highs, edges[:-1]),
    )


@dataclass(frozen=True)
class MeasuresAudioPeaks:
    detail_hz: float = DETAIL_HZ

    def __call__(self, path):
        probed = probe_format(path)
        rate = int(probed.get("sr") or 0)
        if not rate:
            raise PeaksNotMeasurable(str(path))
        per_bin = max(round(rate / self.detail_hz), 1)
        lows, highs = self._bins(path, per_bin)
        if not lows:
            raise PeaksNotMeasurable(str(path))
        floors, ceilings = quantizes(np.concatenate(lows), np.concatenate(highs))
        return Resolution(
            bins=len(floors),
            seconds_per_bin=per_bin / rate,
            lows=floors,
            highs=ceilings,
        )

    def _bins(self, path, per_bin):
        decoding = subprocess.Popen(
            [
                "ffmpeg", "-v", "error", "-nostdin", "-i", str(path),
                "-af", CHANNEL_ONE, "-ac", "1", "-f", "s16le", "-",
            ],
            stdout=subprocess.PIPE,
        )
        lows, highs = [], []
        carried = b""
        with decoding.stdout as stream:
            while True:
                block = stream.read(per_bin * 2 * CHUNK_BINS)
                if not block:
                    break
                samples = np.frombuffer(carried + block, dtype="<i2")
                whole = (len(samples) // per_bin) * per_bin
                carried = samples[whole:].tobytes()
                if whole:
                    shaped = samples[:whole].reshape(-1, per_bin)
                    lows.append(shaped.min(axis=1))
                    highs.append(shaped.max(axis=1))
        if decoding.wait() != 0:
            raise PeaksNotMeasurable(str(path))
        remainder = np.frombuffer(carried, dtype="<i2")
        if remainder.size:
            lows.append(remainder.min(keepdims=True))
            highs.append(remainder.max(keepdims=True))
        return lows, highs


@dataclass(frozen=True)
class GeneratesWaveformPeaks:
    store: Store
    clock: object = now
    measures: object = MeasuresAudioPeaks()

    def __call__(self, recording):
        artifact = Artifact(
            recording_id=recording.recording_id,
            kind="waveform_peaks",
            path=f"{recording.recording_id}/waveform_peaks.json",
            size_bytes=0,
            checksum="",
        )
        body = json.dumps(self._payload(recording), sort_keys=True).encode()
        destination = self.store.resolves(artifact)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        return self.store.saves(
            replace(
                artifact,
                size_bytes=len(body),
                checksum=hashlib.md5(body).hexdigest(),
            )
        )

    def _payload(self, recording):
        payload = {
            "recording_id": recording.recording_id,
            "duration_seconds": recording.duration_seconds or 0.0,
            "full_scale": FULL_SCALE,
            "normalized": False,
            "measured": False,
            "resolutions": {},
        }
        detail = self._measured(recording)
        if detail is None:
            return payload
        return payload | {
            "measured": True,
            "duration_seconds": detail.seconds,
            "resolutions": {
                "overview": folds(detail, OVERVIEW_BINS).sent(),
                "detail": detail.sent(),
            },
        }

    def _measured(self, recording):
        source = self.store.resolves(recording)
        if source is None or not source.is_file():
            return None
        try:
            return self.measures(source)
        except (PeaksNotMeasurable, OSError, ValueError):
            return None
