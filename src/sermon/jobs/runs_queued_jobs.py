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
                last_error=None,
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
        {
            "download": self.downloads,
            "analyze": self.analyzes,
            "render": self.renders,
        }[job.kind]()
        return job
