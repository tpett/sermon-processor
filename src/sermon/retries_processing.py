from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.store import Job, Store
from sermon.store.vocabularies import JOB_STATES_IN_FLIGHT


def now():
    return datetime.now(UTC)


class ProcessingNotFailed(ValueError):
    def __init__(self):
        super().__init__("only a Segment whose processing failed can be retried")


@dataclass(frozen=True)
class RetriesProcessing:
    store: Store
    clock: object = now

    def __call__(self, segment):
        if segment.state != "processing_failed":
            raise ProcessingNotFailed()
        standing = [
            job
            for job in self.store.lists(Job, segment_id=segment.segment_id, kind="render")
            if job.state in JOB_STATES_IN_FLIGHT
        ]
        if standing:
            return standing[0], False
        queued = EnqueuesJob(self.store)(
            Job(
                recording_id=segment.recording_id,
                segment_id=segment.segment_id,
                kind="render",
                state="queued",
                max_attempts=5,
                dedupe_key=f"render:{segment.segment_id}",
                queued_at=self.clock(),
            )
        )
        return queued, True
