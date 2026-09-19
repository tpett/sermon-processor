from __future__ import annotations

from dataclasses import dataclass

from sermon.config import Configuration


@dataclass(frozen=True)
class BindsModelEndpoint:
    configuration: Configuration

    def __call__(self):
        return None
