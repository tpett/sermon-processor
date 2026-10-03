from argparse import Namespace
from datetime import UTC, datetime, timedelta

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment
from sermon.cli import drains
from sermon.config import Credential
from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.jobs.analyzes_recording import RunsAnalyzeJob, StageFailed
from sermon.jobs.downloads_recording import (
    FetchesObject,
    ProbesAudio,
    RunsDownloadJob,
)
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.jobs.recovers_interrupted_jobs import RecoversInterruptedJobs
from sermon.jobs.runs_queued_jobs import (
    ATTEMPT,
    RunsQueuedJobs,
    retry_delay,
)
from sermon.sends_notification import SendsNotification
from sermon.store import Job, LogEntry, Recording, Reviewer, Segment
from sermon.web import creates_app

FLAC_BYTES = b"fLaC" + bytes(64)
SECOND = timedelta(seconds=1)
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
OBJECT_KEY = "recordings/recording_20260823_103015.flac"
WEBHOOK_TOKEN_VALUE = "the-token-only-the-spec-suite-issues"
WEBHOOK = {
    "event": "recording.uploaded",
    "bucket": "sermons",
    "object_key": OBJECT_KEY,
    "size_bytes": len(FLAC_BYTES),
    "recorded_at": "2026-08-23T10:30:15-05:00",
}


class MovesOn:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at

    def passes(self, interval):
        self.at += interval


@pytest.fixture
def queue_clock():
    return MovesOn(FROZEN)


@pytest.fixture
def unreachable_bucket():
    fetches = FetchesObject()
    fetches.error = "connection refused"
    return fetches


def worker_at(store, fetches, clock, analyzes=None):
    return RunsQueuedJobs(
        store=store,
        downloads=RunsDownloadJob(
            store=store,
            fetches=fetches,
            probes=ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1),
            clock=clock,
        ),
        analyzes=analyzes or (lambda: None),
        renders=lambda: None,
        clock=clock,
    )


class TranscriberDown:
    def __init__(self):
        self.down = True
        self.ran = 0

    def __call__(self, recording):
        self.ran += 1
        if self.down:
            raise StageFailed("transcription", "the transcriber did not answer")


class TranscriberUp(TranscriberDown):
    def __init__(self):
        super().__init__()
        self.down = False


def analyzes_at(store, clock, analyses):
    return RunsAnalyzeJob(
        store=store,
        stages=lambda _name: None,
        notifies=SendsNotification(store=store),
        clock=clock,
        analyses=analyses,
    )


def worker(store, fetches):
    return RunsQueuedJobs(
        store=store,
        downloads=RunsDownloadJob(
            store=store,
            fetches=fetches,
            probes=ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1),
            clock=lambda: FROZEN,
        ),
        analyzes=analyzes_at(store, lambda: FROZEN, TranscriberUp()),
        renders=RunsRenderJob(
            store=store,
            steps=lambda _name: None,
            notifies=SendsNotification(store=store),
            clock=lambda: FROZEN,
        ),
    )


@when(parsers.parse('"{trigger}" happens'), target_fixture="trigger_result")
def _(store, trigger):
    if trigger == "a webhook announces a new recording":
        token = Credential(WEBHOOK_TOKEN_VALUE)
        response = creates_app(
            store=store, clock=lambda: FROZEN, webhook_token=token
        ).test_client().post(
            "/api/webhooks/recordings",
            json=WEBHOOK,
            headers={"Authorization": f"Bearer {WEBHOOK_TOKEN_VALUE}"},
        )
        return response
    if trigger == "a download completes":
        recording = store.saves(
            Recording(
                recording_id="recording_20260823_103015",
                object_key=OBJECT_KEY,
                state="discovered",
                started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
                started_at_source="key",
                size_bytes=len(FLAC_BYTES),
            )
        )
        store.saves(
            Job(
                recording_id=recording.recording_id,
                kind="download",
                state="queued",
                max_attempts=5,
                dedupe_key=f"download:{recording.recording_id}",
                queued_at=FROZEN,
            )
        )
        fetches = FetchesObject()
        fetches.stores(OBJECT_KEY, FLAC_BYTES)
        RunsDownloadJob(
            store=store,
            fetches=fetches,
            probes=ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1),
            clock=lambda: FROZEN,
        )()
        return None
    if trigger == "a reviewer approves a recording":
        recording = store.saves(
            Recording(
                recording_id="recording_20260823_103015",
                object_key=OBJECT_KEY,
                state="awaiting_review",
                started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
                started_at_source="key",
                size_bytes=1,
            )
        )
        segment = store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification="sermon",
                state="proposed",
                span_start_seconds=60.0,
                span_end_seconds=3300.0,
                punch_in_seconds=60.0,
                punch_out_seconds=3300.0,
            )
        )
        ApprovesSegment(store=store, clock=lambda: FROZEN)(segment)
        return None
    if trigger == "an operator retries a failed stage":
        return retried_over_http(store)
    raise AssertionError(trigger)


