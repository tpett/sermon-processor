from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

COARSE_HZ = 100
FINE_HZ = 1_000

ALIGNED = "aligned"
UNALIGNABLE = "cannot be aligned"
DISCONTINUOUS = "not a contiguous excerpt"

EASY = "easy"
MODERATE = "moderate"
HARD = "hard"


@dataclass(frozen=True, kw_only=True)
class Probe:
    at_seconds: float
    offset_seconds: float
    ncc: float
    peak_ratio: float | None


@dataclass(frozen=True, kw_only=True)
class Alignment:
    verdict: str
    refusals: tuple[str, ...] = ()
    probes: tuple[Probe, ...] = ()
    punch_in_seconds: float | None = None
    coarse_offset_seconds: float | None = None
    coarse_ncc: float | None = None
    coarse_peak_ratio: float | None = None
    drift_ppm: float | None = None
    fit_residual_seconds: float | None = None
    probe_spread_seconds: float | None = None
    probe_ncc_min: float | None = None

    @property
    def trustworthy(self) -> bool:
        return self.verdict == ALIGNED


@dataclass(frozen=True, kw_only=True)
class CutDifficulty:
    label: str
    quiet_milliseconds: int


@dataclass(frozen=True)
class ReadsEnvelopes:
    work: Path
    coarse_hz: int = COARSE_HZ
    fine_hz: int = FINE_HZ

    def __call__(self, source: Path, tag: str) -> tuple[np.ndarray, np.ndarray]:
        return np.empty(0, dtype=np.float32), np.empty(0, dtype=np.float32)


@dataclass(frozen=True)
class GradesCutDifficulty:
    hz: int = COARSE_HZ

    def __call__(self, source_coarse, at_seconds) -> CutDifficulty:
        return CutDifficulty(label=HARD, quiet_milliseconds=0)


@dataclass(frozen=True)
class LocatesEditInSource:
    coarse_hz: int = COARSE_HZ
    fine_hz: int = FINE_HZ

    def __call__(self, *, source_coarse, source_fine, edit_coarse, edit_fine) -> Alignment:
        return Alignment(verdict=UNALIGNABLE)
