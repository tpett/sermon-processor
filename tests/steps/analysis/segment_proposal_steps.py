from dataclasses import replace

import pytest
from pytest_bdd import given, parsers, then, when
from steps import _analysis, _web

from sermon.analysis.io import reads_json
from sermon.store import Block, Proposal, Segment

READS = _analysis.READS
CLASS_AND_SERVICE_S = 3 * 3600 + 12 * 60
QUIET_MARGIN_S = 0.25
QUIET_RUN_S = 0.5
LEAD_IN_LIMIT_S = 2.0
UNCLEAN = {
    "punch_in_seconds": "no clean cut point found at punch-in",
    "punch_out_seconds": "no clean cut point found at punch-out",
}


def recording_of(store):
    return _analysis.recording_of(store)


def lays_out(store, spans):
    recording = recording_of(store)
    return _analysis.lays_out(store, recording, [(float(start), float(end), kind) for start, end, kind in spans])


def seeded_on(store, segment):
    assert segment.seed_block_id is not None, f"Segment {segment.segment_id} was not seeded on a Block"
    seed = store.loads(Block, segment.seed_block_id)
    assert seed.type == segment.classification
    assert segment.punch_in_seconds < seed.end_seconds and segment.punch_out_seconds > seed.start_seconds
    return seed


def only_segment(store):
    segments = _analysis.proposed(store)
    assert len(segments) == 1, f"{len(segments)} Segments were proposed: {segments}"
    return segments[0]


def block_typed(store, kind, nth=0):
    found = [block for block in _analysis.blocks_of(store) if block.type == kind]
    assert len(found) > nth, f"no {kind} Block {nth} among {[b.type for b in _analysis.blocks_of(store)]}"
    return found[nth]


