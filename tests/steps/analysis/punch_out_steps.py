from dataclasses import dataclass, replace

import pytest
from pytest_bdd import given, parsers, then, when
from steps import _analysis
from steps.analysis.punch_in_steps import speech_between, utterance

from sermon.analysis import ProposesSegments, RefinesPunchOut, ScoresProposals
from sermon.analysis.io import reads_json, writes_json
from sermon.pipeline.segments import TAIL_S
from sermon.store import Block, Proposal, Segment

READS = _analysis.READS
WORD_S = _analysis.WORD_S
QUIET_MARGIN_S = 0.25
CLOSING_PRAYER = "we thank you for this word in jesus name amen"
FOLLOWING = {"communion": _analysis.SPOKEN["communion"], "qa": _analysis.SPOKEN["qa"], "music": ""}


@dataclass
class Tail:
    """The speech either side of the punch-out: the prayer's last word and what follows it."""

    teaching_starts: float = 1900.0
    prayer_starts: float = 4360.0
    last_word: float = 4488.9
    next_starts: float = 4495.0
    following: str = "communion"
    closing: str = CLOSING_PRAYER
    final_word_s: float = WORD_S - 0.05
    stops_early: float | None = None


@pytest.fixture
def tail():
    return Tail()


def teaching_type(store):
    segments = store.lists(Segment)
    return segments[0].classification if segments else "sermon"


def lays_out(store, tail):
    recording = _analysis.recording_of(store)
    teaching_kind = teaching_type(store)
    for segment in store.lists(Segment, recording_id=recording.recording_id):
        for proposal in store.lists(Proposal, segment_id=segment.segment_id):
            store.forgets(proposal)
        store.forgets(segment)
    end = tail.stops_early or recording.duration_seconds
    if tail.stops_early:
        recording = store.saves(replace(recording, duration_seconds=tail.stops_early))
    words = tail.closing.split()
    closing = utterance(tail.last_word - len(words) * WORD_S + 0.05, tail.closing)
    closing["words"][-1]["start"] = round(tail.last_word - tail.final_word_s, 3)
    closing["words"][-1]["end"] = round(tail.last_word, 3)
    closing["end"] = round(tail.last_word, 3)
    teaching = _analysis.SPOKEN["sermon"]
    if tail.stops_early:
        utterances = speech_between(1570.0, 1900.0, _analysis.SPOKEN["scripture_reading"]) + speech_between(tail.teaching_starts, end + 30.0, teaching)
        utterances = [item for item in utterances if item["end"] <= end]
        spans = ((0.0, 1570.0, "music"), (1570.0, tail.teaching_starts, "scripture_reading"), (tail.teaching_starts, end, teaching_kind))
    else:
        following = FOLLOWING[tail.following]
        utterances = (
            speech_between(1570.0, 1900.0, _analysis.SPOKEN["scripture_reading"])
            + speech_between(tail.teaching_starts, tail.prayer_starts - 0.6, teaching)
            + speech_between(tail.prayer_starts, closing["start"] - 0.6, _analysis.SPOKEN["prayer"])
            + [closing]
            + (speech_between(tail.next_starts, tail.next_starts + 300.0, following) if following else [])
        )
        spans = (
            (0.0, 1570.0, "music"),
            (1570.0, tail.teaching_starts, "scripture_reading"),
            (tail.teaching_starts, tail.prayer_starts, teaching_kind),
            (tail.prayer_starts, tail.next_starts, "prayer"),
            (tail.next_starts, tail.next_starts + 300.0, tail.following),
            (tail.next_starts + 300.0, end, "music"),
        )
    silences = [
        {"start": before["end"], "end": after["start"]}
        for before, after in zip(utterances, utterances[1:])
        if after["start"] - before["end"] >= 1.0
    ]
    writes_json(
        store,
        recording,
        "transcript",
        {
            "recording_id": recording.recording_id,
            "started_at": recording.started_at.isoformat(),
            "duration": end,
            "language": "en",
            "utterances": utterances,
            "silences": silences,
            "likely_music": [],
        },
    )
    for block in store.lists(Block, recording_id=recording.recording_id):
        store.forgets(block)
    for start, finish, kind in spans:
        store.saves(Block(recording_id=recording.recording_id, start_seconds=start, end_seconds=finish, type=kind))


