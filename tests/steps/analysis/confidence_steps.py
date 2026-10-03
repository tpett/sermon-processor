import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, then, when
from steps import _analysis, _web
from steps._peaks import writes_peaks

from sermon.analysis import ScoresProposals
from sermon.store import Proposal, Segment

READ_ALOUD = "hear now the word of the lord from the letter to the romans chapter eight verse one"
UNCUED_READING = "please stand as we read together from the eighth chapter tonight and listen"
LIST_ROW = r'<li data-row="recording" data-id="{id}"[^>]*>'


@dataclass
class Service:
    starts: tuple = (10, 2, 20)
    reading_cue: bool = False
    closing_prayer: bool = True
    communion: bool = True
    sermon_ends: float = 4360.0
    run_in: bool = False
    teaching: tuple = ("sermon",)


@pytest.fixture
def service():
    return Service()


def analysed(store, service):
    recording = _analysis.recording_of(store)
    hour, minute, second = service.starts
    recording = store.saves(
        replace(recording, started_at=datetime(2026, 8, 23, hour, minute, second, tzinfo=UTC), state="downloaded")
    )
    spans = [
        (0.0, 1570.0, "music"),
        (1570.0, 1900.0, "scripture_reading", READ_ALOUD if service.reading_cue else UNCUED_READING),
    ]
    at = 1900.0
    if "lesson" in service.teaching:
        spans = [(0.0, 300.0, "music"), (300.0, 1500.0, "lesson"), (1500.0, 1570.0, "prayer")] + spans[1:]
    spans.append((at, service.sermon_ends, "sermon"))
    at = service.sermon_ends
    if service.closing_prayer:
        spans.append((at, at + 140.0, "prayer"))
        at += 140.0
    if service.communion:
        spans.append((at, at + 300.0, "communion"))
        at += 300.0
    spans.append((at, recording.duration_seconds, "music"))
    _analysis.lays_out(store, recording, spans)
    if service.run_in:
        doc = _analysis.transcript_of(store, recording)
        sermon = [item for item in doc["utterances"] if item["start"] >= 1900.0]
        reading = [item for item in doc["utterances"] if item["end"] <= 1900.0]
        shift = sermon[0]["start"] - reading[-1]["end"] - 0.1
        for word in reading[-1]["words"]:
            word["start"] += shift
            word["end"] += shift
        reading[-1]["start"] += shift
        reading[-1]["end"] += shift
        from sermon.analysis.io import writes_json

        writes_json(store, recording, "transcript", doc)
    proposed = _analysis.analyses(store, recording)
    writes_peaks(store, _analysis.the_recording(store))
    return proposed


def the_sermon(store):
    sermons = [item for item in store.lists(Segment) if item.classification == "sermon"]
    assert len(sermons) == 1, f"{len(sermons)} sermon Segments"
    return sermons[0]


@given("a Recording with classified Blocks and proposed Segments")
def _(store, service):
    analysed(store, service)


@given("a Segment starting at the expected Sunday service time")
def _(store, service):
    analysed(store, service)
    sermon = the_sermon(store)
    started = _analysis.the_recording(store).started_at
    begins = started.hour * 3600 + started.minute * 60 + started.second + sermon.punch_in_seconds
    assert 10 * 3600 + 30 * 60 <= begins <= 10 * 3600 + 50 * 60


@given("its punch-in is supported by a speaker change after a scripture reading")
def _(store, service):
    service.reading_cue = True
    analysed(store, service)


@given("its punch-out is supported by a closing prayer followed by a communion invitation")
def _(store, service):
    service.closing_prayer = service.communion = True
    analysed(store, service)


@given("the resulting span is 48 minutes")
def _(store, service):
    service.sermon_ends = 1900.0 + 48 * 60 - 140.0
    analysed(store, service)
    sermon = the_sermon(store)
    assert abs(sermon.punch_out_seconds - sermon.punch_in_seconds - 48 * 60) < 60.0


@given("it contains no closing prayer or communion cue")
def _(store, service):
    service.closing_prayer = service.communion = False
    analysed(store, service)


@when("scoring runs")
def _(store):
    ScoresProposals(store=store)(_analysis.recording_of(store))


@then(parsers.parse('the Segment\'s classification confidence is "{level}"'))
def _(store, level):
    assert _analysis.proposal_of(store, the_sermon(store)).classification_confidence == level


@then(parsers.parse('its boundary confidence is "{level}"'))
def _(store, level):
    assert _analysis.proposal_of(store, the_sermon(store)).boundary_confidence == level


@then(parsers.parse('the classification confidence is "{level}"'))
def _(store, level):
    assert _analysis.proposal_of(store, the_sermon(store)).classification_confidence == level


@then(parsers.parse('the boundary confidence is "{level}"'))
def _(store, level):
    assert _analysis.proposal_of(store, the_sermon(store)).boundary_confidence == level


@then("the evidence list is shown on the Segment")
def _(store):
    sermon = the_sermon(store)
    evidence = _analysis.proposal_of(store, sermon).evidence
    assert evidence
    page = _web.opens_detail(store, sermon.recording_id, segment=sermon.segment_id)
    for item in evidence:
        assert f'data-evidence-finding="{item.finding}"' in page


@then("each piece of evidence links to its timecode")
def _(store):
    sermon = the_sermon(store)
    evidence = _analysis.proposal_of(store, sermon).evidence
    assert evidence
    page = _web.opens_detail(store, sermon.recording_id, segment=sermon.segment_id)
    for item in evidence:
        assert re.search(rf'centre={re.escape(str(item.timecode))}"[^>]*data-role="evidence-seek"', page)


