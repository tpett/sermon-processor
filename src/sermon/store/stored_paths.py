from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_ROOT = Path("data")


class PathEscapesDataRoot(ValueError):
    pass


@dataclass(frozen=True)
class ResolvesStoredPath:
    data_root: Path = DEFAULT_DATA_ROOT

    def __call__(self, path):
        relative = Path(os.path.normpath(path))
        if Path(path).is_absolute() or relative == Path(".") or relative.parts[0] == "..":
            raise PathEscapesDataRoot(path)
        resolved = self.data_root / relative
        if not resolved.resolve().is_relative_to(self.data_root.resolve()):
            raise PathEscapesDataRoot(path)
        return resolved
