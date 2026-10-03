from datetime import datetime
from dataclasses import replace

import pytest
from pytest_bdd import given, parsers, then, when
from steps import _analysis
from steps.analysis.segment_proposal_steps import starts_with, words_within

from sermon.analysis import ClassifiesBlocks
from sermon.analysis.stages import SUNDAY_ORDER

SERVICE_STARTS = (10, 30)
UNSURE = 0.3
UNTYPED = "other"


@pytest.fixture
def classified():
    return {}


def lays_out(store, classified, spans, subject=None, confidence=0.9):
    """The reasoning stage's answer, given; its types are what the double was told to say."""
    recording = _analysis.recording_of(store)
    _analysis.lays_out(store, recording, spans, typed=False)
    _analysis.divides(store, recording, [span[:3] for span in spans], confidence=confidence)
    if subject is not None:
        classified["subject"] = subject


def subject_block(store, classified):
    start, end = classified["subject"]
    found = [block for block in _analysis.blocks_of(store) if block.start_seconds == start]
    assert len(found) == 1, f"no Block starts at {start}"
    assert found[0].end_seconds == end
    return found[0]


def findings(block):
    return " ".join(evidence.finding for evidence in block.evidence).lower()


@when("block classification runs")
def _(store):
    ClassifiesBlocks(store=store)(_analysis.recording_of(store))


@when("Segment proposal runs")
def _(store):
    _analysis.analyses(store, _analysis.recording_of(store))


@then(parsers.parse('a Block typed "{block_type}" {seeds} a Segment'))
def _(store, block_type, seeds):
    recording = _analysis.recording_of(store)
    spans = [(0.0, 1570.0, "music"), (1570.0, 1900.0, "scripture_reading"), (1900.0, 4360.0, block_type),
             (4360.0, 4800.0, "communion"), (4800.0, 5412.0, "music")]
    _analysis.lays_out(store, recording, spans)
    proposed = _analysis.analyses(store, recording)
    typed = [block for block in _analysis.blocks_of(store) if block.start_seconds == 1900.0]
    assert [block.type for block in typed] == [block_type]
    covering = [
        segment
        for segment in proposed
        if segment.punch_in_seconds < typed[0].end_seconds and segment.punch_out_seconds > typed[0].start_seconds
    ]
    if "never" in seeds:
        assert covering == []
    else:
        assert [segment.seed_block_id for segment in covering] == [typed[0].block_id]


@given(parsers.parse('two adjacent Blocks are both typed "{block_type}"'))
def _(store, classified, block_type):
    lays_out(
        store,
        classified,
        [(0.0, 103.0, block_type), (103.0, 3500.0, block_type), (3500.0, 3620.0, "prayer"),
         (3620.0, 4400.0, "qa"), (4400.0, 5412.0, "music")],
    )


@then("one Segment is seeded, not two")
def _(store):
    segments = _analysis.proposed(store)
    assert len(segments) == 1
    assert segments[0].seed_block_id is not None


@then("it spans both Blocks")
def _(store):
    segments = _analysis.proposed(store)
    assert len(segments) == 1
    first, second = _analysis.blocks_of(store)[:2]
    starts_with(store, segments[0], first)
    spoken = words_within(store, second.start_seconds, second.end_seconds)
    assert spoken and spoken[-1]["end"] <= segments[0].punch_out_seconds


@given("a Recording containing a normal Sunday service")
def _(store, classified):
    lays_out(store, classified, _analysis.reads_rows(_analysis.SUNDAY), confidence=UNSURE)


@then("the Blocks are typed in order:")
def _(store, datatable):
    expected = [row[0] for row in datatable[1:]]
    assert [block.type for block in _analysis.blocks_of(store)] == expected


@then("each type carries a confidence derived from evidence, not self-reported")
def _(store):
    blocks = _analysis.blocks_of(store)
    assert blocks
    for block in blocks:
        assert block.self_reported_confidence == UNSURE
        assert block.classification_confidence == "high"
        assert any(evidence.implies == "position prior" for evidence in block.evidence)


@then("each carries the evidence that produced it")
def _(store):
    blocks = _analysis.blocks_of(store)
    assert blocks
    for block in blocks:
        assert block.evidence
        assert all(evidence.finding and evidence.implies for evidence in block.evidence)


