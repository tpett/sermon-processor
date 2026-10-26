import re

from pytest_bdd import given, parsers, then, when

from sermon.adjusts_punch_point import NUDGE_STEPS
from sermon.extends_segment_span import ReadsTimecode
from sermon.store import Segment
from steps._markup import reads_field, reads_rows
from steps import _web

READS = ReadsTimecode()
NUDGE = re.compile(r'data-nudge="([^"]*)"')


def reads_nudges(page):
    return NUDGE.findall(page)


@when(parsers.parse('I nudge the punch-in {direction} by "{amount}"'), target_fixture="detail_page")
def _(store, segment, direction, amount):
    return _web.posts(
        store,
        _web.boundary_action(segment, "punch-in"),
        do="nudge",
        direction=direction,
        amount=amount,
    )


@when(parsers.parse('I adjust the punch-in to "{timecode}"'), target_fixture="detail_page")
def _(store, segment, timecode):
    return _web.posts(
        store, _web.boundary_action(segment, "punch-in"), do="set", timecode=timecode
    )


@given(parsers.parse('I have adjusted the punch-in to "{timecode}"'), target_fixture="detail_page")
def _(store, segment, timecode):
    return _web.posts(
        store, _web.boundary_action(segment, "punch-in"), do="set", timecode=timecode
    )


@when(parsers.parse('I set the punch-out to "{timecode}"'), target_fixture="detail_page")
def _(store, segment, timecode):
    return _web.posts(
        store, _web.boundary_action(segment, "punch-out"), do="set", timecode=timecode
    )


@then(parsers.parse('the punch-in is "{timecode}"'))
def _(store, segment, timecode):
    assert store.loads(Segment, segment.segment_id).punch_in_seconds == READS(timecode)


@then(parsers.parse('the punch-in becomes "{timecode}"'))
def _(detail_page, timecode):
    assert abs(READS(reads_field(detail_page, "punch-in")) - READS(timecode)) < 0.005


@then(parsers.parse('the punch-out becomes "{timecode}"'))
def _(detail_page, timecode):
    assert abs(READS(reads_field(detail_page, "punch-out")) - READS(timecode)) < 0.005


@when("I focus the punch-in", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(store, _web.boundary_action(segment, "punch-in"), do="focus", mode="edit")


@given("the punch-in has focus", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(store, _web.boundary_action(segment, "punch-in"), do="focus", mode="edit")


@when("I move focus to the punch-out", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(store, _web.boundary_action(segment, "punch-out"), do="focus", mode="edit")


@then("the punch-in is visibly marked as the one the keyboard will move")
def _(detail_page):
    assert reads_field(detail_page, "focus-state") == "the keyboard will move the punch-in"
    marked = [row for row in reads_rows(detail_page, "boundary") if row["focused"] == "true"]
    assert [row["boundary"] for row in marked] == ["punch-in"]


@then("the punch-out is visibly not")
def _(detail_page):
    unmarked = [row for row in reads_rows(detail_page, "boundary") if row["boundary"] == "punch-out"]
    assert unmarked[0]["focused"] == "false"
    assert "boundary-focus" not in unmarked[0]


@then("the marking survives my scrolling or zooming the waveform")
def _(store, segment):
    zoomed = _web.opens_detail(
        store,
        segment.recording_id,
        segment=segment.segment_id,
        mode="edit",
        focus="punch-in",
        zoom="three seconds",
    )
    assert reads_field(zoomed, "focus-state") == "the keyboard will move the punch-in"


@then("the punch-out becomes the boundary the keyboard moves")
def _(detail_page):
    assert reads_field(detail_page, "focus-state") == "the keyboard will move the punch-out"


@then("the change is apparent without my having to test it with a nudge")
def _(detail_page):
    marked = [row for row in reads_rows(detail_page, "boundary") if row["focused"] == "true"]
    assert [row["boundary-focus"] for row in marked] == [
        "the keyboard will move this boundary"
    ]


@then("the available nudge steps are shown alongside the boundary")
def _(store, segment):
    detail_page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id, mode="edit")
    assert reads_field(detail_page, "nudge-steps") == ", ".join(NUDGE_STEPS)
    offered = {
        f"{direction} {step}"
        for step in NUDGE_STEPS
        for direction in ("earlier", "later")
    }
    assert offered <= set(reads_nudges(detail_page))


@then("they read as 50 ms, 0.1 s, 1 s and 10 s")
def _(store, segment):
    detail_page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id, mode="edit")
    assert reads_field(detail_page, "nudge-steps") == "50 ms, 0.1 s, 1 s, 10 s"
