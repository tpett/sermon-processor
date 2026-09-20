from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sermon.store import Job, Recording, Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class AcceptsRecordingWebhook:
    store: Store
    clock: object = now

    def __call__(self, payload):
        object_key = payload["object_key"]
        recording_id = Path(object_key).stem
        started_at = datetime.strptime(recording_id, "recording_%Y%m%d_%H%M%S").replace(
            tzinfo=UTC
        )
        self.store.saves(
            Recording(
                recording_id=recording_id,
                object_key=object_key,
                state="discovered",
                started_at=started_at,
                started_at_source="key",
                size_bytes=int(payload["size_bytes"]),
            )
        )
        self.store.saves(
            Job(
                recording_id=recording_id,
                kind="download",
                state="queued",
                max_attempts=5,
                dedupe_key=f"download:{recording_id}",
                queued_at=self.clock(),
            )
        )