@given(parsers.parse('a Block contains "{phrase}"'))
def _(store, classified, phrase):
    lays_out(
        store,
        classified,
        [(0.0, 1500.0, "music"), (1500.0, 1800.0, UNTYPED, phrase.lower()), (1800.0, 5412.0, "music")],
        subject=(1500.0, 1800.0),
    )


@then(parsers.parse('the Block is typed "{block_type}"'))
def _(store, classified, block_type):
    assert subject_block(store, classified).type == block_type


@given("a Block is a single speaker talking for 44 minutes")
def _(store, classified):
    lays_out(
        store,
        classified,
        [(0.0, 1900.0, "music"), (1900.0, 4540.0, UNTYPED, _analysis.SPOKEN["sermon"]), (4540.0, 5412.0, "music")],
        subject=(1900.0, 4540.0),
    )


@given("it follows a scripture reading")
def _(store, classified):
    lays_out(
        store,
        classified,
        [(0.0, 1570.0, "music"), (1570.0, 1900.0, "scripture_reading"),
         (1900.0, 4540.0, UNTYPED, _analysis.SPOKEN["sermon"]), (4540.0, 5412.0, "music")],
        subject=(1900.0, 4540.0),
    )


@then(parsers.parse('the evidence includes "{text}"'))
def _(store, classified, text):
    assert text.lower() in findings(subject_block(store, classified))


@given(parsers.parse('a Block begins at "{clock}"'))
def _(store, classified, clock):
    recording = _analysis.recording_of(store)
    store.saves(replace(recording, started_at=recording.started_at.replace(hour=SERVICE_STARTS[0], minute=SERVICE_STARTS[1], second=0)))
    parsed = datetime.strptime(clock, "%I:%M %p")
    offset = float((parsed.hour - SERVICE_STARTS[0]) * 3600 + (parsed.minute - SERVICE_STARTS[1]) * 60)
    lays_out(
        store,
        classified,
        [(0.0, offset, "music"), (offset, offset + 2400.0, "sermon"), (offset + 2400.0, 4000.0, "music"),
         (4000.0, 5412.0, "sermon")],
        subject=(offset, offset + 2400.0),
    )


@then('starting shortly after the usual service time counts as evidence for "sermon"')
def _(store, classified):
    block = subject_block(store, classified)
    assert any(
        "usual service time" in evidence.finding and evidence.implies == "sermon" for evidence in block.evidence
    )


@then("a Block starting at another time is not excluded from being a sermon")
def _(store, classified):
    later = [block for block in _analysis.blocks_of(store) if block.start_seconds == 4000.0]
    assert len(later) == 1
    assert later[0].type == "sermon"
    assert "usual service time" not in findings(later[0])


@given(parsers.parse('a teaching Block is followed by a "{middle}" Block and then a "{following}" Block'))
def _(store, classified, middle, following):
    lays_out(
        store,
        classified,
        [(0.0, 250.0, "announcements"), (250.0, 3600.0, "sermon"), (3600.0, 3720.0, middle),
         (3720.0, 4500.0, following), (4500.0, 5412.0, "music")],
        subject=(250.0, 3600.0),
    )


@then('the teaching Block is typed "lesson" rather than "sermon"')
def _(store, classified):
    assert subject_block(store, classified).type == "lesson"


@then("the expected Sunday order is:")
def _(datatable):
    headers = datatable[0]
    rows = [dict(zip(headers, row)) for row in datatable[1:]]
    assert [int(row["position"]) for row in rows] == list(range(1, len(rows) + 1))
    assert tuple(row["type"] for row in rows) == SUNDAY_ORDER


@given("a Recording whose Blocks match the expected Sunday order")
def _(store, classified):
    lays_out(store, classified, _analysis.reads_rows(_analysis.SUNDAY), confidence=UNSURE)


@then("each Block gains confidence from its position in the order")
def _(store):
    blocks = _analysis.blocks_of(store)
    assert blocks
    for block in blocks:
        assert block.self_reported_confidence == UNSURE
        assert block.classification_confidence == "high"
        assert any(evidence.implies == "position prior" for evidence in block.evidence)

