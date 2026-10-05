from datetime import UTC, datetime

import pytest

from sermon.adjusts_punch_point import (
    AdjustsPunchPoint,
    BoundaryWouldStrandARemovedSpan,
    RevertsToProposal,
)
from sermon.removes_span import RemovesSpan, kept_pieces, kept_seconds
from sermon.splits_segment import MergesSegments, SplitPointInsideRemovedSpan, SplitsSegment
from sermon.store import RemovedSpan, Recording, Segment, opens_store

FROZEN = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def segment(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20261004_095800",
            object_key="recordings/recording_20261004_095800.flac",
            state="awaiting_review",
            started_at=datetime(2026, 10, 4, 9, 58, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=7200.0,
        )
    )
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=3000.0,
            span_end_seconds=6000.0,
            punch_in_seconds=3100.0,
            punch_out_seconds=5800.0,
            boundary_source="refined",
        )
    )


def removes(store, segment, *spans):
    for start, end in spans:
        segment = RemovesSpan(store=store, clock=lambda: FROZEN)(
            segment, start_seconds=start, end_seconds=end
        )
    return segment


def test_what_ships_is_the_cut_less_its_removed_spans(store, segment):
    held = removes(store, segment, (4000.0, 4600.0), (3105.0, 3105.5))
    assert kept_pieces(held.punch_in_seconds, held.punch_out_seconds, held.removed_spans) == (
        (3100.0, 3105.0),
        (3105.5, 4000.0),
        (4600.0, 5800.0),
    )
    assert kept_seconds(held) == pytest.approx(2700.0 - 600.5)


def test_removed_spans_are_held_in_the_order_they_fall(store, segment):
    held = removes(store, segment, (4000.0, 4600.0), (3105.0, 3105.5))
    assert [span.start_seconds for span in held.removed_spans] == [3105.0, 4000.0]


def test_reverting_to_the_proposal_is_refused_where_it_would_strand_a_span(store, segment):
    AdjustsPunchPoint(store=store, clock=lambda: FROZEN)(segment, punch_in_seconds=3050.0)
    adjusted = removes(store, store.loads(Segment, segment.segment_id), (3060.0, 3061.0))
    with pytest.raises(BoundaryWouldStrandARemovedSpan):
        RevertsToProposal(store=store, clock=lambda: FROZEN)(adjusted)


def test_a_split_hands_each_half_the_spans_inside_it(store, segment):
    held = removes(store, segment, (3105.0, 3105.5), (5000.0, 5100.0))
    earlier, later = SplitsSegment(store=store)(held, at_seconds=4500.0)
    assert earlier.removed_spans == (RemovedSpan(start_seconds=3105.0, end_seconds=3105.5),)
    assert later.removed_spans == (RemovedSpan(start_seconds=5000.0, end_seconds=5100.0),)


def test_a_split_inside_a_removed_span_is_refused(store, segment):
    held = removes(store, segment, (5000.0, 5100.0))
    with pytest.raises(SplitPointInsideRemovedSpan):
        SplitsSegment(store=store)(held, at_seconds=5050.0)


def test_a_merge_keeps_the_spans_both_halves_removed(store, segment):
    held = removes(store, segment, (3105.0, 3105.5), (5000.0, 5100.0))
    earlier, later = SplitsSegment(store=store)(held, at_seconds=4500.0)
    merged = MergesSegments(store=store)(earlier, later)
    assert merged.removed_spans == held.removed_spans
