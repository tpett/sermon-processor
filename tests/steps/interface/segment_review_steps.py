from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment, ReviewSession
from sermon.skips_segment import SkipsSegment
from sermon.extends_segment_span import ReadsTimecode
from sermon.store import Block, Job, Proposal, Recording, Segment

READS = ReadsTimecode()


@pytest.fixture
def review_session():
    return ReviewSession()


def parses_boundaries(text):
    start, end = text.split(" – ")
    return READS(start.strip()), READS(end.strip())


@given(
    parsers.parse('a Recording in state "{state}" containing {count:d} Segments:'),
    target_fixture="recording",
)
def _(store, state, count, datatable):
    stored = store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="2026/09/13/recording_20260913_090014.flac",
            state=state,
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    rows = datatable[1:]
    assert len(rows) == count
    for _, classification, boundaries, confidence in rows:
        start, end = parses_boundaries(boundaries)
        segment = store.saves(
            Segment(
                recording_id=stored.recording_id,
                classification=classification,
                state="proposed",
                span_start_seconds=start,
                span_end_seconds=end,
                punch_in_seconds=start,
                punch_out_seconds=end,
            )
        )
        store.saves(
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence=confidence,
                boundary_confidence=confidence,
                punch_in_grade="moderate",
                punch_out_grade="moderate",
            )
        )
    return stored


@given("its remaining Blocks are music, prayer, qa and communion")
def _(store, recording):
    start = 0.0
    for block_type in ("music", "prayer", "qa", "communion"):
        store.saves(
            Block(
                recording_id=recording.recording_id,
                start_seconds=start,
                end_seconds=start + 60.0,
                type=block_type,
            )
        )
        start += 60.0


@given(
    parsers.parse('a Segment classified "{classification}" whose cuts are both graded "{grade}"'),
    target_fixture="segment",
)
def _(store, recording, classification, grade):
    segment = [
        item
        for item in store.lists(Segment, recording_id=recording.recording_id)
        if item.classification == classification
    ][0]
    proposal = store.lists(Proposal, segment_id=segment.segment_id)[0]
    store.saves(replace(proposal, punch_in_grade=grade, punch_out_grade=grade))
    return segment


@when("I preview the punch-in")
def _(review_session, segment):
    review_session.previews_punch_in(segment)


@when("I preview the punch-out")
def _(review_session, segment):
    review_session.previews_punch_out(segment)


@when("I approve")
def _(store, segment, clock):
    ApprovesSegment(store=store, clock=clock)(segment)


@then("the Segment is queued for processing")
def _(store, segment):
    jobs = store.lists(Job, segment_id=segment.segment_id, kind="render")
    assert len(jobs) == 1
    assert jobs[0].state == "queued"
    assert store.loads(Segment, segment.segment_id).state == "approved"


@then("I did not have to open the waveform editor")
def _(review_session):
    assert review_session.waveform_editor_opened is False


def numbered_segment(store, recording, number):
    segments = sorted(
        store.lists(Segment, recording_id=recording.recording_id),
        key=lambda item: item.span_start_seconds,
    )
    return segments[number - 1]


@when(parsers.parse("I approve Segment {number:d}"))
def _(store, recording, number, clock):
    ApprovesSegment(store=store, clock=clock)(numbered_segment(store, recording, number))


@when(parsers.parse("I skip Segment {number:d}"))
def _(store, recording, number, clock):
    SkipsSegment(store=store, clock=clock)(numbered_segment(store, recording, number))


@then(parsers.parse('Segment {number:d} enters "{state}" and is queued for processing'))
def _(store, recording, number, state):
    segment = numbered_segment(store, recording, number)
    assert store.loads(Segment, segment.segment_id).state == state
    jobs = store.lists(Job, segment_id=segment.segment_id, kind="render")
    assert jobs[0].state == "queued"


@then(parsers.parse('Segment {number:d} enters "{state}"'))
def _(store, recording, number, state):
    segment = numbered_segment(store, recording, number)
    assert store.loads(Segment, segment.segment_id).state == state


@then("exactly one MP3 will be produced")
def _(store, recording):
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="render")
    assert len(jobs) == 1


@then("two separate processing jobs are queued")
def _(store, recording):
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="render")
    assert len(jobs) == 2


@then("two separate MP3s will be produced")
def _(store, recording):
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="render")
    assert len({job.segment_id for job in jobs}) == 2


@then("each carries its own publication details")
def _(store, recording):
    segments = store.lists(Segment, recording_id=recording.recording_id)
    assert len(segments) == 2

