from __future__ import annotations

from dataclasses import dataclass

from sermon.config import Configuration
from sermon.pipeline import classify


@dataclass(frozen=True)
class BindsModelEndpoint:
    configuration: Configuration

    def __call__(self):
        classify.ENDPOINT = self.configuration.model_endpoint