def words_of(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    return [word for item in doc["utterances"] for word in item["words"]]


def the_segment(store):
    segments = store.lists(Segment)
    assert len(segments) == 1, f"{len(segments)} Segments"
    return segments[0]


def following_words(store, tail):
    return [word for word in words_of(store) if word["start"] >= tail.next_starts]


@given(parsers.parse('a Segment classified "{classification}" ending on a prayer Block'))
def _(store, tail, classification):
    lays_out(store, tail)
    ProposesSegments(store=store)(_analysis.recording_of(store))
    assert [segment.classification for segment in store.lists(Segment)] == [classification]


@given(parsers.parse('the last word of that Block is spoken at "{timecode}"'))
def _(store, tail, timecode):
    tail.last_word = READS(timecode)
    lays_out(store, tail)


@given(parsers.parse('the next Block begins at "{timecode}"'))
def _(store, tail, timecode):
    tail.next_starts = READS(timecode)
    lays_out(store, tail)


@when("punch-out refinement runs")
def _(store):
    recording = _analysis.recording_of(store)
    ProposesSegments(store=store)(recording)
    RefinesPunchOut(store=store)(recording)
    ScoresProposals(store=store)(recording)


@then("the punch-out is placed 1.5 seconds after the last word")
def _(store, tail):
    assert the_segment(store).punch_out_seconds == pytest.approx(tail.last_word + TAIL_S, abs=0.05)


@then("the whole of the last word is audible, decay included")
def _(store, tail):
    assert the_segment(store).punch_out_seconds > tail.last_word


@then("the tail stops before any sound belonging to what follows")
def _(store, tail):
    following = following_words(store, tail)
    assert following
    assert the_segment(store).punch_out_seconds < min(word["start"] for word in following)


@then("no audio from the following Block is included")
def _(store, tail):
    segment = the_segment(store)
    heard = [word for word in following_words(store, tail) if word["start"] < segment.punch_out_seconds]
    assert following_words(store, tail)
    assert heard == []


@given("the next Block begins 1.0 seconds after the last word")
def _(store, tail):
    tail.next_starts = tail.last_word + 1.0
    lays_out(store, tail)


@then("the punch-out is placed before the next Block begins")
def _(store, tail):
    assert the_segment(store).punch_out_seconds < tail.next_starts


@then("a margin is left so that no part of the next Block is audible")
def _(store, tail):
    assert tail.next_starts - the_segment(store).punch_out_seconds >= QUIET_MARGIN_S


@given(parsers.parse('the prayer ends with "{words}" at "{timecode}"'))
def _(store, tail, words, timecode):
    tail.closing = words.lower().replace(",", "")
    tail.last_word = READS(timecode)
    lays_out(store, tail)


@given(parsers.parse('the prayer ends at "{timecode}"'))
def _(store, tail, timecode):
    tail.last_word = READS(timecode)
    tail.prayer_starts = min(tail.prayer_starts, tail.last_word - 120.0)
    lays_out(store, tail)


@given(parsers.parse('a communion Block begins at "{timecode}"'))
def _(store, tail, timecode):
    tail.next_starts, tail.following = READS(timecode), "communion"
    lays_out(store, tail)


@given(parsers.parse('a qa Block begins at "{timecode}"'))
def _(store, tail, timecode):
    tail.next_starts, tail.following = READS(timecode), "qa"
    lays_out(store, tail)


@then(parsers.parse('the punch-out falls between "{start}" and "{end}"'))
def _(store, start, end):
    assert READS(start) < the_segment(store).punch_out_seconds < READS(end)


@then("the punch-out is placed at least 250 ms away from the nearest audible sound")
def _(store):
    punch = the_segment(store).punch_out_seconds
    assert min(min(abs(word["start"] - punch), abs(word["end"] - punch)) for word in words_of(store)) >= QUIET_MARGIN_S


@given("the next Block begins immediately with no quiet between")
def _(store, tail):
    tail.next_starts = tail.last_word + 0.05
    lays_out(store, tail)


@then("the punch-out is placed at the quietest available point")
def _(store, tail):
    assert tail.last_word <= the_segment(store).punch_out_seconds <= tail.next_starts


@given(parsers.parse('a candidate falls at "{timecode}" during the final word'))
def _(store, tail, timecode):
    tail.final_word_s = tail.last_word - READS(timecode) + 0.2
    lays_out(store, tail)


@then("the punch-out is moved to after the word ends")
def _(store, tail):
    assert the_segment(store).punch_out_seconds >= tail.last_word


@then("the final word is complete in the output")
def _(store, tail):
    segment = the_segment(store)
    final = [word for word in words_of(store) if word["end"] == tail.last_word]
    assert len(final) == 1
    assert segment.punch_in_seconds <= final[0]["start"] and final[0]["end"] <= segment.punch_out_seconds


@given(parsers.parse('the Recording ends at "{timecode}" while the preacher is still speaking'))
def _(store, tail, timecode):
    tail.stops_early = READS(timecode)
    lays_out(store, tail)


@then("the punch-out is placed at the end of the Recording")
def _(store):
    assert the_segment(store).punch_out_seconds == pytest.approx(_analysis.the_recording(store).duration_seconds, abs=0.05)


@then(parsers.parse('the cut is graded "{first}" or "{second}" on the same basis as the punch-in'))
def _(store, tail, first, second):
    words = sorted(words_of(store), key=lambda word: word["start"])
    after = [word["start"] for word in words if word["start"] > tail.last_word]
    quiet = (min(after) if after else tail.next_starts) - tail.last_word
    expected = first if quiet >= 2.0 else second
    assert _analysis.proposal_of(store, the_segment(store)).punch_out_grade == expected
