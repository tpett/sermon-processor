from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.store import Job, LogEntry, Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class RerunsAnalysis:
    store: Store
    clock: object = now

    def __call__(self, recording, *, actor="reviewer"):
        occurred = self.clock()
        queued = EnqueuesJob(self.store)(
            Job(
                recording_id=recording.recording_id,
                kind="analyze",
                state="queued",
                max_attempts=3,
                dedupe_key=f"analyze:{recording.recording_id}:{occurred.isoformat()}",
                queued_at=occurred,
            )
        )
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                job_id=queued.job_id,
                kind="reanalysis",
                occurred_at=occurred,
                correlation_id=f"reanalyze:{recording.recording_id}",
                actor=actor,
            )
        )
        return queued
