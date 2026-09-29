from datetime import UTC, datetime

import pytest

from sermon.adjusts_punch_point import BoundaryOutsideSegment
from sermon.extends_segment_span import (
    PROPOSAL_MARGIN_SECONDS,
    ExtendsSegmentSpan,
    ReadsTimecode,
    SpanWouldOverlapNeighbour,
    WidensProposedSpan,
)
from sermon.places_punch_in import PlacesPunchIn
from sermon.store import Recording, Segment, opens_store

READS = ReadsTimecode()


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def a_recording(store, recording_id="recording_20260913_090014"):
    return store.saves(
        Recording(
            recording_id=recording_id,
            object_key=f"{recording_id}.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )


def a_segment(
    store,
    recording,
    *,
    classification="sermon",
    start,
    end,
    punch_in=None,
    punch_out=None,
):
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=classification,
            state="proposed",
            span_start_seconds=start,
            span_end_seconds=end,
            punch_in_seconds=start if punch_in is None else punch_in,
            punch_out_seconds=end if punch_out is None else punch_out,
        )
    )


def the_selected_segment(store, recording):
    return a_segment(
        store,
        recording,
        start=READS("1:28:40"),
        end=READS("3:12:00"),
        punch_in=READS("2:00:20.000"),
        punch_out=READS("2:43:32.000"),
    )


def test_reads_the_timecodes_the_scenario_quotes():
    assert READS("1:26:00") == 5160.0
    assert READS("1:28:40") == 5320.0
    assert READS("3:12:00") == 11520.0
    assert READS("2:00:20.000") == 7220.0
    assert READS("2:43:32.000") == 9812.0


def test_extending_the_start_grows_the_span_and_leaves_the_punch_points(store):
    segment = the_selected_segment(store, a_recording(store))
    grown = ExtendsSegmentSpan(store=store)(segment, start_seconds=READS("1:26:00"))
    assert (grown.span_start_seconds, grown.span_end_seconds) == (
        READS("1:26:00"),
        READS("3:12:00"),
    )
    assert (grown.punch_in_seconds, grown.punch_out_seconds) == (
        segment.punch_in_seconds,
        segment.punch_out_seconds,
    )


def test_a_punch_in_may_sit_anywhere_the_old_span_did_not_cover(store):
    segment = the_selected_segment(store, a_recording(store))
    grown = ExtendsSegmentSpan(store=store)(segment, start_seconds=READS("1:26:00"))
    newly_covered = (
        grown.span_start_seconds,
        READS("1:27:00"),
        segment.span_start_seconds - 0.05,
    )
    assert len(set(newly_covered)) == len(newly_covered)
    for earlier in newly_covered:
        assert not (segment.span_start_seconds <= earlier <= segment.span_end_seconds)
        placed = PlacesPunchIn(store=store)(grown, punch_in_seconds=earlier)
        assert placed.punch_in_seconds == earlier
        stored = store.loads(Segment, grown.segment_id)
        assert stored.punch_in_seconds == earlier


def test_extending_into_a_neighbouring_segment_is_refused(store):
    recording = a_recording(store)
    segment = the_selected_segment(store, recording)
    a_segment(
        store,
        recording,
        classification="lesson",
        start=READS("1:00:00"),
        end=READS("1:26:00"),
    )
    with pytest.raises(SpanWouldOverlapNeighbour, match="neighbouring Segment"):
        ExtendsSegmentSpan(store=store)(segment, start_seconds=READS("1:25:00"))


def test_covering_a_neighbour_is_refused(store):
    recording = a_recording(store)
    segment = the_selected_segment(store, recording)
    a_segment(
        store,
        recording,
        classification="lesson",
        start=READS("1:00:00"),
        end=READS("1:26:00"),
    )
    with pytest.raises(SpanWouldOverlapNeighbour, match="neighbouring Segment"):
        ExtendsSegmentSpan(store=store)(segment, start_seconds=READS("0:50:00"))


def test_the_stored_span_is_unchanged_when_overlap_is_refused(store):
    recording = a_recording(store)
    segment = the_selected_segment(store, recording)
    a_segment(
        store,
        recording,
        classification="lesson",
        start=READS("1:00:00"),
        end=READS("1:26:00"),
    )
    with pytest.raises(SpanWouldOverlapNeighbour):
        ExtendsSegmentSpan(store=store)(segment, start_seconds=READS("1:25:00"))
    stored = store.loads(Segment, segment.segment_id)
    assert stored.span_start_seconds == segment.span_start_seconds


def test_touching_a_neighbour_at_a_shared_boundary_is_allowed(store):
    recording = a_recording(store)
    segment = the_selected_segment(store, recording)
    a_segment(
        store,
        recording,
        classification="lesson",
        start=READS("1:00:00"),
        end=READS("1:26:00"),
    )
    grown = ExtendsSegmentSpan(store=store)(segment, start_seconds=READS("1:26:00"))
    assert grown.span_start_seconds == READS("1:26:00")


def test_a_segment_on_another_recording_does_not_block_an_extend(store):
    segment = the_selected_segment(store, a_recording(store))
    a_segment(
        store,
        a_recording(store, recording_id="recording_20260920_090000"),
        classification="lesson",
        start=READS("1:00:00"),
        end=READS("1:30:00"),
    )
    grown = ExtendsSegmentSpan(store=store)(segment, start_seconds=READS("1:26:00"))
    assert grown.span_start_seconds == READS("1:26:00")


