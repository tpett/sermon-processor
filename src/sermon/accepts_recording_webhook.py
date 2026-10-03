from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.reconciles_bucket import recorded_at
from sermon.store import Discovery, Job, Recording, Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class AcceptsRecordingWebhook:
    store: Store
    clock: object = now

    def __call__(self, payload):
        payload = payload or {}
        if not isinstance(payload, dict):
            return 422, {"malformed": "body"}
        required = ("event", "bucket", "object_key", "recorded_at")
        missing = [field for field in required if not payload.get(field)]
        if missing:
            return 422, {"missing": missing[0]}
        if payload.get("event") != "recording.uploaded":
            self.store.saves(
                Discovery(
                    kind="webhook",
                    occurred_at=self.clock(),
                    discovered_count=0,
                    event=payload.get("event"),
                )
            )
            return 202, "ignored"
        object_key = payload["object_key"]
        started_at = recorded_at(object_key)
        if started_at is None:
            return 422, {"malformed": "object_key"}
        try:
            size_bytes = int(payload.get("size_bytes") or 0)
        except (TypeError, ValueError):
            return 422, {"malformed": "size_bytes"}
        existing = self.store.lists(Recording, object_key=object_key)
        if existing:
            self.store.saves(
                Discovery(
                    kind="webhook",
                    occurred_at=self.clock(),
                    discovered_count=0,
                    event=payload["event"],
                )
            )
            return 200, existing[0]
        recording_id = Path(object_key).stem
        self.store.saves(
            Recording(
                recording_id=recording_id,
                object_key=object_key,
                state="discovered",
                started_at=started_at,
                started_at_source="key",
                size_bytes=size_bytes,
            )
        )
        EnqueuesJob(self.store)(
            Job(
                recording_id=recording_id,
                kind="download",
                state="queued",
                max_attempts=5,
                dedupe_key=f"download:{recording_id}",
                queued_at=self.clock(),
            )
        )
        self.store.saves(
            Discovery(
                kind="webhook",
                occurred_at=self.clock(),
                discovered_count=1,
                event=payload["event"],
            )
        )
        return 202, None
