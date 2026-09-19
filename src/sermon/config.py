from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

DATA_ROOT = "SERMON_DATA_ROOT"
OBJECT_STORE_ENDPOINT = "SERMON_OBJECT_STORE_ENDPOINT"
OBJECT_STORE_BUCKET = "SERMON_OBJECT_STORE_BUCKET"
OBJECT_STORE_ACCESS_KEY_ID = "SERMON_OBJECT_STORE_ACCESS_KEY_ID"
OBJECT_STORE_SECRET_ACCESS_KEY = "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY"
MODEL_ENDPOINT = "SERMON_MODEL_ENDPOINT"

VARIABLES = (
    DATA_ROOT,
    OBJECT_STORE_ENDPOINT,
    OBJECT_STORE_BUCKET,
    OBJECT_STORE_ACCESS_KEY_ID,
    OBJECT_STORE_SECRET_ACCESS_KEY,
    MODEL_ENDPOINT,
)


class MissingConfiguration(ValueError):
    pass


class UnusableConfiguration(ValueError):
    pass


class ModelEndpointUnreachable(ConnectionError):
    pass


class Credential:
    def __init__(self, value):
        self.value = value

    def reveals(self):
        return self.value


@dataclass(frozen=True)
class ObjectStore:
    endpoint: str
    bucket: str
    access_key_id: Credential
    secret_access_key: Credential


@dataclass(frozen=True)
class Configuration:
    data_root: Path
    object_store: ObjectStore
    model_endpoint: str


@dataclass(frozen=True)
class ReadsConfiguration:
    environment: Mapping[str, str] = field(default_factory=lambda: os.environ)

    def __call__(self):
        return Configuration(
            data_root=Path(self.environment.get(DATA_ROOT, "data")),
            object_store=ObjectStore(
                endpoint=self.environment.get(OBJECT_STORE_ENDPOINT, ""),
                bucket=self.environment.get(OBJECT_STORE_BUCKET, ""),
                access_key_id=Credential(self.environment.get(OBJECT_STORE_ACCESS_KEY_ID, "")),
                secret_access_key=Credential(
                    self.environment.get(OBJECT_STORE_SECRET_ACCESS_KEY, "")
                ),
            ),
            model_endpoint=self.environment.get(MODEL_ENDPOINT, ""),
        )


@dataclass(frozen=True)
class ReachesModelEndpoint:
    endpoint: str
    over: Callable[[str], object]

    def __call__(self):
        return self.over(self.endpoint)
