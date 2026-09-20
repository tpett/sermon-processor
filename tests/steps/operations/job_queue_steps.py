from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment
from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.jobs.analyzes_recording import RunsAnalyzeJob
from sermon.jobs.downloads_recording import (
    FetchesObject,
    ProbesAudio,
    RunsDownloadJob,
)
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.jobs.runs_queued_jobs import RetriesFailedJob, RunsQueuedJobs
from sermon.sends_notification import SendsNotification
from sermon.store import Job, Recording, Reviewer, Segment
from sermon.web import creates_app

FLAC_BYTES = b"fLaC" + bytes(64)
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
OBJECT_KEY = "recordings/recording_20260823_103015.flac"
WEBHOOK = {
    "event": "recording.uploaded",
    "object_key": OBJECT_KEY,
    "size_bytes": len(FLAC_BYTES),
}


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
        response = creates_app(store=store, clock=lambda: FROZEN).test_client().post(
            "/api/webhooks/recordings", json=WEBHOOK
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
def _():
    return None


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