@then("the reviewer is prompted to check the punch-out specifically")
def _(store):
    sermon = the_sermon(store)
    page = _web.opens_detail(store, sermon.recording_id, segment=sermon.segment_id)
    assert 'data-field="needs-checking-punch-out"' in page
    assert 'data-field="needs-checking-punch-in"' not in page


@given(parsers.parse('the punch-in is graded "{grade}"'))
def _(store, service, grade):
    service.run_in = grade == "hard"
    analysed(store, service)
    assert _analysis.proposal_of(store, the_sermon(store)).punch_in_grade == grade


@then("the Segment is shown as needing attention")
def _(store):
    sermon = the_sermon(store)
    listed = _web.opens_app(store).test_client().get("/").get_data(as_text=True)
    row = re.search(LIST_ROW.format(id=sermon.recording_id), listed)
    assert row and 'data-attention="true"' in row.group(0)
    page = _web.opens_detail(store, sermon.recording_id, segment=sermon.segment_id)
    assert 'data-field="needs-checking-punch-in"' in page


@given("a Recording whose Blocks include music, a lesson and a sermon")
def _(store, service):
    service.teaching = ("lesson", "sermon")
    analysed(store, service)


@given(parsers.parse('{count:d} Segments were proposed, classified "{first}" and "{second}"'))
def _(store, count, first, second):
    assert sorted(item.classification for item in store.lists(Segment)) == sorted([first, second])
    assert len(store.lists(Segment)) == count


@then("the Recording is summarised as containing a sermon")
def _(store):
    recording = _analysis.the_recording(store)
    listed = _web.opens_app(store).test_client().get("/").get_data(as_text=True)
    row = re.search(LIST_ROW.format(id=recording.recording_id), listed)
    assert row
    assert "sermon" in re.search(r'data-classifications="([^"]*)"', row.group(0)).group(1).split()


@then("the recordings list shows the sermon Segment's confidence")
def _(store):
    sermon = the_sermon(store)
    confidence = _analysis.proposal_of(store, sermon).classification_confidence
    listed = _web.opens_app(store).test_client().get("/").get_data(as_text=True)
    row = re.search(LIST_ROW.format(id=sermon.recording_id), listed)
    assert row and f'data-confidence="{confidence}"' in row.group(0)


@then("the other Segments and all Blocks are visible on the detail view")
def _(store):
    recording = _analysis.the_recording(store)
    page = _web.opens_detail(store, recording.recording_id)
    for segment in store.lists(Segment, recording_id=recording.recording_id):
        assert f'<li data-row="segment" data-segment="{segment.segment_id}" data-classification="{segment.classification}"' in page
    assert page.count('<li data-row="block"') == len(_analysis.blocks_of(store, recording))


def proposals_of_every_segment(store):
    segments = store.lists(Segment)
    assert segments, "no Segment was proposed"
    return [_analysis.proposal_of(store, segment) for segment in segments]


@then("the Segment does not claim more certainty than one analysis supports")
def _(store):
    for proposal in proposals_of_every_segment(store):
        assert proposal.agreement_gap_seconds is None


@then("nothing implies a second opinion was sought and agreed")
def _(store):
    sermon = the_sermon(store)
    page = _web.opens_detail(store, sermon.recording_id, segment=sermon.segment_id)
    for proposal in proposals_of_every_segment(store):
        assert proposal.agreement_gap_seconds is None
    assert "agree" not in page.lower()


@then("the Segment carries, most useful first:")
def _(store, datatable):
    sermon = the_sermon(store)
    page = _web.opens_detail(store, sermon.recording_id, segment=sermon.segment_id)
    places = [
        page.find('data-field="punch-in-grade"'),
        page.find("data-evidence-finding="),
        page.find('data-field="segment-length"'),
    ]
    assert len(datatable) - 1 == len(places)
    assert all(place >= 0 for place in places)
    assert places == sorted(places), f"shown in the order {places}"


@then("each evidence entry states what was found, where, and what it implies, for example:")
def _(store, datatable):
    sermon = the_sermon(store)
    evidence = _analysis.proposal_of(store, sermon).evidence
    assert evidence
    page = _web.opens_detail(store, sermon.recording_id, segment=sermon.segment_id)
    markers = re.findall(r'<li data-row="evidence-marker"[^>]*>', page)
    for item in evidence:
        shown = [marker for marker in markers if f'data-evidence-finding="{item.finding}"' in marker]
        assert shown, f"{item.finding!r} is not shown"
        assert f'data-evidence-seconds="{item.timecode}"' in shown[0]
        assert f'data-evidence-implies="{item.implies}"' in shown[0]


@then("a confidence band tells the reviewer where to look first")
def _(store):
    recording = _analysis.the_recording(store)
    listed = _web.opens_app(store).test_client().get("/").get_data(as_text=True)
    row = re.search(LIST_ROW.format(id=recording.recording_id), listed)
    assert row
    banded = re.search(r'data-confidence="([^"]*)"', row.group(0)).group(1)
    assert banded in {"high", "medium", "low"}


@then("it is not shown as needing attention")
def _(store):
    recording = _analysis.the_recording(store)
    listed = _web.opens_app(store).test_client().get("/").get_data(as_text=True)
    row = re.search(LIST_ROW.format(id=recording.recording_id), listed)
    assert row
    assert 'data-attention="false"' in row.group(0)
