from datetime import UTC, date, datetime

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.renders_segment import RunsRenderJob
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


@then(parsers.parse('the Segment enters "{state}"'))
def _(store, segment, state):
    entered = [
        entry.entered_state
        for entry in store.lists(LogEntry, segment_id=segment.segment_id)
        if entry.entered_state is not None
    ]
    assert state in entered


@then("the following steps run in order:")
def _(process_log, datatable):
    expected = [row[0] for row in datatable[1:]]
    assert process_log == expected


@then(parsers.parse('when publishing completes the Segment enters "{state}"'))
def _(store, segment, state):
    assert store.loads(Segment, segment.segment_id).state == state


@then("the reviewer is notified")
def _(store, segment, process_sent):
    notifications = store.lists(Notification, segment_id=segment.segment_id)
    assert notifications
    assert process_sent == notifications