def words_of(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    return [word for utterance in doc["utterances"] for word in utterance.get("words", ())]


def words_within(store, start, end):
    return [word for word in words_of(store) if word["start"] < end and word["end"] > start]


def inside_a_word(store, moment):
    return [word for word in words_of(store) if word["start"] < moment < word["end"]]


def quiet_exists_near(store, moment):
    words = sorted(words_of(store), key=lambda word: word["start"])
    return any(
        later["start"] - earlier["end"] >= QUIET_RUN_S
        and earlier["end"] - 2.0 <= moment <= later["start"] + 2.0
        for earlier, later in zip(words, words[1:])
    )


def nearest_sound(store, moment):
    return min(
        (min(abs(word["start"] - moment), abs(word["end"] - moment)) for word in words_of(store)),
        default=float("inf"),
    )


def unclean_boundaries(store, segment):
    found = []
    for boundary in UNCLEAN:
        moment = getattr(segment, boundary)
        if inside_a_word(store, moment):
            found.append(boundary)
        elif quiet_exists_near(store, moment) and nearest_sound(store, moment) < QUIET_MARGIN_S:
            found.append(boundary)
    return found


def ends_with(store, segment, block):
    """The cut ends after the Block's last word and before anything that follows it is heard."""
    spoken = words_within(store, block.start_seconds, block.end_seconds)
    assert spoken, f"the {block.type} Block holds no speech"
    following = [word for word in words_of(store) if word["start"] >= block.end_seconds]
    assert spoken[-1]["end"] <= segment.punch_out_seconds
    assert not following or segment.punch_out_seconds <= min(word["start"] for word in following)


def starts_with(store, segment, block):
    """The cut starts before the Block's first word and after everything before it was heard."""
    spoken = words_within(store, block.start_seconds, block.end_seconds)
    assert spoken, f"the {block.type} Block holds no speech"
    earlier = [word for word in words_of(store) if word["end"] <= block.start_seconds]
    assert segment.punch_in_seconds <= spoken[0]["start"]
    assert not earlier or segment.punch_in_seconds >= max(word["end"] for word in earlier)


def first_word_after(store, moment):
    return min((word["start"] for word in words_of(store) if word["start"] >= moment), default=None)


@when("segment proposal runs")
def _(store):
    _analysis.analyses(store, recording_of(store))


@then("the Q&A is excluded")
def _(store):
    segment = only_segment(store)
    qa = block_typed(store, "qa")
    assert segment.punch_out_seconds <= words_within(store, qa.start_seconds, qa.end_seconds)[0]["start"]


@given("the Recording contains a lesson Block and a sermon Block")
def _(store):
    store.saves(replace(recording_of(store), duration_seconds=float(CLASS_AND_SERVICE_S)))
    lays_out(
        store,
        [
            (0.0, 250.0, "announcements"),
            (250.0, 3680.0, "lesson"),
            (3680.0, 3835.0, "prayer"),
            (3835.0, 4500.0, "qa"),
            (4500.0, 5400.0, "music"),
            (5400.0, 8800.0, "sermon"),
            (8800.0, 8930.0, "prayer"),
            (8930.0, 9400.0, "communion"),
            (9400.0, float(CLASS_AND_SERVICE_S), "music"),
        ],
    )


@then("each is independently classified, dispositionable and renderable")
def _(store):
    segments = _analysis.proposed(store)
    duration = _analysis.the_recording(store).duration_seconds
    assert [item.classification for item in segments] == ["lesson", "sermon"]
    assert [item.state for item in segments] == ["proposed", "proposed"]
    assert len({item.segment_id for item in segments}) == 2
    for item in segments:
        seeded_on(store, item)
        assert len(store.lists(Proposal, segment_id=item.segment_id)) == 1
        assert 0.0 <= item.punch_in_seconds < item.punch_out_seconds <= duration
    first, second = segments
    assert first.punch_out_seconds <= second.punch_in_seconds


@given("the Recording contains only announcements and music Blocks")
def _(store):
    lays_out(store, [(0.0, 240.0, "announcements"), (240.0, 1200.0, "music"), (1200.0, 5412.0, "music")])


@then('the Recording is summarised as "nothing to publish"')
def _(store):
    page = _web.opens_detail(store, _analysis.the_recording(store).recording_id)
    assert "nothing to publish" in page.lower()


@given("a sermon Block is immediately followed by a prayer Block")
def _(store):
    lays_out(
        store,
        [
            (0.0, 240.0, "announcements"),
            (240.0, 1570.0, "music"),
            (1570.0, 1900.0, "scripture_reading"),
            (1900.0, 4360.0, "sermon"),
            (4360.0, 4492.0, "prayer"),
            (4492.0, 4800.0, "communion"),
            (4800.0, 5412.0, "music"),
        ],
    )


@then("the prayer is included in the Segment")
def _(store):
    segment = only_segment(store)
    prayer = block_typed(store, "prayer")
    assert prayer.start_seconds >= block_typed(store, "sermon").end_seconds - 0.001
    spoken = words_within(store, prayer.start_seconds, prayer.end_seconds)
    assert spoken
    assert all(segment.punch_in_seconds <= word["start"] and word["end"] <= segment.punch_out_seconds for word in spoken)


@given("a sermon Block is followed by a music Block and then a prayer Block")
def _(store):
    lays_out(
        store,
        [
            (0.0, 1570.0, "music"),
            (1570.0, 1900.0, "scripture_reading"),
            (1900.0, 4300.0, "sermon"),
            (4300.0, 4600.0, "music"),
            (4600.0, 4720.0, "prayer"),
            (4720.0, 5000.0, "communion"),
            (5000.0, 5412.0, "announcements"),
        ],
    )


@then("the Segment ends at the end of the sermon Block")
def _(store):
    ends_with(store, only_segment(store), block_typed(store, "sermon"))


@then("the later prayer is not included")
def _(store):
    segment = only_segment(store)
    prayer = block_typed(store, "prayer")
    spoken = words_within(store, prayer.start_seconds, prayer.end_seconds)
    assert spoken
    assert segment.punch_out_seconds <= spoken[0]["start"]


@given(parsers.parse('a sermon Block followed by a prayer Block followed by a "{following}" Block'))
def _(store, following):
    lays_out(
        store,
        [
            (0.0, 1570.0, "music"),
            (1570.0, 1900.0, "scripture_reading"),
            (1900.0, 4360.0, "sermon"),
            (4360.0, 4492.0, "prayer"),
            (4492.0, 4800.0, following),
            (4800.0, 5412.0, "announcements" if following == "music" else "music"),
        ],
    )


@then("the Segment ends at the end of the prayer Block")
def _(store):
    ends_with(store, only_segment(store), block_typed(store, "prayer"))


@given("a prayer Block immediately precedes the sermon Block")
def _(store):
    lays_out(
        store,
        [
            (0.0, 240.0, "announcements"),
            (240.0, 1700.0, "music"),
            (1700.0, 1900.0, "prayer"),
            (1900.0, 4300.0, "sermon"),
            (4300.0, 4420.0, "prayer"),
            (4420.0, 4800.0, "communion"),
            (4800.0, 5412.0, "music"),
        ],
    )


@then("the Segment starts at the sermon Block, not at the prayer")
def _(store):
    opening = block_typed(store, "prayer", 0)
    sermon = block_typed(store, "sermon")
    assert opening.end_seconds == sermon.start_seconds
    starts_with(store, only_segment(store), sermon)


@given("a proposed Segment where the length falls outside the expected range")
def _(store):
    lays_out(
        store,
        [(0.0, 1570.0, "music"), (1570.0, 1900.0, "scripture_reading"), (1900.0, 2500.0, "sermon"),
         (2500.0, 2620.0, "prayer"), (2620.0, 2900.0, "communion"), (2900.0, 5412.0, "music")],
    )


@given("a proposed Segment where a boundary falls outside the Recording")
def _(store):
    lays_out(
        store,
        [(0.0, 1570.0, "music"), (1570.0, 1900.0, "scripture_reading"), (1900.0, 4360.0, "music"),
         (4360.0, 5600.0, "sermon")],
    )


@given("a proposed Segment where the punch-in is more than 30 s from the nearest Block edge")
def _(store):
    pytest.fail(
        "the analyze walk derives every proposal from Block edges and never consults the "
        "model's own segment boundaries (sp-atw), so no proposal it makes can sit 30 s from one"
    )


@given("a proposed Segment where the punch-in falls outside the Block the Segment is seeded on")
def _(store):
    pytest.fail(
        "the analyze walk derives every proposal from its seeding Block and never consults the "
        "model's own segment boundaries (sp-atw), so no proposal it makes can start outside it"
    )


@then("the proposal is treated as implausible")
def _(store):
    segment = only_segment(store)
    assert segment.boundary_source == "refined"


@given("a proposed Segment that is not implausible by any of those tests")
def _(store):
    lays_out(
        store,
        [(0.0, 1570.0, "music"), (1570.0, 1900.0, "scripture_reading"), (1900.0, 4360.0, "sermon"),
         (4360.0, 4492.0, "prayer"), (4492.0, 4800.0, "communion"), (4800.0, 5412.0, "music")],
    )


@then("its boundaries are used as proposed")
def _(store):
    segment = only_segment(store)
    assert segment.punch_in_seconds == pytest.approx(block_typed(store, "sermon").start_seconds, abs=0.01)
    assert segment.punch_out_seconds == pytest.approx(block_typed(store, "prayer").end_seconds, abs=0.01)


@then("the refinement rules do not run")
def _(store):
    segment = only_segment(store)
    assert segment.boundary_source == "model"


@then("the boundary invariants below are still enforced")
def _(store):
    segment = only_segment(store)
    assert unclean_boundaries(store, segment) == []
    spoken = first_word_after(store, segment.punch_in_seconds)
    assert spoken is not None and spoken - segment.punch_in_seconds <= LEAD_IN_LIMIT_S


@given(parsers.parse("a proposed Segment {minutes:d} minutes long"))
def _(store, minutes):
    ends = 1900.0 + minutes * 60
    lays_out(
        store,
        [(0.0, 1570.0, "music"), (1570.0, 1900.0, "scripture_reading"), (1900.0, ends, "sermon"),
         (ends, ends + 120.0, "prayer"), (ends + 120.0, ends + 400.0, "communion"), (ends + 400.0, 5412.0, "music")],
    )


@then("the refinement rules are applied instead")
def _(store):
    segment = only_segment(store)
    prayer = block_typed(store, "prayer")
    assert segment.punch_out_seconds != pytest.approx(prayer.end_seconds, abs=0.01)
    last = max(word["end"] for word in words_within(store, prayer.start_seconds, prayer.end_seconds))
    assert last <= segment.punch_out_seconds <= last + 1.5 + 0.001


@then("the Segment records that its boundaries came from the rules")
def _(store):
    assert only_segment(store).boundary_source == "refined"


@given("a Recording laid out as an ordinary Sunday")
def _(store):
    lays_out(store, _analysis.reads_rows(_analysis.SUNDAY))


@then("the punch-in does not fall inside a word")
def _(store):
    segment = only_segment(store)
    assert inside_a_word(store, segment.punch_in_seconds) == []


@then("the punch-out does not fall inside a word")
def _(store):
    segment = only_segment(store)
    assert inside_a_word(store, segment.punch_out_seconds) == []


@then("neither boundary sits within 250 ms of audible sound where quiet exists")
def _(store):
    segment = only_segment(store)
    for boundary in UNCLEAN:
        moment = getattr(segment, boundary)
        assert quiet_exists_near(store, moment), f"{boundary} has no quiet near it to choose"
        assert nearest_sound(store, moment) >= QUIET_MARGIN_S, f"{boundary} {moment} sits on sound"


@then("the lead-in before the first word does not exceed 2.0 seconds")
def _(store):
    segment = only_segment(store)
    spoken = first_word_after(store, segment.punch_in_seconds)
    assert spoken is not None
    assert spoken - segment.punch_in_seconds <= LEAD_IN_LIMIT_S


@then("a boundary that cannot satisfy these is flagged rather than moved silently")
def _(store):
    segment = only_segment(store)
    flagged = [boundary for boundary in UNCLEAN if UNCLEAN[boundary] in segment.warnings]
    assert flagged == unclean_boundaries(store, segment)


@then("every Segment records whether its boundaries were proposed or refined")
def _(store):
    segments = _analysis.proposed(store)
    assert segments, "analysis proposed no Segment"
    assert all(item.boundary_source in {"model", "refined"} for item in segments)


@then("that is visible in the processing log")
def _(store):
    segments = _analysis.proposed(store)
    assert segments, "analysis proposed no Segment"
    page = _web.opens_detail(store, _analysis.the_recording(store).recording_id)
    for item in segments:
        assert item.boundary_source in page


@given("two teaching Blocks are adjacent with no intervening Block")
def _(store):
    lays_out(
        store,
        [(0.0, 1570.0, "music"), (1570.0, 1900.0, "scripture_reading"), (1900.0, 3100.0, "sermon"),
         (3100.0, 4360.0, "lesson"), (4360.0, 4492.0, "prayer"), (4492.0, 4800.0, "communion"),
         (4800.0, 5412.0, "music")],
    )


@then("they are proposed as one Segment")
def _(store):
    segment = only_segment(store)
    starts_with(store, segment, block_typed(store, "sermon"))
    ends_with(store, segment, block_typed(store, "prayer"))


@then("the reviewer can split it if they were genuinely two messages")
def _(store):
    segment = only_segment(store)
    page = _web.opens_detail(store, _analysis.the_recording(store).recording_id, segment=segment.segment_id)
    assert f"/recordings/{segment.recording_id}/actions/split-segment" in page


@when("segment proposal produces spans that would overlap")
def _(store):
    lays_out(
        store,
        [(0.0, 600.0, "music"), (600.0, 1800.0, "sermon"), (1800.0, 1900.0, "prayer"),
         (1900.0, 2000.0, "announcements"), (2000.0, 4360.0, "lesson"), (4360.0, 5412.0, "music")],
    )
    _analysis.analyses(store, recording_of(store))


@then("the overlap is resolved before the Proposal is offered")
def _(store):
    segments = _analysis.proposed(store)
    assert len(segments) == 2
    assert [seeded_on(store, item).type for item in segments] == ["sermon", "lesson"]
    first, second = segments
    assert first.span_end_seconds <= second.span_start_seconds
    assert first.punch_out_seconds <= second.punch_in_seconds
    for item in segments:
        assert store.lists(Proposal, segment_id=item.segment_id)


@then("no two Segments share any audio")
def _(store):
    segments = sorted(_analysis.proposed(store), key=lambda item: item.punch_in_seconds)
    assert len(segments) >= 2
    for earlier, later in zip(segments, segments[1:]):
        assert earlier.punch_out_seconds <= later.punch_in_seconds


@then("a Segment exists with those boundaries")
def _(store, drawn):
    start, end = drawn
    drawn = [item for item in store.lists(Segment) if abs(item.punch_in_seconds - start) < 0.05]
    assert len(drawn) == 1
    assert abs(drawn[0].punch_out_seconds - end) < 0.05


@then("it can be classified and approved like any other")
def _(store, drawn):
    drawn = [item for item in store.lists(Segment) if abs(item.punch_in_seconds - drawn[0]) < 0.05]
    assert len(drawn) == 1
    page = _web.opens_detail(store, _analysis.the_recording(store).recording_id, segment=drawn[0].segment_id)
    base = f"/recordings/{drawn[0].recording_id}/segments/{drawn[0].segment_id}"
    assert f"{base}/classify" in page
    assert f"{base}/approve" in page


@then("each can be classified, adjusted and dispositioned independently")
def _(store):
    segments = _analysis.proposed(store)
    assert len(segments) == 2
    for item in segments:
        page = _web.opens_detail(store, _analysis.the_recording(store).recording_id, segment=item.segment_id)
        base = f"/recordings/{item.recording_id}/segments/{item.segment_id}"
        for action in ("classify", "boundaries/punch-in", "approve", "skip"):
            assert f"{base}/{action}" in page, f"no {action} control for Segment {item.segment_id}"


@then("1 Segment exists spanning from the first punch-in to the last punch-out")
def _(store):
    live = [item for item in store.lists(Segment) if item.state != "recut"]
    assert [(item.punch_in_seconds, item.punch_out_seconds) for item in live] == [(0.0, 200.0)]


@given(parsers.parse("a proposed Segment is {length} long"))
def _(store, length):
    ends = 1900.0 + READS(length)
    duration = max(5412.0, ends + 600.0)
    store.saves(replace(recording_of(store), duration_seconds=duration))
    lays_out(
        store,
        [(0.0, 1570.0, "music"), (1570.0, 1900.0, "scripture_reading"), (1900.0, ends, "sermon"),
         (ends, ends + 120.0, "communion"), (ends + 120.0, duration, "music")],
    )


@then("the Segment is not flagged")
def _(store):
    assert only_segment(store).warnings == ()
