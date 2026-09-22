from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BoundaryError:
    recording_id: str


@dataclass(frozen=True)
class MeasuresBoundaryError:
    ground_truth: Path

    def __call__(self, recording_id, proposed):
        raise NotImplementedError
