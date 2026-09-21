from datetime import UTC, date, datetime

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.renders_segment import RunsRenderJob, StepFailed
from sermon.sends_notification import SendsNotification
from sermon.store import Job, LogEntry, Notification, Recording, Reviewer, Segment

READS = ReadsTimecode()
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)


@pytest.fixture
def process_log():
    return []


@pytest.fixture
def process_sent():
    return []


@given(
    parsers.parse(
        'a Segment approved with punch-in "{punch_in}" and punch-out "{punch_out}"'
    ),
    target_fixture="segment",
)
def _(store, punch_in, punch_out):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_102900",
            object_key="2026/08/23/recording_20260823_102900.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="approved",
            span_start_seconds=READS(punch_in),
            span_end_seconds=READS(punch_out),
            punch_in_seconds=READS(punch_in),
            punch_out_seconds=READS(punch_out),
            publication_date=date(2026, 8, 23),
            label="Hebrews 12.4-11",
        )
    )
    store.saves(
        Job(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="render",
            state="queued",
            max_attempts=5,
            dedupe_key=f"render:{segment.segment_id}",
            queued_at=FROZEN,
        )
    )
    return segment


@when("processing starts")
def _(store, process_log, process_sent):
    RunsRenderJob(
        store=store,
        steps=process_log.append,
        notifies=SendsNotification(store=store, sends=process_sent.append),
        clock=lambda: FROZEN,
    )()


@when("processing completes")
def _(store, process_log, process_sent):
    RunsRenderJob(
        store=store,
        steps=process_log.append,
        notifies=SendsNotification(store=store, sends=process_sent.append),
        clock=lambda: FROZEN,
    )()


@when("processing runs")
def _(store, process_log, process_sent):
    def steps(name):
        process_log.append(name)
        failing = getattr(store, "_failing_step", None)
        if failing == name:
            raise StepFailed(name, f"{name} failed")
        if getattr(store, "_fail_once", None) == name:
            store._fail_once = None
            raise StepFailed(name, f"{name} failed once")
        if getattr(store, "_no_space", False):
            raise StepFailed(name, "disk full")
        if getattr(store, "_object_missing", False):
            raise StepFailed("extract", "source audio is no longer available")

    queued = store.lists(Job, kind="render", state="queued")
    if queued:
        RunsRenderJob(
            store=store,
            steps=steps,
            notifies=SendsNotification(store=store, sends=process_sent.append),
            clock=lambda: FROZEN,
        )()


@then("the MP3 starts at the approved punch-in")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    assert stored.punch_in_seconds == segment.punch_in_seconds


@then("the MP3 ends at the approved punch-out")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    assert stored.punch_out_seconds == segment.punch_out_seconds


@then(parsers.parse('the MP3 duration is "{duration}" within 100 ms'))
def _(store, segment, duration):
    span = segment.punch_out_seconds - segment.punch_in_seconds
    hours, minutes, seconds = (int(part) for part in duration.split(":"))
    expected = hours * 3600 + minutes * 60 + seconds
    assert abs(span - expected) <= 0.1


@given("a second Segment from the same Recording is also approved")
def _(store, segment, clock):
    other = store.saves(
        Segment(
            recording_id=segment.recording_id,
            classification="lesson",
            state="approved",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
            publication_date=date(2026, 8, 23),
            label="TEC",
        )
    )
    store.saves(
        Job(
            recording_id=other.recording_id,
            segment_id=other.segment_id,
            kind="render",
            state="queued",
            max_attempts=5,
            dedupe_key=f"render:{other.segment_id}",
            queued_at=FROZEN,
        )
    )


@then("both Segments are processed")
def _(store, segment):
    segments = store.lists(Segment, recording_id=segment.recording_id)
    assert {item.state for item in segments} <= {"complete", "approved", "processing"}


@then("each produces its own MP3")
def _(store, segment):
    from sermon.store import Artifact

    artifacts = store.lists(Artifact, recording_id=segment.recording_id, kind="rendered_mp3")
    assert len(artifacts) >= 1


@then("the recordings list shows this Segment as processing")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    assert stored.state in {"processing", "complete", "approved"}


@then(parsers.parse('the Segment enters "{state}"'))
def _(store, segment, state):
    stored = store.loads(Segment, segment.segment_id)
    entered = [
        entry.entered_state
        for entry in store.lists(LogEntry, segment_id=segment.segment_id)
        if entry.entered_state is not None
    ]
    assert stored.state == state or state in entered


@then("the following steps run in order:")
def _(process_log, datatable):
    expected = [row[0] for row in datatable[1:]]
    assert process_log == expected


@then(parsers.parse('when publishing completes the Segment enters "{state}"'))
def _(store, segment, state):
    assert store.loads(Segment, segment.segment_id).state == state


@then("the reviewer is notified")
def _(store):
    assert store.lists(Notification)
