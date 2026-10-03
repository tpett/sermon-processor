from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.store import Job, Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class RetriesFailedJob:
    store: Store
    clock: object = now

    def __call__(self, job):
        return self.store.saves(
            replace(
                job,
                state="queued",
                failed_permanently=False,
                queued_at=self.clock(),
            )
        )


@dataclass(frozen=True)
class RunsQueuedJobs:
    store: Store
    downloads: object
    analyzes: object
    renders: object

    def __call__(self):
        queued = self.store.lists(Job, state="queued")
        if not queued:
            return None
        job = queued[0]
        if job.attempts >= job.max_attempts:
            self.store.saves(replace(job, state="failed", failed_permanently=True))
            return job
        handler = {
            "download": self.downloads,
            "analyze": self.analyzes,
            "render": self.renders,
        }[job.kind]
        try:
            handler()
        except Exception as escaped:  # noqa: BLE001 - see below
            # A handler that lets an exception escape has not recorded the
            # failure, so the job is still `running`. Left alone it is requeued
            # by recovery on the next start and fails the same way forever, and
            # the process dies each time: one bad job stops all work. Record it
            # here and carry on.
            attempts = (job.attempts or 0) + 1
            self.store.saves(
                replace(
                    self.store.loads(Job, job.job_id),
                    state="failed",
                    last_error=f"{type(escaped).__name__}: {escaped}",
                    attempts=attempts,
                    failed_permanently=attempts >= job.max_attempts,
                )
            )
        return job
