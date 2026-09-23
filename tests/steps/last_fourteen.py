from dataclasses import replace
from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment
from sermon.store import Proposal, Recording, Segment
from steps import _web


@given("a Recording of 104 minutes")
def _(store):
    store.saves(
        Recording(
            recording_id="recording_20260816_090014",
            object_key="recordings/recording_20260816_090014.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 16, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=6240.0,
        )
    )


@given("one of its Segments was skipped")
def _(store, recording):
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="lesson",
            state="skipped",
            span_start_seconds=1.0,
            span_end_seconds=3497.0,
            punch_in_seconds=1.0,
            punch_out_seconds=3497.0,
        )
    )
    store.saves(
        Proposal(
            segment_id=segment.segment_id,
            classification_confidence="high",
            boundary_confidence="high",
            punch_in_grade="easy",
            punch_out_grade="easy",
        )
    )
    store._revisited = segment


@when("I revisit that Segment")
def _(store, recording):
    segment = store._revisited
    store.saves(replace(segment, state="proposed"))
    store.saves(replace(store.loads(Recording, recording.recording_id), state="awaiting_review"))


@then('the Segment returns to "proposed"')
def _(store):
    assert store.loads(Segment, store._revisited.segment_id).state == "proposed"


@then('the Recording returns to "awaiting_review"')
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state == "awaiting_review"


@then("its boundaries, classification, summary and evidence are unchanged")
def _(store):
    assert store.loads(Segment, store._revisited.segment_id).classification == "lesson"


@then("no re-analysis is needed")
def _(store):
    from sermon.store import Job

    assert not [job for job in store.lists(Job, kind="analyze") if job.state == "queued"]


@when("a reviewer approves it now")
def _(store, clock):
    skipped = [item for item in store.lists(Segment) if item.state == "skipped"]
    if skipped:
        ApprovesSegment(store=store, clock=clock)(skipped[0])


@when("I revert it to proposed", target_fixture="detail_page")
def _(store, recording):
    approved = [
        one
        for one in store.lists(Segment, recording_id=recording.recording_id)
        if one.state == "approved"
    ]
    return _web.posts(store, _web.segment_action(approved[0], "reopen"))


@given("I approved Segment 2 a moment ago")
def _(store, recording, clock):
    segments = sorted(
        store.lists(Segment, recording_id=recording.recording_id),
        key=lambda item: item.span_start_seconds,
    )
    if segments:
        ApprovesSegment(store=store, clock=clock)(segments[-1])
