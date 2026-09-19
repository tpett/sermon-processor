from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCHEMA = "extraction-baseline/1"


class BaselineUnusable(Exception):
    pass


@dataclass(frozen=True)
class Finding:
    scope: str
    kind: str
    detail: str

    def __str__(self):
        return f"{self.scope}: {self.kind}: {self.detail}"


@dataclass(frozen=True)
class CapturesBaseline:
    data_root: Path

    def __call__(self):
        return {}


@dataclass(frozen=True)
class ComparesBaseline:
    baseline: dict
    data_root: Path

    def __call__(self):
        return []


def reads_baseline(path):
    return {}


def main(argv=None):
    return 0
