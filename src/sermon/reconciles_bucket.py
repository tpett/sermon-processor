from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.store import Discovery, Job, Recording, SkippedObject, Store


def now():
    return datetime.now(UTC)


KEY = re.compile(r"(?:^|.*/)recording_(\d{8})_(\d{6})\.flac$")
SETTLE_SECONDS = 30.0
DEFAULT_CUTOFF = date(2026, 1, 1)


class MalformedObjectKey(ValueError):
    pass


def recorded_at(object_key):
    match = KEY.search(object_key) if isinstance(object_key, str) else None
    if match is None:
        return None
    try:
        return datetime.strptime(
            f"{match.group(1)}_{match.group(2)}", "%Y%m%d_%H%M%S"
        ).replace(tzinfo=UTC)
    except ValueError:
        return None


def skip_reason(object_key, *, ingest_cutoff):
    recorded = recorded_at(object_key)
    if recorded is None:
        if object_key.endswith(".flac"):
            return "key does not match the pattern"
        return "not an audio object"
    if recorded.date() == date(1970, 1, 1):
        return "recorder clock not set"
    if ingest_cutoff is not None and recorded.date() < ingest_cutoff:
        return "before the ingest cutoff"
    return None


def creates_recording(store, object_key, *, size_bytes, clock, queues=True):
    started_at = recorded_at(object_key)
    if started_at is None:
        raise MalformedObjectKey(object_key)
    recording = store.saves(
        Recording(
            recording_id=Path(object_key).stem,
            object_key=object_key,
            state="discovered",
            started_at=started_at,
            started_at_source="key",
            size_bytes=int(size_bytes or 0),
        )
    )
    if not queues:
        return recording
    EnqueuesJob(store)(
        Job(
            recording_id=recording.recording_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{recording.recording_id}",
            queued_at=clock(),
        )
    )
    return recording


@dataclass(frozen=True)
class ReconcilesBucket:
    store: Store
    lists_objects: object
    clock: object = now
    ingest_cutoff: date | None = DEFAULT_CUTOFF
    settle_seconds: float = SETTLE_SECONDS

    def __call__(self):
        try:
            objects = list(self.lists_objects())
        except ObjectStoreForbidden:
            self.store.saves(
                Discovery(
                    kind="scan",
                    occurred_at=self.clock(),
                    discovered_count=0,
                    failure="credentials",
                )
            )
            return
        except (ObjectStoreUnreachable, OSError):
            self.store.saves(
                Discovery(
                    kind="scan",
                    occurred_at=self.clock(),
                    discovered_count=0,
                    failure="transient",
                )
            )
            return
        discovered = 0
        moment = self.clock()
        for item in objects:
            object_key = item["object_key"] if isinstance(item, dict) else item.object_key
            size_bytes = item["size_bytes"] if isinstance(item, dict) else item.size_bytes
            last_modified = (
                item["last_modified"] if isinstance(item, dict) else item.last_modified
            )
            if object_key.endswith(".flac.meta.json"):
                parent_key = object_key[: -len(".meta.json")]
                parents = self.store.lists(Recording, object_key=parent_key)
                if parents:
                    from dataclasses import replace

                    self.store.saves(replace(parents[0], sidecar_present=True))
                else:
                    self.store.saves(
                        SkippedObject(object_key=object_key, reason="not an audio object")
                    )
                continue
            reason = skip_reason(object_key, ingest_cutoff=self.ingest_cutoff)
            if reason:
                self.store.saves(SkippedObject(object_key=object_key, reason=reason))
                continue
            if last_modified is not None:
                age = (moment - last_modified).total_seconds()
                if 0 <= age < self.settle_seconds:
                    continue
            if self.store.lists(Recording, object_key=object_key):
                continue
            creates_recording(
                self.store,
                object_key,
                size_bytes=size_bytes,
                clock=self.clock,
                queues=False,
            )
            discovered += 1
        self.store.saves(
            Discovery(
                kind="scan",
                occurred_at=moment,
                discovered_count=discovered,
            )
        )

    def ingests(self, object_key, *, size_bytes=0):
        if recorded_at(object_key) is None:
            raise MalformedObjectKey(object_key)
        existing = self.store.lists(Recording, object_key=object_key)
        if existing:
            return existing[0]
        return creates_recording(
            self.store, object_key, size_bytes=size_bytes, clock=self.clock
        )


class ObjectStoreUnreachable(OSError):
    pass


class ObjectStoreForbidden(PermissionError):
    pass
