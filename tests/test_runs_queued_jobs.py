from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from sermon.analysis.transcribes_audio import AudioNotDecodable
from sermon.config import ModelEndpointUnreachable
from sermon.jobs.analyzes_recording import RunsAnalyzeJob, StageFailed
from sermon.jobs.downloads_recording import FetchesObject, ProbesAudio, RunsDownloadJob
from sermon.jobs.renders_mp3 import RenderProducedNothing
from sermon.jobs.renders_segment import RunsRenderJob, StepFailed
from sermon.jobs.runs_queued_jobs import RetriesFailedJob, RunsQueuedJobs, retry_delay
from sermon.sends_notification import SendsNotification
from sermon.store import Job, LogEntry, Notification, Recording, Reviewer, Segment, opens_store

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


def test_a_download_that_stops_retrying_is_marked_permanent(store, clock):
    job = a_download(store)
    fetches = FetchesObject()
    for attempt in range(1, 4):
        worker(store, clock, fetches)()
        clock.passes(retry_delay(attempt))

    stopped = store.loads(Job, job.job_id)
    assert (stopped.state, stopped.attempts, stopped.failed_permanently) == ("failed", 3, True)
    assert store.loads(Recording, job.recording_id).state == "ingest_failed"


def test_a_job_with_no_logged_attempt_runs_at_once(store, clock):
    job = store.saves(replace(a_download(store), attempts=2))
    fetches = FetchesObject()
    fetches.stores(f"recordings/{job.recording_id}.flac", FLAC_BYTES)
    worker(store, clock, fetches)()
    assert store.loads(Job, job.job_id).state == "succeeded"


def an_analysis(store, *, max_attempts=3, recording_id="recording_20260823_102900"):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    store.saves(
        Recording(
            recording_id=recording_id,
            object_key=f"recordings/{recording_id}.flac",
            state="downloaded",
            started_at=STARTED,
            started_at_source="key",
            size_bytes=1,
            duration_seconds=5412.0,
        )
    )
    return store.saves(
        Job(
            recording_id=recording_id,
            kind="analyze",
            state="queued",
            max_attempts=max_attempts,
            dedupe_key=f"analyze:{recording_id}",
            queued_at=STARTED,
        )
    )


class FailsAnalysis:
    def __init__(self, times, error=None):
        self.remaining = times
        self.error = error or StageFailed("transcription", "the transcriber did not answer")
        self.ran = 0

    def __call__(self, recording):
        self.ran += 1
        if self.remaining:
            self.remaining -= 1
            raise self.error


def analyzes_with(store, clock, analyses, sent):
    return RunsAnalyzeJob(
        store=store,
        stages=lambda _name: None,
        notifies=SendsNotification(store=store, sends=sent.append),
        clock=clock,
        analyses=analyses,
    )


def analysis_worker(store, clock, analyses, sent=None):
    return RunsQueuedJobs(
        store=store,
        downloads=lambda: None,
        analyzes=analyzes_with(store, clock, analyses, [] if sent is None else sent),
        renders=lambda: None,
        clock=clock,
    )


def entered(store, recording_id):
    return [
        (entry.entered_state, entry.error)
        for entry in store.lists(LogEntry, recording_id=recording_id)
        if entry.kind == "state_change"
    ]


def test_a_failed_analysis_returns_the_recording_to_downloaded_and_is_retried(store, clock):
    job = an_analysis(store)
    analyses = FailsAnalysis(times=1)
    analysis_worker(store, clock, analyses)()

    assert store.loads(Job, job.job_id).state == "queued"
    assert store.loads(Recording, job.recording_id).state == "downloaded"
    assert entered(store, job.recording_id) == [
        ("analyzing", None),
        ("downloaded", "transcription: the transcriber did not answer"),
    ]

    clock.passes(retry_delay(1) - SECOND)
    assert analysis_worker(store, clock, analyses)() is None
    clock.passes(SECOND)
    analysis_worker(store, clock, analyses)()

    assert analyses.ran == 2
    assert store.loads(Job, job.job_id).state == "succeeded"
    assert store.loads(Recording, job.recording_id).state == "awaiting_review"
    assert [entry.error for entry in attempts_of(store, job)] == [
        "transcription: the transcriber did not answer",
        None,
    ]


def test_an_analysis_that_exhausts_its_budget_fails_the_recording_once(store, clock):
    job = an_analysis(store)
    sent = []
    analyses = FailsAnalysis(times=10)
    for attempt in range(1, 4):
        analysis_worker(store, clock, analyses, sent)()
        clock.passes(retry_delay(attempt))

    stopped = store.loads(Job, job.job_id)
    assert (stopped.state, stopped.attempts, stopped.failed_permanently) == ("failed", 3, True)
    assert analysis_worker(store, clock, analyses, sent)() is None
    assert analyses.ran == 3
    assert store.loads(Recording, job.recording_id).state == "analysis_failed"
    failed = [error for state, error in entered(store, job.recording_id) if state == "analysis_failed"]
    assert failed == ["transcription: the transcriber did not answer"]


def test_an_analysis_that_exhausts_its_budget_tells_the_reviewer_why(store, clock):
    job = an_analysis(store)
    sent = []
    analyses = FailsAnalysis(times=10)
    for attempt in range(1, 4):
        analysis_worker(store, clock, analyses, sent)()
        clock.passes(retry_delay(attempt))

    told = store.lists(Notification, recording_id=job.recording_id)
    assert [(item.kind, item.recipient, item.state) for item in told] == [
        ("analysis_failed", "reviewer", "pending")
    ]
    assert "transcription" in told[0].summary
    assert "the transcriber did not answer" in told[0].summary
    assert sent == told