def retried_over_http(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key=OBJECT_KEY,
            state="analysis_failed",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    failed = store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="failed",
            max_attempts=5,
            attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}",
            queued_at=FROZEN,
            last_error="transcription timed out",
        )
    )
    return (
        creates_app(store=store, clock=lambda: FROZEN)
        .test_client()
        .post(f"/api/jobs/{failed.job_id}/retry")
    )


ENQUEUED_BY = {
    "a webhook announces a new recording": "download",
    "a download completes": "analyze",
    "a reviewer approves a recording": "render",
    "an operator retries a failed stage": "analyze",
}


@then("a job is enqueued")
def _(store, _pytest_bdd_example):
    expected = ENQUEUED_BY[_pytest_bdd_example["trigger"]]
    queued = [(job.kind, job.recording_id) for job in store.lists(Job, state="queued")]
    assert queued == [(expected, "recording_20260823_103015")], queued


@then("the triggering request returns immediately")
def _(store, trigger_result, _pytest_bdd_example):
    if _pytest_bdd_example["trigger"] == "an operator retries a failed stage":
        assert trigger_result.status_code == 202
        (job,) = store.lists(Job, kind="analyze")
        assert (job.state, job.attempts) == ("queued", 0)
        assert store.lists(Recording)[0].state == "analysis_failed"
        assert store.lists(LogEntry, job_id=job.job_id) == []
        return
    if trigger_result is not None:
        assert trigger_result.status_code == 202
        assert store.lists(Recording)[0].state == "discovered"
        return
    recordings = store.lists(Recording)
    if recordings and recordings[0].state == "downloaded":
        assert store.lists(Job, kind="analyze", state="queued")
        assert recordings[0].state != "analyzing"
        return
    segments = store.lists(Segment)
    if segments and segments[0].state == "approved":
        assert store.lists(Job, kind="render", state="queued")
        assert segments[0].state != "processing"
        return
    assert store.lists(Job, state="queued")


@given("jobs are queued")
def _(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key=OBJECT_KEY,
            state="discovered",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=len(FLAC_BYTES),
        )
    )
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{recording.recording_id}",
            queued_at=FROZEN,
        )
    )
    fetches = FetchesObject()
    fetches.stores(OBJECT_KEY, FLAC_BYTES)
    store._queued_fetches = fetches


@when("the application restarts")
def _(store):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    RecoversInterruptedJobs(store=store)()
    waiting = len(store.lists(Job, state="queued"))
    drains(worker(store, store._queued_fetches), Namespace(once=False, limit=waiting, poll=0), print, None)


@then("the queued jobs still run")
def _(store):
    downloads = store.lists(Job, kind="download")
    assert [job.state for job in downloads] == ["succeeded"], [job.state for job in downloads]
    assert store.lists(Recording)[0].state == "downloaded"


@then("no job runs twice as a result of the restart")
def _(store):
    downloads = store.lists(Job, kind="download")
    assert len(downloads) == 1
    attempts = [entry for entry in store.lists(LogEntry, job_id=downloads[0].job_id) if entry.kind == ATTEMPT]
    assert len(attempts) == 1, f"{len(attempts)} attempts were logged"


@given("an analysis job is already queued for a Recording")
def _(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key=OBJECT_KEY,
            state="downloaded",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=11520.0,
        )
    )
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}",
            queued_at=FROZEN,
        )
    )


@when("another analysis job is enqueued for the same Recording")
def _(store):
    recording = store.lists(Recording)[0]
    EnqueuesJob(store)(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}",
            queued_at=FROZEN,
        )
    )


@then("only one job runs")
def _(store):
    worker(store, FetchesObject())()
    assert worker(store, FetchesObject())() is None
    jobs = store.lists(Job, kind="analyze")
    assert [job.state for job in jobs] == ["succeeded"]
    assert len(attempts_logged(store, jobs[0])) == 1
    assert store.lists(Recording)[0].state == "awaiting_review"


@given("a job fails", target_fixture="failing_job")
def _(store, queue_clock, unreachable_bucket):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key=OBJECT_KEY,
            state="discovered",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=len(FLAC_BYTES),
        )
    )
    job = store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{recording.recording_id}",
            queued_at=FROZEN,
        )
    )
    worker_at(store, unreachable_bucket, queue_clock)()
    return store.loads(Job, job.job_id)


@then("it is retried with increasing delay between attempts")
def _(store, failing_job, queue_clock, unreachable_bucket):
    assert retry_delay(2) - SECOND >= retry_delay(1)
    runs = worker_at(store, unreachable_bucket, queue_clock)
    for attempt in (1, 2):
        queue_clock.passes(retry_delay(attempt) - SECOND)
        assert runs() is None, f"retried before attempt {attempt}'s delay had passed"
        assert store.loads(Job, failing_job.job_id).attempts == attempt
        queue_clock.passes(SECOND)
        assert runs() is not None
        assert store.loads(Job, failing_job.job_id).attempts == attempt + 1


