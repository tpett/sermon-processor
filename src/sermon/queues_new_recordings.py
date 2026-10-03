from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sermon.reconciles_bucket import queues_download
from sermon.store import Job, LogEntry, Recording, Store

MAX_QUEUED_PER_SCAN = 2
FUTURE_TOLERANCE = timedelta(days=1)
ACTOR = "scheduled scan"


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class QueuesNewRecordings:
    store: Store
    clock: object = now
    limit: int = MAX_QUEUED_PER_SCAN

    def __call__(self):
        moment = self.clock()
        plausible = [
            recording
            for recording in self.store.lists(Recording)
            if recording.started_at <= moment + FUTURE_TOLERANCE
        ]
        downloaded = {job.recording_id for job in self.store.lists(Job, kind="download")}
        acted_on = [
            recording
            for recording in plausible
            if recording.state != "discovered" or recording.recording_id in downloaded
        ]
        if not acted_on:
            return ()
        mark = max(recording.started_at for recording in acted_on)
        fresh = sorted(
            (recording for recording in plausible if recording.started_at > mark),
            key=lambda recording: recording.started_at,
        )[: self.limit]
        for recording in fresh:
            job = queues_download(self.store, recording, clock=self.clock)
            self.store.saves(
                LogEntry(
                    recording_id=recording.recording_id,
                    job_id=job.job_id,
                    kind="download_queued",
                    occurred_at=moment,
                    correlation_id=job.dedupe_key,
                    actor=ACTOR,
                )
            )
        return tuple(fresh)
