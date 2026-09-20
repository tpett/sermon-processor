from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.jobs.analyzes_recording import CLASS_AND_SERVICE, RunsAnalyzeJob
from sermon.sends_notification import SendsNotification
from sermon.store import Job, LogEntry, Notification, Proposal, Recording, Reviewer, Segment

FROZEN = datetime(2026, 9, 13, 12, 41, tzinfo=UTC)


@pytest.fixture
def stage_log():
    return []


@pytest.fixture
def sent():
    return []


@pytest.fixture
def clock():
    return lambda: FROZEN


@given(parsers.parse("the Recording is {length} long"), target_fixture="recording")
def _(store, recording, length):
    hours, minutes, seconds = (int(part) for part in length.split(":"))
    return store.saves(
        replace(
            recording,
            duration_seconds=float(hours * 3600 + minutes * 60 + seconds),
        )
    )


@given("it contains a 9:00 class and the 10:30 service", target_fixture="contents")
def _():
    return CLASS_AND_SERVICE


def runs_analysis(store, recording, stage_log, sent, contents, clock):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}",
            queued_at=clock(),
        )
    )
    RunsAnalyzeJob(
        store=store,
        stages=stage_log.append,
        notifies=SendsNotification(store=store, sends=sent.append),
        contents=contents,
        clock=clock,
    )()


@when("Analysis starts")
def _(store, recording, stage_log, sent, contents, clock):
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@when("Analysis completes")
def _(store, recording, stage_log, sent, contents, clock):
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@then(parsers.parse('the Recording enters "{state}"'))
def _(store, recording, state):
    entered = [
        entry.entered_state
        for entry in store.lists(LogEntry, recording_id=recording.recording_id)
        if entry.entered_state is not None
    ]
    assert state in entered


@then("the following stages run in order:")
def _(stage_log, datatable):
    expected = [row[0] for row in datatable[1:]]
    first_seen = []
    for name in stage_log:
        if name not in first_seen:
            first_seen.append(name)
    assert first_seen == expected


@then("blocking and block_classification iterate until stable")
def _(stage_log):
    assert stage_log.count("blocking") >= 2
    assert stage_log.count("block_classification") >= 2


@then(parsers.parse('when scoring completes the Recording enters "{state}"'))
def _(store, recording, state):
    assert store.loads(Recording, recording.recording_id).state == state


@then("a notification is sent to the reviewers unless nothing publishable was found")
def _(store, recording, sent):
    notifications = store.lists(Notification, recording_id=recording.recording_id)
    assert notifications
    assert sent == notifications


@then(parsers.parse("{count:d} Segments exist"))
def _(store, recording, count):
    assert len(store.lists(Segment, recording_id=recording.recording_id)) == count


@then("each Segment has its own punch-in, punch-out, classification and confidence")
def _(store, recording):
    segments = store.lists(Segment, recording_id=recording.recording_id)
    punches = {(segment.punch_in_seconds, segment.punch_out_seconds) for segment in segments}
    classes = {segment.classification for segment in segments}
    assert len(punches) == len(segments)
    assert len(classes) == len(segments)
    for segment in segments:
        proposals = store.lists(Proposal, segment_id=segment.segment_id)
        assert len(proposals) == 1
        assert proposals[0].classification_confidence in {"high", "medium", "low"}
        assert proposals[0].boundary_confidence in {"high", "medium", "low"}


@then("each Segment is independently dispositionable")
def _(store, recording):
    assert len(store.lists(Segment, recording_id=recording.recording_id)) == 2


@then("approving one does not affect the other")
def _(store, recording):
    segments = store.lists(Segment, recording_id=recording.recording_id)
    store.saves(replace(segments[0], state="approved"))
    other = store.loads(Segment, segments[1].segment_id)
    assert other.state == "proposed"
