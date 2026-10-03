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
    held = {item.classification: item for item in store.lists(Segment, recording_id=recording.recording_id)}
    assert set(held) == {"lesson", "sermon"}
    _web.posts(store, _web.segment_action(held["lesson"], "skip"))
    _web.posts(store, _web.segment_action(held["sermon"], "approve"), intent="archive")
    assert store.loads(Recording, recording.recording_id).state == "reviewed"


def the_skipped_segment(store):
    skipped = [item for item in store.lists(Segment) if item.classification == "lesson"]
    assert len(skipped) == 1
    return skipped[0]


@when("I revisit that Segment")
def _(store, recording):
    segment = the_skipped_segment(store)
    store._before_revisit = (segment, tuple(store.lists(Proposal, segment_id=segment.segment_id)))
    _web.posts(store, _web.segment_action(segment, "reopen"))


@then('the Segment returns to "proposed"')
def _(store):
    assert the_skipped_segment(store).state == "proposed"


@then('the Recording returns to "awaiting_review"')
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state == "awaiting_review"


@then("its boundaries, classification, summary and evidence are unchanged")
def _(store):
    before, proposals = store._before_revisit
    after = the_skipped_segment(store)
    assert replace(after, state=before.state, disposition_at=before.disposition_at) == before
    assert tuple(store.lists(Proposal, segment_id=after.segment_id)) == proposals


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
