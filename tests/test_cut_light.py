"""The cut light's sides, which the scenario cannot reach.

`A cut light shows the exact instant` auditions the punch-in, so it pins the
punch-in's sides and nothing else. Swapping the punch-out's sides left the whole
605-scenario suite green, which is the sort of silence that ships a confident lie:
a punch-out keeps what *precedes* it, and a reviewer told otherwise would discard
the sermon and keep the communion.
"""

from datetime import UTC, datetime

import pytest

from sermon.shows_recording import ShowsRecording
from sermon.store import Proposal, Recording, Segment, opens_store

PUNCH_IN = 1165.70
PUNCH_OUT = 4243.78


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def segment(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260712_103000",
            object_key="recordings/recording_20260712_103000.flac",
            state="awaiting_review",
            started_at=datetime(2026, 7, 12, 10, 30, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=5391.86,
        )
    )
    saved = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=PUNCH_IN,
            span_end_seconds=PUNCH_OUT,
            punch_in_seconds=PUNCH_IN,
            punch_out_seconds=PUNCH_OUT,
        )
    )
    store.saves(
        Proposal(
            segment_id=saved.segment_id,
            classification_confidence="high",
            boundary_confidence="high",
            punch_in_grade="easy",
            punch_out_grade="easy",
        )
    )
    return saved


def light_at(store, playhead):
    return ShowsRecording(store=store)(
        "recording_20260712_103000", playhead_seconds=playhead
    ).cut_light


def test_before_a_punch_in_is_discarded(store, segment):
    light = light_at(store, PUNCH_IN - 2.30)
    assert (light.boundary, light.state, light.side) == ("punch-in", "before", "discarded")
    assert light.offset == "−2.30 s"
    assert (light.discards, light.keeps) == ("before the cut", "after the cut")


def test_after_a_punch_in_is_kept(store, segment):
    light = light_at(store, PUNCH_IN + 1.42)
    assert (light.state, light.side) == ("after", "kept")
    assert light.offset == "+1.42 s"


def test_before_a_punch_out_is_kept(store, segment):
    light = light_at(store, PUNCH_OUT - 2.00)
    assert light.boundary == "punch-out"
    assert (light.state, light.side) == ("before", "kept")
    assert (light.discards, light.keeps) == ("after the cut", "before the cut")


def test_after_a_punch_out_is_discarded(store, segment):
    light = light_at(store, PUNCH_OUT + 1.22)
    assert light.boundary == "punch-out"
    assert (light.state, light.side) == ("after", "discarded")
    assert light.offset == "+1.22 s"


def test_the_instant_itself_is_neither_side(store, segment):
    light = light_at(store, PUNCH_IN)
    assert (light.state, light.side, light.offset) == ("at", "on the cut", "0.00 s")


def test_the_tolerance_is_narrower_than_the_placeable_precision(store, segment):
    """The spec calls 100 ms the precision a boundary can be placed to, so a
    light that read "at" across a wider window would claim the cut early."""
    light = light_at(store, PUNCH_IN)
    assert light.tolerance_seconds < 0.100
    assert light_at(store, PUNCH_IN + light.tolerance_seconds).state == "at"
    assert light_at(store, PUNCH_IN + light.tolerance_seconds * 2).state == "after"


def test_the_nearer_boundary_is_the_one_tracked(store, segment):
    midpoint = (PUNCH_IN + PUNCH_OUT) / 2
    assert light_at(store, midpoint - 1).boundary == "punch-in"
    assert light_at(store, midpoint + 1).boundary == "punch-out"