def test_extending_the_end_into_a_neighbour_is_refused(store):
    recording = a_recording(store)
    segment = the_selected_segment(store, recording)
    a_segment(
        store,
        recording,
        classification="lesson",
        start=READS("3:12:00"),
        end=READS("4:00:00"),
    )
    with pytest.raises(SpanWouldOverlapNeighbour, match="neighbouring Segment"):
        ExtendsSegmentSpan(store=store)(segment, end_seconds=READS("3:13:00"))


def test_the_store_still_saves_overlapping_spans(store):
    recording = a_recording(store)
    the_selected_segment(store, recording)
    overlapping = a_segment(
        store,
        recording,
        classification="lesson",
        start=READS("1:00:00"),
        end=READS("1:30:00"),
    )
    stored = store.loads(Segment, overlapping.segment_id)
    assert stored.span_end_seconds == READS("1:30:00")


def test_a_span_that_would_strand_the_punch_in_is_refused(store):
    segment = the_selected_segment(store, a_recording(store))
    with pytest.raises(BoundaryOutsideSegment, match="within the Segment"):
        ExtendsSegmentSpan(store=store)(segment, start_seconds=READS("2:10:00"))
    stored = store.loads(Segment, segment.segment_id)
    assert stored.span_start_seconds == segment.span_start_seconds


def test_a_span_that_would_strand_the_punch_out_is_refused(store):
    segment = the_selected_segment(store, a_recording(store))
    with pytest.raises(BoundaryOutsideSegment, match="within the Segment"):
        ExtendsSegmentSpan(store=store)(segment, end_seconds=READS("2:30:00"))
    stored = store.loads(Segment, segment.segment_id)
    assert stored.span_end_seconds == segment.span_end_seconds


def test_a_span_may_still_be_tightened_onto_its_punch_points(store):
    segment = the_selected_segment(store, a_recording(store))
    tightened = ExtendsSegmentSpan(store=store)(
        segment,
        start_seconds=segment.punch_in_seconds,
        end_seconds=segment.punch_out_seconds,
    )
    assert tightened.span_start_seconds == segment.punch_in_seconds
    assert tightened.span_end_seconds == segment.punch_out_seconds


PRODUCTION_PUNCHES = (3060.83, 5594.575)
PRODUCTION_DURATION = 6791.607619
WORST_MEASURED_PUNCH_IN_ERROR = 118.887


def a_proposal(store, recording, punch_in, punch_out):
    return Segment(
        recording_id=recording.recording_id,
        classification="sermon",
        state="proposed",
        span_start_seconds=punch_in,
        span_end_seconds=punch_out,
        punch_in_seconds=punch_in,
        punch_out_seconds=punch_out,
        boundary_source="model",
    )


def test_a_proposed_span_is_born_with_room_on_both_edges(store):
    recording = a_recording(store)
    roomy = WidensProposedSpan(store=store)(
        a_proposal(store, recording, *PRODUCTION_PUNCHES), PRODUCTION_DURATION
    )
    assert PRODUCTION_PUNCHES[0] - roomy.span_start_seconds >= WORST_MEASURED_PUNCH_IN_ERROR
    assert roomy.span_end_seconds - PRODUCTION_PUNCHES[1] >= WORST_MEASURED_PUNCH_IN_ERROR
    assert roomy.span_start_seconds == PRODUCTION_PUNCHES[0] - PROPOSAL_MARGIN_SECONDS
    assert roomy.span_end_seconds == PRODUCTION_PUNCHES[1] + PROPOSAL_MARGIN_SECONDS


def test_the_room_never_reaches_before_the_recording_starts(store):
    recording = a_recording(store)
    roomy = WidensProposedSpan(store=store)(a_proposal(store, recording, 4.0, 600.0), 3600.0)
    assert roomy.span_start_seconds == 0.0


def test_the_room_never_reaches_past_the_recording_end(store):
    recording = a_recording(store)
    roomy = WidensProposedSpan(store=store)(a_proposal(store, recording, 400.0, 3500.0), 3600.0)
    assert roomy.span_end_seconds == 3600.0


def test_the_room_stops_at_a_neighbouring_segment(store):
    recording = a_recording(store)
    a_segment(store, recording, start=0.0, end=1000.0)
    a_segment(store, recording, start=4000.0, end=5000.0)
    roomy = WidensProposedSpan(store=store)(
        a_proposal(store, recording, 1050.0, 3950.0), PRODUCTION_DURATION
    )
    assert roomy.span_start_seconds == 1000.0
    assert roomy.span_end_seconds == 4000.0


def test_the_room_a_proposal_is_born_with_is_never_refused_as_an_overlap(store):
    recording = a_recording(store)
    a_segment(store, recording, start=0.0, end=1000.0)
    roomy = store.saves(
        WidensProposedSpan(store=store)(
            a_proposal(store, recording, 1050.0, 3950.0), PRODUCTION_DURATION
        )
    )
    grown = ExtendsSegmentSpan(store=store)(roomy, start_seconds=roomy.span_start_seconds)
    assert grown.span_start_seconds == roomy.span_start_seconds