@then("each attempt is recorded with its error")
def _(store, failing_job):
    job = store.loads(Job, failing_job.job_id)
    logged = [
        entry
        for entry in store.lists(LogEntry, job_id=job.job_id)
        if entry.kind == ATTEMPT
    ]
    assert job.attempts >= 1
    assert len(logged) == job.attempts
    assert [entry.error for entry in logged] == ["connection refused"] * job.attempts
    assert len({entry.occurred_at for entry in logged}) == len(logged)
    assert all(entry.duration_seconds is not None for entry in logged)


@given("jobs are queued, running, and failed")
def _(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key=OBJECT_KEY,
            state="downloaded",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    for state, kind in (("queued", "download"), ("running", "analyze"), ("failed", "render")):
        store.saves(
            Job(
                recording_id=recording.recording_id,
                kind=kind,
                state=state,
                max_attempts=5,
                dedupe_key=f"{kind}:{recording.recording_id}:{state}",
                queued_at=FROZEN,
                last_error="boom" if state == "failed" else None,
            )
        )


FAILED_STATE_OF = {"download": "ingest_failed", "analyze": "analysis_failed"}
LONG_AFTER = timedelta(days=1)


def attempts_logged(store, job):
    return [entry for entry in store.lists(LogEntry, job_id=job.job_id) if entry.kind == ATTEMPT]


@given("a job has failed its maximum number of attempts", target_fixture="failing_job")
def _(store, queue_clock):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key=OBJECT_KEY,
            state="downloaded",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=5412.0,
        )
    )
    job = store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}",
            queued_at=FROZEN,
        )
    )
    store._transcriber = TranscriberDown()
    runs = worker_at(
        store, FetchesObject(), queue_clock, analyzes_at(store, queue_clock, store._transcriber)
    )
    for attempt in range(1, job.max_attempts + 1):
        assert runs() is not None, f"attempt {attempt} did not run"
        queue_clock.passes(retry_delay(attempt))
    return store.loads(Job, job.job_id)


@then("the Recording enters the matching failed state")
def _(store, failing_job):
    expected = FAILED_STATE_OF[failing_job.kind]
    assert store.loads(Recording, failing_job.recording_id).state == expected
    failed = [
        entry.error
        for entry in store.lists(LogEntry, recording_id=failing_job.recording_id)
        if entry.entered_state == expected
    ]
    assert failed == ["transcription: the transcriber did not answer"], failed


@then("the job stops retrying")
def _(store, failing_job, queue_clock):
    stopped = store.loads(Job, failing_job.job_id)
    assert (stopped.state, stopped.attempts, stopped.failed_permanently) == ("failed", 5, True)
    queue_clock.passes(LONG_AFTER)
    runs = worker_at(
        store, FetchesObject(), queue_clock, analyzes_at(store, queue_clock, store._transcriber)
    )
    assert runs() is None
    assert store._transcriber.ran == 5
    assert len(attempts_logged(store, stopped)) == 5


@then("an operator can retry it manually")
def _(store, failing_job, queue_clock):
    answered = (
        creates_app(store=store, clock=queue_clock)
        .test_client()
        .post(f"/api/jobs/{failing_job.job_id}/retry")
    )
    assert answered.status_code == 202, answered.status_code
    store._transcriber.down = False
    runs = worker_at(
        store, FetchesObject(), queue_clock, analyzes_at(store, queue_clock, store._transcriber)
    )
    assert runs() is not None
    assert store._transcriber.ran == 6
    assert store.loads(Job, failing_job.job_id).state == "succeeded"
    assert store.loads(Recording, failing_job.recording_id).state == "awaiting_review"


@given("a job fails because the source file is not decodable audio", target_fixture="failing_job")
def _(store, queue_clock):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key=OBJECT_KEY,
            state="discovered",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=len(FLAC_BYTES),
        )
    )
    job = store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{recording.recording_id}",
            queued_at=FROZEN,
        )
    )
    store._undecodable = FetchesObject()
    store._undecodable.stores(OBJECT_KEY, b"")
    assert worker_at(store, store._undecodable, queue_clock)() is not None
    return store.loads(Job, job.job_id)


@then("it is not retried")
def _(store, failing_job, queue_clock):
    for attempt in range(1, failing_job.max_attempts + 1):
        queue_clock.passes(retry_delay(attempt))
        assert worker_at(store, store._undecodable, queue_clock)() is None
    stopped = store.loads(Job, failing_job.job_id)
    assert (stopped.state, stopped.attempts, stopped.failed_permanently) == ("failed", 1, True)
    assert len(attempts_logged(store, stopped)) == 1


@then('the Recording enters "ingest_failed" immediately')
def _(store, failing_job):
    assert failing_job.attempts == 1
    assert store.loads(Recording, failing_job.recording_id).state == "ingest_failed"
    failed = [
        entry.error
        for entry in store.lists(LogEntry, recording_id=failing_job.recording_id)
        if entry.entered_state == "ingest_failed"
    ]
    assert failed == ["source file is not decodable audio"], failed
