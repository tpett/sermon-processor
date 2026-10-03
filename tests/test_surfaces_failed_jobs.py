from datetime import UTC, date, datetime, timedelta

import pytest

from sermon.jobs.analyzes_recording import RunsAnalyzeJob, StageFailed
from sermon.jobs.renders_segment import RunsRenderJob, StepFailed
from sermon.jobs.runs_queued_jobs import RunsQueuedJobs
from sermon.sends_notification import SendsNotification
from sermon.store import Job, Recording, Reviewer, Segment, opens_store
from sermon.web import creates_app
from steps._markup import reads_field, reads_rows

STARTED = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
RECORDING_ID = "recording_20260913_090014"
EVERY_DELAY = timedelta(hours=1)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    opened.saves(Reviewer(actor="reviewer", receives_notifications=True))
    yield opened
    opened.close()


class Clock:
    def __init__(self):
        self.at = STARTED

    def __call__(self):
        return self.at


def a_recording(store, state):
    return store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=f"recordings/{RECORDING_ID}.flac",
            state=state,
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=10990.0,
        )
    )


def drains(store, clock, *, analyzes=None, renders=None):
    refuses = lambda: None  # noqa: E731
    runs = RunsQueuedJobs(
        store=store,
        downloads=refuses,
        analyzes=analyzes or refuses,
        renders=renders or refuses,
        clock=clock,
    )
    while store.lists(Job, state="queued"):
        runs()
        clock.at += EVERY_DELAY


def analysis_keeps_failing(store):
    a_recording(store, "downloaded")
    store.saves(
        Job(
            recording_id=RECORDING_ID,
            kind="analyze",
            state="queued",
            max_attempts=3,
            dedupe_key=f"analyze:{RECORDING_ID}",
            queued_at=STARTED,
        )
    )
    clock = Clock()

    def fails(_recording):
        raise StageFailed("transcription", "the transcriber did not answer")

    drains(
        store,
        clock,
        analyzes=RunsAnalyzeJob(
            store=store,
            stages=lambda _name: None,
            notifies=SendsNotification(store=store),
            clock=clock,
            analyses=fails,
        ),
    )


def render_keeps_failing(store):
    a_recording(store, "reviewed")
    segment = store.saves(
        Segment(
            recording_id=RECORDING_ID,
            classification="sermon",
            state="approved",
            span_start_seconds=1.0,
            span_end_seconds=3500.0,
            punch_in_seconds=1.0,
            punch_out_seconds=3500.0,
            intent="publish",
            label="Hebrews 12.25-29",
            publication_date=date(2026, 9, 13),
        )
    )
    store.saves(
        Job(
            recording_id=RECORDING_ID,
            segment_id=segment.segment_id,
            kind="render",
            state="queued",
            max_attempts=3,
            dedupe_key=f"render:{segment.segment_id}",
            queued_at=STARTED,
        )
    )
    clock = Clock()

    def steps(name):
        if name == "encode":
            raise StepFailed(name, "encoder crashed")

    drains(
        store,
        clock,
        renders=RunsRenderJob(
            store=store, steps=steps, notifies=SendsNotification(store=store), clock=clock
        ),
    )
    return segment


def client(store):
    return creates_app(store=store, clock=lambda: STARTED).test_client()


def test_the_detail_page_names_the_stage_and_error_analysis_failed_on(store):
    analysis_keeps_failing(store)
    page = client(store).get(f"/recordings/{RECORDING_ID}").get_data(as_text=True)

    assert reads_field(page, "state") == "analysis_failed"
    assert reads_field(page, "reason") == "transcription: the transcriber did not answer"


def test_the_detail_page_names_the_step_and_error_a_render_failed_on(store):
    segment = render_keeps_failing(store)
    page = client(store).get(
        f"/recordings/{RECORDING_ID}", query_string={"segment": segment.segment_id}
    ).get_data(as_text=True)

    assert reads_field(page, "segment-failure") == "encode: encoder crashed"


def test_the_list_marks_a_recording_whose_analysis_failed_and_says_why(store):
    analysis_keeps_failing(store)
    (row,) = reads_rows(client(store).get("/").get_data(as_text=True), "recording")

    assert row["failed"] == "true"
    assert row["row-failure"] == "transcription: the transcriber did not answer"


def test_the_list_marks_a_recording_one_of_whose_segments_failed_to_render(store):
    render_keeps_failing(store)
    (row,) = reads_rows(client(store).get("/").get_data(as_text=True), "recording")

    assert row["failed"] == "true"
    assert row["row-failure"] == "encode: encoder crashed"


def test_a_recording_still_being_retried_is_not_marked_failed(store):
    a_recording(store, "downloaded")
    (row,) = reads_rows(client(store).get("/").get_data(as_text=True), "recording")

    assert row["failed"] == "false"
    assert not row.get("row-failure")


def test_the_failed_filter_finds_a_recording_whose_segment_failed_to_render(store):
    render_keeps_failing(store)
    rows = reads_rows(client(store).get("/?filter=Failed").get_data(as_text=True), "recording")

    assert [row["id"] for row in rows] == [RECORDING_ID]

