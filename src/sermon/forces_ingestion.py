from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.store import Job, Store
from sermon.store.vocabularies import JOB_STATES_IN_FLIGHT


def now():
    return datetime.now(UTC)


INGEST_ACTION = "ingest"
DOWNLOAD_ATTEMPTS = 5
NOTHING_QUEUED = "none"
QUEUED = "queued"
WAITING = "waiting"
RUNNING = "running"


@dataclass(frozen=True)
class QueueStanding:
    """Where a Recording's download stands in the queue the worker drains."""

    outcome: str
    job: Job | None
    position: int | None
    queued_count: int
    since: datetime | None


def finds_download(store, recording):
    in_flight = [
        job
        for job in store.lists(Job, recording_id=recording.recording_id, kind="download")
        if job.state in JOB_STATES_IN_FLIGHT
    ]
    return in_flight[0] if in_flight else None


def reads_standing(store, recording, queued=None):
    waiting = store.lists(Job, state="queued") if queued is None else list(queued)
    job = finds_download(store, recording)
    if job is None:
        return QueueStanding(
            outcome=NOTHING_QUEUED,
            job=None,
            position=None,
            queued_count=len(waiting),
            since=None,
        )
    if job.state == RUNNING:
        return QueueStanding(
            outcome=RUNNING,
            job=job,
            position=None,
            queued_count=len(waiting),
            since=job.started_at,
        )
    # store.lists orders jobs by queued_at, which is the order RunsQueuedJobs picks in.
    identified = [one.job_id for one in waiting]
    return QueueStanding(
        outcome=WAITING,
        job=job,
        position=identified.index(job.job_id) + 1 if job.job_id in identified else None,
        queued_count=len(waiting),
        since=job.queued_at,
    )


@dataclass(frozen=True)
class ForcesIngestion:
    """features/ingestion/s3_reconciliation.feature, "An operator can force ingestion"."""

    store: Store
    clock: object = now

    def __call__(self, recording):
        standing = reads_standing(self.store, recording)
        if standing.outcome != NOTHING_QUEUED:
            return standing
        EnqueuesJob(self.store)(
            Job(
                recording_id=recording.recording_id,
                kind="download",
                state="queued",
                max_attempts=DOWNLOAD_ATTEMPTS,
                dedupe_key=f"download:{recording.recording_id}",
                queued_at=self.clock(),
            )
        )
        return replace(reads_standing(self.store, recording), outcome=QUEUED)
