from __future__ import annotations

import os
import urllib.error
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

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

HTTP_SCHEMES = ("http", "https")


class MissingConfiguration(ValueError):
    pass


class UnusableConfiguration(ValueError):
    pass


class ModelEndpointUnreachable(ConnectionError):
    def __init__(self, endpoint):
        super().__init__(f"the model endpoint {endpoint} did not answer")
        self.endpoint = endpoint


class Credential:
    __slots__ = ("_value",)

    def __init__(self, value):
        self._value = value

    def reveals(self):
        return self._value

    def __repr__(self):
        return f"{type(self).__name__}(redacted)"

    __str__ = __repr__

    def __eq__(self, other):
        return type(other) is type(self) and other.reveals() == self._value

    def __hash__(self):
        return hash((type(self), self._value))


def refuses_a_non_http_endpoint(name, endpoint):
    reached = urlparse(endpoint)
    if reached.scheme not in HTTP_SCHEMES or not reached.netloc:
        raise UnusableConfiguration(f"{name} is {endpoint!r}, which is not an HTTP endpoint")


def refuses_a_bare_credential(name, credential):
    if not isinstance(credential, Credential):
        raise UnusableConfiguration(f"{name} is a {type(credential).__name__}, not a Credential")


@dataclass(frozen=True)
class ObjectStore:
    endpoint: str
    bucket: str
    access_key_id: Credential
    secret_access_key: Credential

    def __post_init__(self):
        refuses_a_non_http_endpoint(OBJECT_STORE_ENDPOINT, self.endpoint)
        refuses_a_bare_credential(OBJECT_STORE_ACCESS_KEY_ID, self.access_key_id)
        refuses_a_bare_credential(OBJECT_STORE_SECRET_ACCESS_KEY, self.secret_access_key)


@dataclass(frozen=True)
class Configuration:
    data_root: Path
    object_store: ObjectStore
    model_endpoint: str

    def __post_init__(self):
        if not isinstance(self.data_root, Path):
            raise UnusableConfiguration(
                f"{DATA_ROOT} is a {type(self.data_root).__name__}, not a Path"
            )
        if not self.data_root.is_absolute():
            raise UnusableConfiguration(
                f"{DATA_ROOT} is {str(self.data_root)!r}, which moves with the working directory"
            )
        refuses_a_non_http_endpoint(MODEL_ENDPOINT, self.model_endpoint)


@dataclass(frozen=True)
class ReadsConfiguration:
    environment: Mapping[str, str] = field(default_factory=lambda: os.environ)

    def __call__(self):
        unset = [name for name in VARIABLES if not self.environment.get(name)]
        if unset:
            raise MissingConfiguration(f"nothing sets {', '.join(unset)}")
        return Configuration(
            data_root=Path(self.environment[DATA_ROOT]),
            object_store=ObjectStore(
                endpoint=self.environment[OBJECT_STORE_ENDPOINT],
                bucket=self.environment[OBJECT_STORE_BUCKET],
                access_key_id=Credential(self.environment[OBJECT_STORE_ACCESS_KEY_ID]),
                secret_access_key=Credential(self.environment[OBJECT_STORE_SECRET_ACCESS_KEY]),
            ),
            model_endpoint=self.environment[MODEL_ENDPOINT],
        )


@dataclass(frozen=True)
class ReachesModelEndpoint:
    endpoint: str
    over: Callable[[str], object]

    def __post_init__(self):
        refuses_a_non_http_endpoint(MODEL_ENDPOINT, self.endpoint)

    def __call__(self):
        try:
            return self.over(self.endpoint)
        except urllib.error.HTTPError:
            raise
        except OSError as unanswered:
            raise ModelEndpointUnreachable(self.endpoint) from unanswered
