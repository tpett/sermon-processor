from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.object_store import FetchedObject
from sermon.reconciles_bucket import ObjectStoreForbidden, ObjectStoreUnreachable
from sermon.jobs.probes_recording import AudioNotMeasurable
from sermon.store import Job, LogEntry, Recording, Store


def now():
    return datetime.now(UTC)


class ObjectNotReadable(RuntimeError):
    pass


class ChecksumMismatch(RuntimeError):
    pass


class ObjectTruncated(ChecksumMismatch):
    def __init__(self, written, announced):
        super().__init__(f"{written} of the {announced} bytes the store announced")


class UndecodableAudio(RuntimeError):
    def __init__(self):
        super().__init__("source file is not decodable audio")


class InsufficientDisk(RuntimeError):
    pass


@dataclass(frozen=True)
class HeldObject:
    body: bytes
    last_modified: datetime | None = None
    announced_bytes: int | None = None
    entity_tag: str | None = None


class FetchesObject:
    def __init__(self):
        self._objects = {}
        self.error = None
        self.destinations = []
        self.fetched = []

    def stores(self, key, body, *, last_modified=None, size_bytes=None, entity_tag=None):
        payload = bytes(body)
        self._objects[key] = HeldObject(
            body=payload,
            last_modified=last_modified,
            announced_bytes=len(payload) if size_bytes is None else size_bytes,
            entity_tag=hashlib.md5(payload).hexdigest() if entity_tag is None else entity_tag,
        )

    def drops(self, key):
        self._objects.pop(key, None)

    def holds(self, key):
        held = self._objects.get(key)
        return None if held is None else held.body

    def _refuses(self):
        if self.error in {"403 Forbidden", "403"}:
            raise ObjectStoreForbidden(self.error)
        if self.error:
            raise ObjectStoreUnreachable(self.error)

    def lists(self):
        self._refuses()
        return [
            {
                "object_key": key,
                "size_bytes": held.announced_bytes,
                "last_modified": held.last_modified,
            }
            for key, held in self._objects.items()
        ]

    def __call__(self, key, destination):
        self._refuses()
        held = self._objects.get(key)
        if held is None:
            return None
        self.destinations.append(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(held.body)
        fetched = FetchedObject(
            size_bytes=len(held.body),
            announced_bytes=held.announced_bytes,
            checksum=hashlib.md5(held.body).hexdigest(),
            entity_tag=held.entity_tag,
            last_modified=held.last_modified,
        )
        self.fetched.append(fetched)
        return fetched


def refuses_a_partial_transfer(fetched, destination):
    if fetched.announced_bytes is None or fetched.size_bytes == fetched.announced_bytes:
        return
    destination.unlink(missing_ok=True)
    raise ObjectTruncated(fetched.size_bytes, fetched.announced_bytes)


def refuses_a_digest_the_store_disowns(fetched, destination):
    if fetched.entity_tag is None or fetched.entity_tag == fetched.checksum:
        return
    destination.unlink(missing_ok=True)
    raise ChecksumMismatch(fetched.checksum)


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
        local_path = recording.object_key
        destination = self.store.resolves(replace(downloading, local_path=local_path))
        fetched = self.fetches(recording.object_key, destination)
        if fetched is None:
            if recording.state not in {"discovered"}:
                warnings = list(recording.warnings)
                if "source no longer available" not in warnings:
                    warnings.append("source no longer available")
                self.store.saves(replace(recording, warnings=tuple(warnings)))
            raise ObjectNotReadable(recording.object_key)
        if not fetched.size_bytes:
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
        refuses_a_partial_transfer(fetched, destination)
        refuses_a_digest_the_store_disowns(fetched, destination)
        if recording.checksum:
            expected = recording.checksum.rstrip(".")
            if fetched.checksum != recording.checksum and not fetched.checksum.startswith(expected):
                destination.unlink(missing_ok=True)
                raise ChecksumMismatch(fetched.checksum)
        started_at = datetime.strptime(
            Path(recording.object_key).stem, "recording_%Y%m%d_%H%M%S"
        ).replace(tzinfo=UTC)
        sidecar_path = destination.with_name(f"{destination.name}.meta.json")
        sidecar = self.fetches(f"{recording.object_key}.meta.json", sidecar_path)
        if sidecar is None:
            sidecar_present = False
            try:
                probed = self.probes(destination)
            except AudioNotMeasurable:
                # A file ffprobe cannot measure is not decodable audio, whatever
                # left it that way -- a truncated transfer reads exactly like a
                # corrupt source. Keeping it would fail the same way on every
                # retry.
                destination.unlink(missing_ok=True)
                raise UndecodableAudio from None
            duration_seconds = probed.duration_seconds
            sample_rate = probed.sample_rate
            channels = probed.channels
        else:
            sidecar_present = True
            metadata = json.loads(sidecar_path.read_text(encoding="utf-8"))
            duration_seconds = float(metadata["duration"])
            sample_rate = int(metadata["sample_rate"])
            channels = int(metadata["channels"])
        downloaded = self.store.saves(
            replace(
                downloading,
                state="downloaded",
                local_path=local_path,
                checksum=fetched.checksum,
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
