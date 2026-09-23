from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.adjusts_punch_point import reads_boundary_history
from sermon.extends_segment_span import (
    ExtendsSegmentSpan,
    ReadsTimecode,
    SpanWouldOverlapNeighbour,
)
from sermon.places_punch_in import PlacesPunchIn
from sermon.shows_recording import NOTICES, formats_precise
from sermon.store import Proposal, Recording, Segment, opens_store
from steps._markup import reads_field, reads_rows
from steps import _web

READS = ReadsTimecode()
REFUSALS = frozenset(
    NOTICES[name] for name in NOTICES if name == NOTICES[name]
)


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
            duration_seconds=READS("3:12:00"),
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


@pytest.fixture
def detail_page(store, segment):
    return _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)


@when(parsers.parse('I try to set the punch-out to "{timecode}"'), target_fixture="detail_page")
def _(store, segment, timecode):
    return _web.posts(store, _web.boundary_action(segment, "punch-out"), do="set", timecode=timecode)


@when(parsers.parse('I try to set the "{boundary}" to "{timecode}"'), target_fixture="detail_page")
def _(store, segment, boundary, timecode):
    return _web.posts(store, _web.boundary_action(segment, boundary), do="set", timecode=timecode)


@when("I try to set a span shorter than 1 second", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(
        store,
        _web.boundary_action(segment, "punch-out"),
        do="set",
        timecode=formats_precise(segment.punch_in_seconds + 0.4),
    )


@when("I set a span of 6 minutes", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(
        store,
        _web.boundary_action(segment, "punch-out"),
        do="set",
        timecode=formats_precise(segment.punch_in_seconds + 360),
    )


@then("the change is rejected")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") in REFUSALS


@then("I am told the punch-out must be after the punch-in")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == "the punch-out must be after the punch-in"


@then("I am told the boundary must fall within the Segment")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == "the boundary must fall within the Segment"


@then("I am told the selection is too short")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == "the selection is too short"


@then(parsers.parse('the punch-out remains "{timecode}"'))
def _(detail_page, timecode):
    assert abs(READS(reads_field(detail_page, "punch-out")) - READS(timecode)) < 0.005


@then("the change is accepted")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") not in REFUSALS


@then("I am warned that the length is outside the expected range")
def _(detail_page):
    assert reads_field(detail_page, "length-warning") == "the length is outside the expected range"


@then("I can approve anyway")
def _(detail_page):
    offered = [row["action"] for row in reads_rows(detail_page, "segment-action")]
    assert "Approve" in offered


@then("the adjustment is saved without approving")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == "the adjustment is saved without approving"
    assert reads_field(detail_page, "segment-state") == "proposed"


@when("I revert to the proposed boundaries", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(store, _web.boundary_action(segment, "punch-in"), do="revert")


@then("my discarded adjustment is recorded in the history")
def _(store, segment):
    discarded = [
        entry
        for entry in reads_boundary_history(store, segment.segment_id)
        if entry.correlation_id == f"revert:{segment.segment_id}"
    ]
    assert [entry.punch_in_seconds for entry in discarded] == [READS("2:00:16.500")]


@given("I have adjusted a Segment's boundaries", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(
        store,
        _web.boundary_action(segment, "punch-in"),
        do="set",
        timecode=formats_precise(segment.punch_in_seconds + 1),
    )


@when("Analysis is re-run", target_fixture="detail_page")
def _(store, recording, segment):
    _web.posts(store, _web.recording_action(recording, "re-run-analysis"))
    return _web.opens_detail(store, recording.recording_id, segment=segment.segment_id)


@then("my adjustment survives")
def _(detail_page, segment):
    assert READS(reads_field(detail_page, "punch-in")) == segment.punch_in_seconds + 1


@then("the new machine proposal is offered beside it, not applied over it")
def _(detail_page):
    offered = reads_field(detail_page, "proposed-boundaries")
    assert offered.split(" – ")[0] != reads_field(detail_page, "punch-in")


@when("I adjust this Segment's punch-in", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(
        store,
        _web.boundary_action(segment, "punch-in"),
        do="nudge",
        direction="later",
        amount="1 s",
    )


@then("the other Segment's boundaries are unchanged")
def _(store, segment):
    others = [
        one
        for one in store.lists(Segment, recording_id=segment.recording_id)
        if one.segment_id != segment.segment_id
    ]
    assert others
    assert all(
        (one.punch_in_seconds, one.punch_out_seconds)
        == (one.span_start_seconds, one.span_end_seconds)
        for one in others
    )


@given(
    parsers.parse('I have selected a Segment whose intent is "{intent}"'),
    target_fixture="segment",
)
def _(store, recording, intent):
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="meeting",
            state="proposed",
            span_start_seconds=0.0,
            span_end_seconds=READS("1:40:00"),
            punch_in_seconds=0.0,
            punch_out_seconds=READS("1:40:00"),
            intent=intent,
        )
    )


@then("the boundary controls are collapsed")
def _(store, segment):
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert reads_field(page, "boundary-controls") == "collapsed"


@then("I am told the whole span will be kept")
def _(store, segment):
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert reads_field(page, "whole-span-note") == "the whole span will be kept"


@then("I can still expand the controls and trim it if I want to")
def _(store, segment):
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert reads_field(page, "expand-boundaries") == "Trim it anyway"
    assert [row["boundary"] for row in reads_rows(page, "boundary")] == ["punch-in", "punch-out"]


@when("I choose that alternative", target_fixture="detail_page")
def _(store, segment):
    candidates = [
        candidate
        for proposal in store.lists(Proposal, segment_id=segment.segment_id)
        for candidate in proposal.punch_in_candidates
    ]
    return _web.posts(
        store,
        _web.boundary_action(segment, "punch-in"),
        do="set",
        timecode=formats_precise(candidates[0].timecode),
    )


@then("the evidence panel shows why that candidate was considered")
def _(detail_page):
    rows = reads_rows(detail_page, "alternative")
    assert [row["alternative-because"] for row in rows] == ["silence"]


@given("the opening contains a throat-clear before the first real words", target_fixture="segment")
def _(store, segment):
    return store.saves(
        replace(segment, punch_in_seconds=segment.punch_in_seconds - 2.0, boundary_source="model")
    )


@when("I move the punch-in past it", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(
        store,
        _web.boundary_action(segment, "punch-in"),
        do="nudge",
        direction="later",
        amount="10 s",
    )


@then("the adjustment is accepted without warning")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == NOTICES["adjusted"]
    assert reads_field(detail_page, "length-warning") is None


@then("the machine proposal remains available to revert to")
def _(detail_page):
    assert reads_field(detail_page, "proposed-boundaries")
    assert reads_field(detail_page, "revert-control") == "Revert to the machine proposal"
