from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import (
    ExtendsSegmentSpan,
    ReadsTimecode,
    SpanWouldOverlapNeighbour,
)
from sermon.places_punch_in import PlacesPunchIn
from sermon.store import Recording, Segment, opens_store

READS = ReadsTimecode()


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@given("I am on the tailnet")
def _():
    return None


@given(parsers.re('^a Recording in state "(?P<state>[^"]+)"$'), target_fixture="recording")
def _(store, state):
    return store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="2026/09/13/recording_20260913_090014.flac",
            state=state,
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )


@given(
    parsers.parse(
        'I have selected a Segment classified "{classification}" spanning "{start}" to "{end}"'
    ),
    target_fixture="segment",
)
def _(store, recording, classification, start, end):
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=classification,
            state="proposed",
            span_start_seconds=READS(start),
            span_end_seconds=READS(end),
            punch_in_seconds=READS(start),
            punch_out_seconds=READS(end),
        )
    )


@given(
    parsers.parse('its punch-in is "{punch_in}" and punch-out is "{punch_out}"'),
    target_fixture="segment",
)
def _(store, segment, punch_in, punch_out):
    return store.saves(
        replace(
            segment,
            punch_in_seconds=READS(punch_in),
            punch_out_seconds=READS(punch_out),
        )
    )


@when(
    parsers.parse("I extend the Segment's own start to \"{timecode}\""),
    target_fixture="extended_segment",
)
def _(store, segment, timecode):
    return ExtendsSegmentSpan(store=store)(segment, start_seconds=READS(timecode))


@then("the Segment's span grows")
def _(segment, extended_segment):
    assert extended_segment.span_start_seconds < segment.span_start_seconds
    assert extended_segment.span_end_seconds == segment.span_end_seconds


@then("the punch-in may now be placed anywhere within the new span")
def _(store, extended_segment):
    placed = PlacesPunchIn(store=store)(
        extended_segment, punch_in_seconds=READS("1:27:00")
    )
    assert placed.punch_in_seconds == READS("1:27:00")
    stored = store.loads(Segment, extended_segment.segment_id)
    assert stored.punch_in_seconds == READS("1:27:00")


@then("the change is rejected if it would overlap the neighbouring Segment")
def _(store, recording, extended_segment):
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="lesson",
            state="proposed",
            span_start_seconds=READS("1:00:00"),
            span_end_seconds=READS("1:26:00"),
            punch_in_seconds=READS("1:00:00"),
            punch_out_seconds=READS("1:26:00"),
        )
    )
    with pytest.raises(SpanWouldOverlapNeighbour) as rejected:
        ExtendsSegmentSpan(store=store)(
            extended_segment, start_seconds=READS("1:25:00")
        )
    assert str(rejected.value) == "it would overlap the neighbouring Segment"
    stored = store.loads(Segment, extended_segment.segment_id)
    assert stored.span_start_seconds == READS("1:26:00")
