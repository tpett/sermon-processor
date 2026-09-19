from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_ROOT = Path("data")


class PathEscapesDataRoot(ValueError):
    pass


@dataclass(frozen=True)
class ResolvesArtifactPath:
    data_root: Path = DEFAULT_DATA_ROOT

    def __call__(self, path):
        return Path(path)
