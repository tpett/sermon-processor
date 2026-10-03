"""Source and edit envelopes the alignment reads as if it had decoded them.

The alignment itself -- locating, fitting, gating, grading -- is the shipped code;
only the decode and the duration probe are stood in for, through the seams the
alignment command already takes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from sermon.analysis.aligns_edit import COARSE_HZ, FINE_HZ
from sermon.config import (
    DATA_ROOT,
    MODEL_ENDPOINT,
    OBJECT_STORE_ACCESS_KEY_ID,
    OBJECT_STORE_BUCKET,
    OBJECT_STORE_ENDPOINT,
    OBJECT_STORE_SECRET_ACCESS_KEY,
)
from sermon.store import Recording

PER_COARSE_FRAME = FINE_HZ // COARSE_HZ
SYLLABLE_MS = 25
NOWHERE = "http://127.0.0.1:9"


def speech(seconds, seed=7):
    """Smooth on a syllable, as a real envelope is; white noise decorrelates under drift."""
    generator = np.random.default_rng(seed)
    loud = generator.gamma(2.0, 0.3, size=int(seconds * FINE_HZ) + SYLLABLE_MS)
    smoothed = np.convolve(loud, np.ones(SYLLABLE_MS) / SYLLABLE_MS, mode="valid")
    return smoothed[: int(seconds * FINE_HZ)].astype(np.float32) + 0.01


def coarsened(fine):
    frames = len(fine) // PER_COARSE_FRAME
    return fine[: frames * PER_COARSE_FRAME].reshape(frames, PER_COARSE_FRAME).mean(axis=1)


def excerpt(source, start_seconds, length_seconds, stretch_ppm=0.0):
    wanted = np.arange(int(length_seconds * FINE_HZ)) * (1 + stretch_ppm / 1e6)
    return np.interp(start_seconds * FINE_HZ + wanted, np.arange(len(source)), source).astype(np.float32)


@dataclass
class Pair:
    """One source and the edit a human made from it, and where the edit really came from."""

    recording_id: str
    source_seconds: float
    offset_seconds: float
    edit_seconds: float
    classification: str = "sermon"
    gain: float = 1.0
    stretch_ppm: float = 0.0
    spliced_at: float | None = None
    unrelated: bool = False
    seed: int = 7

    @property
    def source_name(self):
        return f"{self.recording_id}.flac"

    @property
    def edit_name(self):
        return f"{self.recording_id}.edit.mp3"

    def source_fine(self):
        return speech(self.source_seconds, seed=self.seed)

    def edit_fine(self):
        source = self.source_fine()
        if self.unrelated:
            return speech(self.edit_seconds, seed=self.seed + 92)
        if self.spliced_at is not None:
            head = excerpt(source, self.offset_seconds, self.spliced_at)
            tail = excerpt(source, self.offset_seconds + self.spliced_at + 3.0, self.edit_seconds - self.spliced_at)
            return np.concatenate([head, tail]) * self.gain
        return excerpt(source, self.offset_seconds, self.edit_seconds, self.stretch_ppm) * self.gain


@dataclass
class Corpus:
    root: Path
    pairs: dict = field(default_factory=dict)
    printed: list = field(default_factory=list)
    exits: dict = field(default_factory=dict)

    def reads(self, path, tag):
        for pair in self.pairs.values():
            if Path(path).name == pair.source_name:
                fine = pair.source_fine()
                return coarsened(fine), fine
            if Path(path).name == pair.edit_name:
                fine = pair.edit_fine()
                return coarsened(fine), fine
        raise FileNotFoundError(path)

    def measures(self, path):
        for pair in self.pairs.values():
            if Path(path).name == pair.source_name:
                return pair.source_seconds
            if Path(path).name == pair.edit_name:
                return pair.edit_seconds
        raise FileNotFoundError(path)


def settings_for(root):
    return {
        DATA_ROOT: str(root),
        OBJECT_STORE_ENDPOINT: NOWHERE,
        OBJECT_STORE_BUCKET: "unused",
        OBJECT_STORE_ACCESS_KEY_ID: "unused",
        OBJECT_STORE_SECRET_ACCESS_KEY: "unused",
        MODEL_ENDPOINT: NOWHERE,
    }


def registers(store, pair):
    return store.saves(
        Recording(
            recording_id=pair.recording_id,
            object_key=f"recordings/{pair.recording_id}.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=pair.source_seconds,
        )
    )


def lays_down(corpus, pair):
    sources = corpus.root / "desktop"
    sources.mkdir(parents=True, exist_ok=True)
    (sources / pair.source_name).write_bytes(b"\0")
    (sources / pair.edit_name).write_bytes(b"\0")
    return sources / pair.source_name, sources / pair.edit_name
