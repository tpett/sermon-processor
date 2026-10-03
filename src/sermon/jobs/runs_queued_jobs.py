from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime, timedelta

from sermon.jobs.downloads_recording import fails_ingest
from sermon.store import Job, LogEntry, Store
from sermon.store.vocabularies import JOB_STATES_IN_FLIGHT

FIRST_RETRY_DELAY = timedelta(minutes=1)
ATTEMPT = "job_attempt"
REQUEUED_AFTER_FAILURE = frozenset({"analyze", "render"})


def now():
    return datetime.now(UTC)


def retry_delay(attempts):
    return FIRST_RETRY_DELAY * 2 ** (max(attempts, 1) - 1)


def next_attempt_at(store, job):
    logged = [
        entry
        for entry in store.lists(LogEntry, job_id=job.job_id)
        if entry.kind == ATTEMPT
    ]
    if not logged or logged[-1].error is None:
        return None
    ended = logged[-1].occurred_at + timedelta(seconds=logged[-1].duration_seconds or 0.0)
    if job.queued_at > ended:
        return None
    return ended + retry_delay(job.attempts)


def aimed_at(handler, job):
    if is_dataclass(handler) and "job_id" in {field.name for field in fields(handler)}:
        return replace(handler, job_id=job.job_id)
    return handler


class JobNotFailed(ValueError):
    def __init__(self, job):
        super().__init__(f"only a failed job can be retried; job {job.job_id} is {job.state}")


@dataclass(frozen=True)
class RetriesFailedJob:
    store: Store
    clock: object = now

    def __call__(self, job):
        if job.state != "failed":
            raise JobNotFailed(job)
        standing = [
            held
            for held in self.store.lists(Job, recording_id=job.recording_id, kind=job.kind)
            if held.state in JOB_STATES_IN_FLIGHT and held.dedupe_key == job.dedupe_key
        ]
        if standing:
            return standing[0], False
        requeued = self.store.saves(
            replace(
                job,
                state="queued",
                attempts=0,
                failed_permanently=False,
                queued_at=self.clock(),
            )
        )
        return requeued, True


@dataclass(frozen=True)
class RunsQueuedJobs:
    store: Store
    downloads: object
    analyzes: object
    renders: object
    clock: object = now

    def __call__(self):
        at = self.clock()
        eligible = [
            job
            for job in self.store.lists(Job, state="queued")
            if (next_attempt_at(self.store, job) or at) <= at
        ]
        if not eligible:
            return None
        job = eligible[0]
        if job.attempts >= job.max_attempts:
            self.store.saves(replace(job, state="failed", failed_permanently=True))
            if job.kind == "download":
                fails_ingest(self.store, job.recording_id, "download: retry budget exhausted", clock=self.clock)
            return job
        handler = {
            "download": self.downloads,
            "analyze": self.analyzes,
            "render": self.renders,
        }[job.kind]
        try:
            aimed_at(handler, job)()
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
        self._logs_attempt(self.store.loads(Job, job.job_id), began=at)
        self._requeues_within_budget(self.store.loads(Job, job.job_id))
        return job

    def _requeues_within_budget(self, ran):
        if ran.kind not in REQUEUED_AFTER_FAILURE or ran.state != "failed" or ran.failed_permanently:
            return
        if ran.attempts >= ran.max_attempts:
            self.store.saves(replace(ran, failed_permanently=True))
            return
        self.store.saves(replace(ran, state="queued"))

    def _logs_attempt(self, ran, *, began):
        self.store.saves(
            LogEntry(
                recording_id=ran.recording_id,
                segment_id=ran.segment_id,
                job_id=ran.job_id,
                kind=ATTEMPT,
                occurred_at=began,
                correlation_id=ran.dedupe_key,
                duration_seconds=(self.clock() - began).total_seconds(),
                error=None if ran.state in {"succeeded", "cancelled"} else ran.last_error,
            )
        )
