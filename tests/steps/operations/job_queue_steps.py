from datetime import UTC, datetime, timedelta

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment
from sermon.config import Credential
from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.jobs.analyzes_recording import RunsAnalyzeJob
from sermon.jobs.downloads_recording import (
    FetchesObject,
    ProbesAudio,
    RunsDownloadJob,
)
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.jobs.recovers_interrupted_jobs import RecoversInterruptedJobs
from sermon.jobs.runs_queued_jobs import (
    ATTEMPT,
    RetriesFailedJob,
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


def worker_at(store, fetches, clock):
    return RunsQueuedJobs(
        store=store,
        downloads=RunsDownloadJob(
            store=store,
            fetches=fetches,
            probes=ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1),
            clock=clock,
        ),
        analyzes=lambda: None,
        renders=lambda: None,
        clock=clock,
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
        analyzes=RunsAnalyzeJob(
            store=store,
            stages=lambda _name: None,
            notifies=SendsNotification(store=store),
            clock=lambda: FROZEN,
        ),
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
        RetriesFailedJob(store=store, clock=lambda: FROZEN)(failed)
        return None
    raise AssertionError(trigger)


@then("a job is enqueued")
def _(store):
    queued = store.lists(Job, state="queued")
    assert queued


@then("the triggering request returns immediately")
def _(store, trigger_result):
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
    return RecoversInterruptedJobs(store=store)()


@then("the queued jobs still run")
def _(store):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    worker(store, store._queued_fetches)()
    assert store.lists(Job, kind="download")[0].state == "succeeded"
    assert store.lists(Recording)[0].state == "downloaded"


@then("no job runs twice as a result of the restart")
def _(store):
    worker(store, store._queued_fetches)()
    downloads = store.lists(Job, kind="download")
    assert len(downloads) == 1
    assert downloads[0].state == "succeeded"


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
    worker(store, FetchesObject())()
    jobs = store.lists(Job, kind="analyze")
    succeeded = [job for job in jobs if job.state == "succeeded"]
    assert len(succeeded) == 1
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
