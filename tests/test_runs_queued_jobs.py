from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from sermon.jobs.downloads_recording import FetchesObject, ProbesAudio, RunsDownloadJob
from sermon.jobs.renders_segment import RunsRenderJob, StepFailed
from sermon.jobs.runs_queued_jobs import RetriesFailedJob, RunsQueuedJobs, retry_delay
from sermon.sends_notification import SendsNotification
from sermon.store import Job, LogEntry, Recording, Segment, opens_store

STARTED = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)
FLAC_BYTES = b"fLaC" + bytes(64)
PROBE = ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1)
SECOND = timedelta(seconds=1)


class Clock:
    def __init__(self, at=STARTED):
        self.at = at

    def __call__(self):
        return self.at

    def passes(self, interval):
        self.at += interval


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def clock():
    return Clock()


def a_download(store, recording_id="recording_20260315_094835"):
    store.saves(
        Recording(
            recording_id=recording_id,
            object_key=f"recordings/{recording_id}.flac",
            state="discovered",
            started_at=STARTED,
            started_at_source="key",
            size_bytes=len(FLAC_BYTES),
        )
    )
    return store.saves(
        Job(
            recording_id=recording_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{recording_id}",
            queued_at=STARTED,
        )
    )


def unreachable():
    fetches = FetchesObject()
    fetches.error = "connection refused"
    return fetches


def worker(store, clock, fetches, *, renders=None):
    return RunsQueuedJobs(
        store=store,
        downloads=RunsDownloadJob(store=store, fetches=fetches, probes=PROBE, clock=clock),
        analyzes=lambda: None,
        renders=renders or (lambda: None),
        clock=clock,
    )


def attempts_of(store, job):
    return [
        entry
        for entry in store.lists(LogEntry, job_id=job.job_id)
        if entry.kind == "job_attempt"
    ]


def test_the_delay_grows_with_each_attempt():
    delays = [retry_delay(attempts) for attempts in range(1, 5)]
    assert delays == sorted(delays)
    assert len(set(delays)) == len(delays)
    assert delays[0] > timedelta(0)


def test_a_failed_download_is_not_retried_before_its_delay(store, clock):
    job = a_download(store)
    fetches = unreachable()
    worker(store, clock, fetches)()
    assert store.loads(Job, job.job_id).attempts == 1

    clock.passes(retry_delay(1) - SECOND)
    assert worker(store, clock, fetches)() is None
    assert store.loads(Job, job.job_id).attempts == 1

    clock.passes(SECOND)
    assert worker(store, clock, fetches)() is not None
    assert store.loads(Job, job.job_id).attempts == 2


def test_the_second_retry_waits_longer_than_the_first(store, clock):
    job = a_download(store)
    fetches = unreachable()
    worker(store, clock, fetches)()
    clock.passes(retry_delay(1))
    worker(store, clock, fetches)()
    assert store.loads(Job, job.job_id).attempts == 2

    clock.passes(retry_delay(2) - SECOND)
    assert worker(store, clock, fetches)() is None
    clock.passes(SECOND)
    worker(store, clock, fetches)()
    assert store.loads(Job, job.job_id).attempts == 3


def test_a_job_waiting_out_its_delay_does_not_hold_up_the_next(store, clock):
    waiting = a_download(store)
    fetches = unreachable()
    worker(store, clock, fetches)()
    later = a_download(store, recording_id="recording_20260322_094835")
    fetches.error = None
    fetches.stores(f"recordings/{later.recording_id}.flac", FLAC_BYTES)

    worker(store, clock, fetches)()

    assert store.loads(Job, later.job_id).state == "succeeded"
    assert store.loads(Job, waiting.job_id).attempts == 1


def test_each_attempt_is_logged_with_its_error(store, clock):
    job = a_download(store)
    fetches = unreachable()
    worker(store, clock, fetches)()
    clock.passes(retry_delay(1))
    worker(store, clock, fetches)()
    clock.passes(retry_delay(2))
    fetches.error = None
    fetches.stores(f"recordings/{job.recording_id}.flac", FLAC_BYTES)
    worker(store, clock, fetches)()

    logged = attempts_of(store, job)
    assert [entry.error for entry in logged] == ["connection refused", "connection refused", None]
    assert [entry.occurred_at for entry in logged] == [
        STARTED,
        STARTED + retry_delay(1),
        STARTED + retry_delay(1) + retry_delay(2),
    ]
    assert {entry.recording_id for entry in logged} == {job.recording_id}
    assert all(entry.duration_seconds is not None for entry in logged)