def test_an_unreachable_model_host_is_retried_like_any_other_failure(store, clock):
    job = an_analysis(store, max_attempts=2)
    analyses = FailsAnalysis(times=10, error=ModelEndpointUnreachable("http://100.88.211.71:11434"))
    analysis_worker(store, clock, analyses)()

    assert store.loads(Job, job.job_id).state == "queued"
    assert store.loads(Recording, job.recording_id).state == "downloaded"

    clock.passes(retry_delay(1))
    analysis_worker(store, clock, analyses)()

    assert store.loads(Job, job.job_id).failed_permanently
    assert store.loads(Recording, job.recording_id).state == "analysis_failed"
    failed = [error for state, error in entered(store, job.recording_id) if state == "analysis_failed"]
    assert len(failed) == 1 and "http://100.88.211.71:11434" in failed[0]


def test_an_undecodable_source_is_not_retried(store, clock):
    job = an_analysis(store)
    undecodable = StageFailed("transcription", "could not be decoded")
    undecodable.__cause__ = AudioNotDecodable("recordings/recording_20260823_102900/source.flac")
    analyses = FailsAnalysis(times=10, error=undecodable)
    analysis_worker(store, clock, analyses)()

    stopped = store.loads(Job, job.job_id)
    assert (stopped.state, stopped.attempts, stopped.failed_permanently) == ("failed", 1, True)
    assert store.loads(Recording, job.recording_id).state == "analysis_failed"
    clock.passes(retry_delay(1))
    assert analysis_worker(store, clock, analyses)() is None


def test_an_analysis_waiting_out_its_delay_does_not_hold_up_the_next(store, clock):
    waiting = an_analysis(store, recording_id="recording_20260823_102900")
    analyses = FailsAnalysis(times=1)
    analysis_worker(store, clock, analyses)()
    later = an_analysis(store, recording_id="recording_20260830_102900")

    analysis_worker(store, clock, analyses)()

    assert store.loads(Job, later.job_id).state == "succeeded"
    assert store.loads(Job, waiting.job_id).attempts == 1
    assert store.loads(Recording, waiting.recording_id).state == "downloaded"


def test_a_render_that_fails_within_its_budget_is_not_shown_as_failed(store, clock):
    job = a_render(store)
    renders = renders_with(store, clock, encodes_after(1))
    worker(store, clock, FetchesObject(), renders=renders)()

    assert store.loads(Segment, job.segment_id).state == "approved"
    assert store.lists(Notification) == []


def test_a_render_that_exhausts_its_budget_tells_the_reviewer_why(store, clock):
    job = a_render(store)
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    sent = []
    renders = RunsRenderJob(
        store=store,
        steps=encodes_after(10),
        notifies=SendsNotification(store=store, sends=sent.append),
        clock=clock,
    )
    for attempt in range(1, 4):
        worker(store, clock, FetchesObject(), renders=renders)()
        clock.passes(retry_delay(attempt))

    told = store.lists(Notification, segment_id=job.segment_id)
    assert [(item.kind, item.recipient) for item in told] == [("processing_failed", "reviewer")]
    assert "encode" in told[0].summary and "encoder crashed" in told[0].summary
    assert sent == told


def test_an_analysis_run_on_its_own_leaves_its_job_queued_for_the_worker(store, clock):
    job = an_analysis(store)
    analyzes_with(store, clock, FailsAnalysis(times=1), [])()

    assert store.loads(Job, job.job_id).state == "queued"
    assert store.loads(Recording, job.recording_id).state == "downloaded"


def test_a_render_run_on_its_own_leaves_its_job_queued_for_the_worker(store, clock):
    job = a_render(store)
    renders_with(store, clock, encodes_after(1))()

    assert store.loads(Job, job.job_id).state == "queued"
    assert store.loads(Segment, job.segment_id).state == "approved"


def test_a_render_chain_that_keeps_failing_fails_the_segment(store, clock, tmp_path):
    job = a_render(store)

    def chain_breaks(*_args, **_kwargs):
        raise RenderProducedNothing("published/2026-08-23 - Hebrews 12.4-11.mp3")

    renders = RunsRenderJob(
        store=store,
        steps=lambda _name: None,
        notifies=SendsNotification(store=store),
        clock=clock,
        renders=chain_breaks,
    )
    for attempt in range(1, 4):
        worker(store, clock, FetchesObject(), renders=renders)()
        clock.passes(retry_delay(attempt))

    assert store.loads(Job, job.job_id).failed_permanently
    assert store.loads(Segment, job.segment_id).state == "processing_failed"
    assert [item.kind for item in store.lists(Notification)] == ["processing_failed"]


def test_a_source_that_failed_to_decode_for_want_of_disk_is_retried(store, clock):
    job = an_analysis(store)
    decoding = AudioNotDecodable("recordings/recording_20260823_102900/source.flac")
    decoding.__cause__ = OSError(28, "No space left on device")
    undecoded = StageFailed("transcription", "could not be decoded")
    undecoded.__cause__ = decoding
    analysis_worker(store, clock, FailsAnalysis(times=10, error=undecoded))()

    assert store.loads(Job, job.job_id).state == "queued"
    assert store.loads(Recording, job.recording_id).state == "downloaded"


def test_an_analysis_whose_handler_crashed_is_retried_within_its_budget(store, clock):
    job = an_analysis(store)

    def explodes():
        raise RuntimeError("the worker lost its database handle")

    RunsQueuedJobs(
        store=store, downloads=explodes, analyzes=explodes, renders=explodes, clock=clock
    )()

    held = store.loads(Job, job.job_id)
    assert (held.state, held.attempts) == ("queued", 1)
