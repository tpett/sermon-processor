from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from sermon.store import Job, Store
from sermon.store.vocabularies import JOB_STATES_IN_FLIGHT


@dataclass(frozen=True)
class EnqueuesJob:
    store: Store

    def __call__(self, job):
        try:
            return self.store.saves(job)
        except sqlite3.IntegrityError:
            queued = [
                existing
                for existing in self.store.lists(
                    Job, recording_id=job.recording_id, kind=job.kind
                )
                if existing.state in JOB_STATES_IN_FLIGHT
                and existing.dedupe_key == job.dedupe_key
            ]
            return queued[0]
