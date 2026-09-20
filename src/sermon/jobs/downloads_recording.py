from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.store import Job, Recording, Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class FetchedObject:
    body: bytes
    last_modified: datetime | None = None


class FetchesObject:
    def __init__(self):
        self._objects = {}

    def stores(self, key, body, *, last_modified=None):
        self._objects[key] = FetchedObject(body=bytes(body), last_modified=last_modified)

    def drops(self, key):
        self._objects.pop(key, None)

    def __call__(self, key):
        return self._objects.get(key)


@dataclass(frozen=True)
class ProbesAudio:
    duration_seconds: float
    sample_rate: int
    channels: int

    def __call__(self, path):
        return self


@dataclass(frozen=True)
class DownloadsRecording:
    store: Store
    fetches: object
    probes: object
    clock: object = now

    def __call__(self, recording):
        return recording


@dataclass(frozen=True)
class RunsDownloadJob:
    store: Store
    fetches: object
    probes: object
    clock: object = now

    def __call__(self):
        job = self.store.lists(Job, kind="download", state="queued")[0]
        recording = self.store.loads(Recording, job.recording_id)
        DownloadsRecording(
            store=self.store,
            fetches=self.fetches,
            probes=self.probes,
            clock=self.clock,
        )(recording)