def test_an_attempt_records_how_long_it_took(store, clock):
    job = a_download(store)

    def slow():
        clock.passes(timedelta(seconds=42))
        raise RuntimeError("stalled")

    RunsQueuedJobs(
        store=store, downloads=slow, analyzes=slow, renders=slow, clock=clock
    )()

    (logged,) = attempts_of(store, job)
    assert logged.duration_seconds == 42.0
    assert logged.occurred_at == STARTED


def test_the_delay_runs_from_when_the_attempt_ended(store, clock):
    job = a_download(store)
    fetches = unreachable()

    def stalls_then_refuses(key, destination):
        clock.passes(timedelta(minutes=10))
        return fetches(key, destination)

    worker(store, clock, stalls_then_refuses)()
    assert store.loads(Job, job.job_id).attempts == 1

    clock.passes(retry_delay(1) - SECOND)
    assert worker(store, clock, fetches)() is None
    clock.passes(SECOND)
    assert worker(store, clock, fetches)() is not None


def test_an_escaped_exception_is_logged_as_a_failed_attempt(store, clock):
    job = a_download(store)

    def explodes():
        raise RuntimeError("probe crashed")

    RunsQueuedJobs(
        store=store, downloads=explodes, analyzes=explodes, renders=explodes, clock=clock
    )()

    (logged,) = attempts_of(store, job)
    assert logged.error == "RuntimeError: probe crashed"


def test_a_job_requeued_by_hand_runs_without_waiting(store, clock):
    job = a_download(store)

    def explodes():
        raise RuntimeError("probe crashed")

    RunsQueuedJobs(
        store=store, downloads=explodes, analyzes=explodes, renders=explodes, clock=clock
    )()
    clock.passes(SECOND)
    RetriesFailedJob(store=store, clock=clock)(store.loads(Job, job.job_id))
    clock.passes(SECOND)

    fetches = FetchesObject()
    fetches.stores(f"recordings/{job.recording_id}.flac", FLAC_BYTES)
    worker(store, clock, fetches)()
    assert store.loads(Job, job.job_id).state == "succeeded"


def a_render(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_102900",
            object_key="recordings/recording_20260823_102900.flac",
            state="reviewed",
            started_at=STARTED,
            started_at_source="key",
            size_bytes=1,
        )
    )
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="approved",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
            publication_date=date(2026, 8, 23),
            label="Hebrews 12.4-11",
        )
    )
    return store.saves(
        Job(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="render",
            state="queued",
            max_attempts=3,
            dedupe_key=f"render:{segment.segment_id}",
            queued_at=STARTED,
        )
    )


def encodes_after(failures):
    remaining = [failures]

    def steps(name):
        if name == "encode" and remaining[0]:
            remaining[0] -= 1
            raise StepFailed(name, "encoder crashed")

    return steps


def renders_with(store, clock, steps):
    return RunsRenderJob(
        store=store, steps=steps, notifies=SendsNotification(store=store), clock=clock
    )


def test_a_failed_render_is_retried_after_its_delay(store, clock):
    job = a_render(store)
    renders = renders_with(store, clock, encodes_after(1))
    worker(store, clock, FetchesObject(), renders=renders)()
    assert store.loads(Job, job.job_id).state == "queued"

    clock.passes(retry_delay(1) - SECOND)
    assert worker(store, clock, FetchesObject(), renders=renders)() is None
    clock.passes(SECOND)
    worker(store, clock, FetchesObject(), renders=renders)()

    assert store.loads(Job, job.job_id).state == "succeeded"
    assert store.loads(Segment, job.segment_id).state == "complete"
    assert [entry.error for entry in attempts_of(store, job)] == ["encode: encoder crashed", None]


def test_a_render_that_exhausts_its_budget_fails_permanently(store, clock):
    job = a_render(store)
    renders = renders_with(store, clock, encodes_after(10))
    for attempt in range(1, 4):
        worker(store, clock, FetchesObject(), renders=renders)()
        clock.passes(retry_delay(attempt))

    stopped = store.loads(Job, job.job_id)
    assert (stopped.state, stopped.attempts, stopped.failed_permanently) == ("failed", 3, True)
    assert worker(store, clock, FetchesObject(), renders=renders)() is None
    assert store.loads(Segment, job.segment_id).state == "processing_failed"


def test_a_job_with_no_logged_attempt_runs_at_once(store, clock):
    job = store.saves(replace(a_download(store), attempts=2))
    fetches = FetchesObject()
    fetches.stores(f"recordings/{job.recording_id}.flac", FLAC_BYTES)
    worker(store, clock, fetches)()
    assert store.loads(Job, job.job_id).state == "succeeded"
