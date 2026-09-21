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
        if getattr(self.store, "_scratch_exhausted", False):
            self.store._paused_for_scratch = True
            return None
        queued = self.store.lists(Job, state="queued")
        if not queued:
            return None
        limit = getattr(self.store, "_analysis_concurrency", None)
        if limit is not None:
            running = len(self.store.lists(Job, kind="analyze", state="running"))
            analyze_queued = [job for job in queued if job.kind == "analyze"]
            if running >= limit:
                return None
            queued = analyze_queued or queued
        job = queued[0]
        if job.attempts >= job.max_attempts:
            self.store.saves(replace(job, state="failed", failed_permanently=True))
            return job
        {
            "download": self.downloads,
            "analyze": self.analyzes,
            "render": self.renders,
        }[job.kind]()
        return job
