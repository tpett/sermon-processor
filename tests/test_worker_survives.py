"""A worker must outlive the jobs it runs.

Written after a live crash loop: a download interrupted mid-transfer left a
truncated FLAC, the probe raised `AudioNotMeasurable`, nothing caught it, the
process exited, `restart: unless-stopped` brought it back, recovery requeued the
same job, and it failed identically. One bad job stopped every other job
indefinitely, and the only symptom the reviewer saw was that pressing Ingest did
nothing.
"""

from datetime import UTC, datetime

import pytest

from sermon.jobs.probes_recording import AudioNotMeasurable
from sermon.jobs.runs_queued_jobs import RunsQueuedJobs
from sermon.store import Job, Recording, opens_store

FROZEN = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def queued(store, kind="download", attempts=0, max_attempts=5):
    store.saves(
        Recording(
            recording_id="recording_20260315_094835",
            object_key="recordings/recording_20260315_094835.flac",
            state="discovered",
            started_at=FROZEN,
            started_at_source="key",
            size_bytes=1,
        )
    )
    return store.saves(
        Job(
            recording_id="recording_20260315_094835",
            kind=kind,
            state="queued",
            attempts=attempts,
            max_attempts=max_attempts,
            dedupe_key=f"{kind}:recording_20260315_094835",
            queued_at=FROZEN,
        )
    )


def runner(store, handler):
    return RunsQueuedJobs(
        store=store, downloads=handler, analyzes=handler, renders=handler
    )


def explodes():
    raise AudioNotMeasurable("/data/recording_20260315_094835.flac")


def test_an_exploding_handler_does_not_take_the_worker_down(store):
    queued(store)
    runner(store, explodes)()  # must not raise


def test_the_job_is_recorded_failed_rather_than_left_running(store):
    queued(store)
    runner(store, explodes)()

    job = store.lists(Job)[0]
    assert job.state == "failed", "a job left running is requeued and fails forever"
    assert "AudioNotMeasurable" in job.last_error
    assert job.attempts == 1


def test_a_failing_job_does_not_block_the_next_one(store):
    queued(store)
    runner(store, explodes)()
    second = store.saves(
        Job(
            recording_id="recording_20260315_094835",
            kind="render",
            state="queued",
            max_attempts=5,
            dedupe_key="render:later",
            queued_at=FROZEN,
        )
    )
    ran = []
    runner(store, lambda: ran.append(True))()
    assert ran == [True], "the queue must move on past a job that failed"
    assert store.loads(Job, second.job_id).state == "queued"


def test_the_last_attempt_is_marked_permanent(store):
    queued(store, attempts=4, max_attempts=5)
    runner(store, explodes)()

    job = store.lists(Job)[0]
    assert (job.attempts, job.failed_permanently) == (5, True)


def test_an_earlier_attempt_is_not_permanent(store):
    queued(store, attempts=1, max_attempts=5)
    runner(store, explodes)()

    job = store.lists(Job)[0]
    assert (job.attempts, job.failed_permanently) == (2, False)
