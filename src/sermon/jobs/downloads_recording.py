from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.store import Job, LogEntry, Recording, Store


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
        correlation_id = f"download:{recording.recording_id}"
        downloading = self.store.saves(replace(recording, state="downloading"))
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=correlation_id,
                entered_state="downloading",
            )
        )
        fetched = self.fetches(recording.object_key)
        local_path = recording.object_key
        destination = self.store.resolves(replace(downloading, local_path=local_path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(fetched.body)
        started_at = datetime.strptime(
            Path(recording.object_key).stem, "recording_%Y%m%d_%H%M%S"
        ).replace(tzinfo=UTC)
        sidecar = self.fetches(f"{recording.object_key}.meta.json")
        if sidecar is None:
            sidecar_present = False
            probed = self.probes(destination)
            duration_seconds = probed.duration_seconds
            sample_rate = probed.sample_rate
            channels = probed.channels
        else:
            sidecar_present = True
            metadata = json.loads(sidecar.body)
            duration_seconds = float(metadata["duration"])
            sample_rate = int(metadata["sample_rate"])
            channels = int(metadata["channels"])
        downloaded = self.store.saves(
            replace(
                downloading,
                state="downloaded",
                local_path=local_path,
                sidecar_present=sidecar_present,
                duration_seconds=duration_seconds,
                sample_rate=sample_rate,
                channels=channels,
                started_at=started_at,
                started_at_source="key",
            )
        )
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=correlation_id,
                entered_state="downloaded",
            )
        )
        EnqueuesJob(self.store)(
            Job(
                recording_id=recording.recording_id,
                kind="analyze",
                state="queued",
                max_attempts=5,
                dedupe_key=f"analyze:{recording.recording_id}",
                queued_at=self.clock(),
            )
        )
        return downloaded


@dataclass(frozen=True)
class RunsDownloadJob:
    store: Store
    fetches: object
    probes: object
    clock: object = now

    def __call__(self):
        job = self.store.lists(Job, kind="download", state="queued")[0]
        running = self.store.saves(replace(job, state="running", started_at=self.clock()))
        recording = self.store.loads(Recording, running.recording_id)
        DownloadsRecording(
            store=self.store,
            fetches=self.fetches,
            probes=self.probes,
            clock=self.clock,
        )(recording)
        self.store.saves(replace(running, state="succeeded"))
