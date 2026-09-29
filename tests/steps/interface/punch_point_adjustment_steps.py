from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.adjusts_punch_point import reads_boundary_history
from sermon.extends_segment_span import ReadsTimecode
from sermon.shows_recording import NOTICES, formats_precise
from sermon.store import Block, Proposal, Recording, Segment, opens_store
from steps._markup import reads_field, reads_rows
from steps._peaks import writes_peaks, writes_utterances
from steps import _web

READS = ReadsTimecode()
SPOKEN_AROUND_THE_CUT = (
    (7214.0, 7219.2, "let us stand together as we sing the final verse"),
    (7220.4, 7226.0, "good morning and welcome to the message this week"),
    (7226.5, 7233.0, "open your bibles with me to the letter to the Hebrews"),
    (9806.0, 9811.4, "so let us pray together as we close this morning"),
    (9812.6, 9818.0, "please stand for the closing hymn"),
)
ANATOMY = (
    (0.0, 1800.0, "music", "the opening songs"),
    (1800.0, 7220.0, "lesson", "the class hour"),
    (7220.0, 9812.0, "sermon", "the message"),
    (9812.0, 11520.0, "communion", "the table and the sending"),
)
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
def _(store, recording, segment, punch_in, punch_out):
    writes_peaks(store, recording)
    writes_utterances(store, recording, SPOKEN_AROUND_THE_CUT)
    for start, end, block_type, summary in ANATOMY:
        store.saves(
            Block(
                recording_id=recording.recording_id,
                start_seconds=start,
                end_seconds=end,
                type=block_type,
                summary=summary,
            )
        )
    return store.saves(
        replace(
            segment,
            punch_in_seconds=READS(punch_in),
            punch_out_seconds=READS(punch_out),
        )
    )


def reads_span(page):
    edges = {row["edge"]: READS(row["span-edge-at"]) for row in reads_rows(page, "span-edge")}
    assert {"start", "end"} <= set(edges), page
    return edges["start"], edges["end"]


@when(
    parsers.parse("I extend the Segment's own start to \"{timecode}\""),
    target_fixture="detail_page",
)
def _(store, segment, timecode):
    return _web.posts(
        store, _web.span_action(segment, "start"), do="set", timecode=timecode
    )


@then("the Segment's span grows")
def _(segment, detail_page):
    grown_start, grown_end = reads_span(detail_page)
    assert grown_start < segment.span_start_seconds
    assert grown_end == segment.span_end_seconds


@then("the punch-in may now be placed anywhere within the new span")
def _(store, segment, detail_page):
    grown_start, _ = reads_span(detail_page)
    outside_the_old_span = (
        grown_start,
        (grown_start + segment.span_start_seconds) / 2,
        segment.span_start_seconds - 0.5,
    )
    for at in outside_the_old_span:
        assert grown_start <= at < segment.span_start_seconds
        page = _web.posts(
            store,
            _web.boundary_action(segment, "punch-in"),
            do="set",
            timecode=formats_precise(at),
        )
        assert reads_field(page, "action-notice") not in REFUSALS
        assert abs(READS(reads_field(page, "punch-in")) - at) < 0.005


@then("the change is rejected if it would overlap the neighbouring Segment")
def _(store, recording, segment, detail_page):
    grown_start, _ = reads_span(detail_page)
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="lesson",
            state="proposed",
            span_start_seconds=READS("1:00:00"),
            span_end_seconds=grown_start,
            punch_in_seconds=READS("1:00:00"),
            punch_out_seconds=grown_start,
        )
    )
    refused = _web.posts(
        store,
        _web.span_action(segment, "start"),
        do="set",
        timecode=formats_precise(grown_start - 60),
    )
    assert (
        reads_field(refused, "action-notice") == "it would overlap the neighbouring Segment"
    )
    assert reads_span(refused)[0] == grown_start


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


@when("I punch the punch-in in from beside the waveform", target_fixture="detail_page")
def _(store, segment):
    client = _web.opens_app(store).test_client()
    client.post(
        f"/api/recordings/{segment.recording_id}/seek",
        json={"seconds": getattr(store, "_playhead", 0.0)},
    )
    posted = client.post(_web.boundary_action(segment, "punch-in"), data={"do": "playhead"})
    return client.get(posted.headers["Location"]).get_data(as_text=True)


@then("a punch control for each boundary sits beside the waveform rather than in a lower card")
def _(detail_page):
    rows = reads_rows(detail_page, "punch-point")
    assert [row["boundary"] for row in rows] == ["punch-in", "punch-out"]
    assert all(row["punch-control"] for row in rows)
    beside = detail_page.index('<section class="waveform">')
    lower = detail_page.index('<div class="supporting">')
    placed = [
        detail_page.index(f'data-row="punch-point" data-boundary="{row["boundary"]}"')
        for row in rows
    ]
    assert all(beside < at < lower for at in placed)
