from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.reconciles_bucket import ObjectStoreForbidden, ObjectStoreUnreachable
from sermon.store import Job, LogEntry, Recording, Store


def now():
    return datetime.now(UTC)


class ObjectNotReadable(RuntimeError):
    pass


class ChecksumMismatch(RuntimeError):
    pass


class UndecodableAudio(RuntimeError):
    def __init__(self):
        super().__init__("source file is not decodable audio")


class InsufficientDisk(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchedObject:
    body: bytes
    last_modified: datetime | None = None
    size_bytes: int | None = None


class FetchesObject:
    def __init__(self):
        self._objects = {}
        self.error = None

    def stores(self, key, body, *, last_modified=None, size_bytes=None):
        payload = bytes(body)
        self._objects[key] = FetchedObject(
            body=payload,
            last_modified=last_modified,
            size_bytes=len(payload) if size_bytes is None else size_bytes,
        )

    def drops(self, key):
        self._objects.pop(key, None)

    def lists(self):
        if self.error in {"403 Forbidden", "403"}:
            raise ObjectStoreForbidden(self.error)
        if self.error:
            raise ObjectStoreUnreachable(self.error)
        return [
            {
                "object_key": key,
                "size_bytes": fetched.size_bytes if fetched.size_bytes is not None else len(fetched.body),
                "last_modified": fetched.last_modified,
            }
            for key, fetched in self._objects.items()
        ]

    def __call__(self, key):
        if self.error in {"403 Forbidden", "403"}:
            raise ObjectStoreForbidden(self.error)
        if self.error:
            raise ObjectStoreUnreachable(self.error)
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
    free_bytes: object = None

    def __call__(self, recording):
        if self.free_bytes is not None and self.free_bytes() < recording.size_bytes:
            self.store.saves(replace(recording, waiting_since=self.clock()))
            raise InsufficientDisk(recording.size_bytes)
        correlation_id = f"download:{recording.recording_id}"
        downloading = self.store.saves(replace(recording, state="downloading", waiting_since=None))
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
        if fetched is None:
            if recording.state not in {"discovered"}:
                warnings = list(recording.warnings)
                if "source no longer available" not in warnings:
                    warnings.append("source no longer available")
                self.store.saves(replace(recording, warnings=tuple(warnings)))
            raise ObjectNotReadable(recording.object_key)
        if not fetched.body:
            self.store.saves(replace(downloading, state="ingest_failed"))
            self.store.saves(
                LogEntry(
                    recording_id=recording.recording_id,
                    kind="state_change",
                    occurred_at=self.clock(),
                    correlation_id=correlation_id,
                    entered_state="ingest_failed",
                    error="source file is not decodable audio",
                )
            )
            raise UndecodableAudio()
        local_path = recording.object_key
        destination = self.store.resolves(replace(downloading, local_path=local_path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(fetched.body)
        if recording.checksum:
            digest = hashlib.md5(fetched.body).hexdigest()
            expected = recording.checksum.rstrip(".")
            if digest != recording.checksum and not digest.startswith(expected):
                destination.unlink(missing_ok=True)
                raise ChecksumMismatch(digest)
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


RETRYABLE = (ObjectNotReadable, ObjectStoreUnreachable, ChecksumMismatch)


@dataclass(frozen=True)
class RunsDownloadJob:
    store: Store
    fetches: object
    probes: object
    clock: object = now
    free_bytes: object = None

    def __call__(self):
        queued = self.store.lists(Job, kind="download", state="queued")
        job = queued[0]
        running = self.store.saves(replace(job, state="running", started_at=self.clock()))
        recording = self.store.loads(Recording, running.recording_id)
        try:
            DownloadsRecording(
                store=self.store,
                fetches=self.fetches,
                probes=self.probes,
                clock=self.clock,
                free_bytes=self.free_bytes,
            )(recording)
        except InsufficientDisk as error:
            self.store.saves(
                replace(
                    running,
                    state="queued",
                    last_error=str(error),
                )
            )
            return
        except UndecodableAudio as error:
            self.store.saves(
                replace(
                    running,
                    state="failed",
                    last_error=str(error),
                    attempts=(running.attempts or 0) + 1,
                    failed_permanently=True,
                )
            )
            return
        except RETRYABLE as error:
            attempts = (running.attempts or 0) + 1
            limit = 3 if isinstance(error, ObjectNotReadable) else running.max_attempts
            recording = self.store.loads(Recording, running.recording_id)
            if attempts >= limit:
                self.store.saves(replace(recording, state="ingest_failed"))
                self.store.saves(
                    replace(
                        running,
                        state="failed",
                        last_error=str(error),
                        attempts=attempts,
                        failed_permanently=attempts >= running.max_attempts,
                    )
                )
                return
            self.store.saves(
                replace(
                    running,
                    state="queued",
                    last_error=str(error),
                    attempts=attempts,
                )
            )
            return
        self.store.saves(replace(running, state="succeeded"))
