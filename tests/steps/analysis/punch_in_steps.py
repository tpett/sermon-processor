from dataclasses import dataclass, replace

import pytest
from pytest_bdd import given, parsers, then, when
from steps import _analysis, _web

from sermon.analysis import ProposesSegments, RefinesPunchIn, ScoresProposals
from sermon.analysis.io import reads_json, writes_json
from sermon.store import Block, Proposal, Segment

READS = _analysis.READS
WORD_S = _analysis.WORD_S
LEAD_IN_LIMIT_S = 1.0
QUIET_MARGIN_S = 0.25
CLOSING_READING = "this is the word of the lord"
TEACHING = _analysis.SPOKEN["sermon"]
FALSE_START = "um sorry let me just"
QUIET_BEFORE = {
    "10 seconds of clean silence before the first word": 10.0,
    "2 seconds of clean silence": 2.0,
    "between 250 ms and 2 s of quiet": 1.0,
    "under 250 ms of quiet, words either side": 0.1,
    "audible noise or feedback near the cut point": 0.0,
    "music fading under the first words": 0.0,
}


@dataclass
class RunUp:
    """The speech either side of the cut: where the reading stops and the teaching starts."""

    seed_start: float = 1900.0
    reading_ends: float = 1897.0
    first_word: float = 1901.5
    opening: str = TEACHING
    false_start: bool = False
    music_under: bool = False


@pytest.fixture
def run_up():
    return RunUp()


def utterance(start, text):
    words = [
        {"w": word, "word": word, "start": round(start + index * WORD_S, 3), "end": round(start + index * WORD_S + WORD_S - 0.05, 3)}
        for index, word in enumerate(text.split())
    ]
    return {"start": words[0]["start"], "end": words[-1]["end"], "text": text, "confidence": 0.92, "speaker": "Speaker 1", "words": words}


def speech_between(start, end, text, period=8.5):
    spoken, at = [], start
    while at + len(text.split()) * WORD_S < end:
        spoken.append(utterance(at, text))
        at += period
    return spoken


def lays_out(store, run_up):
    recording = _analysis.recording_of(store)
    reading = utterance(run_up.reading_ends - len(CLOSING_READING.split()) * WORD_S + 0.05, CLOSING_READING)
    opening = []
    starts = run_up.first_word
    if run_up.false_start:
        opening.append(utterance(starts, FALSE_START))
        starts = opening[-1]["end"] + 1.2
    opening.append(utterance(starts, run_up.opening))
    utterances = (
        speech_between(1570.0, reading["start"] - 0.6, _analysis.SPOKEN["scripture_reading"])
        + [reading]
        + opening
        + speech_between(opening[-1]["end"] + 0.6, 4300.0, TEACHING)
        + speech_between(4300.0, 4420.0, _analysis.SPOKEN["prayer"])
        + speech_between(4420.0, 4800.0, _analysis.SPOKEN["communion"])
    )
    silences = [
        {"start": before["end"], "end": after["start"]}
        for before, after in zip(utterances, utterances[1:])
        if after["start"] - before["end"] >= 1.0
    ]
    music = [{"start": 0.0, "end": 1570.0}, {"start": 4800.0, "end": recording.duration_seconds}]
    if run_up.music_under:
        music.append({"start": run_up.reading_ends, "end": run_up.first_word + 5.0})
    writes_json(
        store,
        recording,
        "transcript",
        {
            "recording_id": recording.recording_id,
            "started_at": recording.started_at.isoformat(),
            "duration": recording.duration_seconds,
            "language": "en",
            "utterances": utterances,
            "silences": silences,
            "likely_music": music,
        },
    )
    for block in store.lists(Block, recording_id=recording.recording_id):
        store.forgets(block)
    for start, end, kind in (
        (0.0, 1570.0, "music"),
        (1570.0, run_up.seed_start, "scripture_reading"),
        (run_up.seed_start, 4300.0, "sermon"),
        (4300.0, 4420.0, "prayer"),
        (4420.0, 4800.0, "communion"),
        (4800.0, recording.duration_seconds, "music"),
    ):
        store.saves(Block(recording_id=recording.recording_id, start_seconds=start, end_seconds=end, type=kind))


def words_of(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    return [word for item in doc["utterances"] for word in item["words"]]


def the_segment(store):
    segments = store.lists(Segment)
    assert len(segments) == 1, f"{len(segments)} Segments"
    return segments[0]


def first_word_after(store, moment):
    later = [word["start"] for word in words_of(store) if word["start"] >= moment]
    assert later, f"no word follows {moment}"
    return min(later)


def proposal_of(store):
    return _analysis.proposal_of(store, the_segment(store))


@given(parsers.parse('a Segment classified "{classification}" seeded on a Block beginning at "{timecode}"'))
def _(store, run_up, classification, timecode):
    run_up.seed_start = READS(timecode)
    lays_out(store, run_up)


@given(parsers.parse('the previous Block ends at "{timecode}"'))
def _(store, run_up, timecode):
    assert READS(timecode) == run_up.seed_start
    lays_out(store, run_up)


@given(parsers.parse('the first word of the Block begins at "{timecode}"'))
def _(store, run_up, timecode):
    run_up.first_word = READS(timecode)
    lays_out(store, run_up)


@given(parsers.parse('the first word begins at "{timecode}"'))
def _(store, run_up, timecode):
    run_up.first_word = READS(timecode)
    lays_out(store, run_up)


@given(parsers.parse('the previous Block has audible speech up to "{timecode}"'))
def _(store, run_up, timecode):
    run_up.reading_ends = READS(timecode)
    lays_out(store, run_up)


@when("punch-in refinement runs")
def _(store):
    recording = _analysis.recording_of(store)
    ProposesSegments(store=store)(recording)
    RefinesPunchIn(store=store)(recording)
    ScoresProposals(store=store)(recording)


@then(parsers.parse('the punch-in is placed at "{timecode}"'))
def _(store, timecode):
    assert abs(the_segment(store).punch_in_seconds - READS(timecode)) < 0.05


@then("the lead-in never exceeds 1.0 second")
def _(store):
    segment = the_segment(store)
    assert 0.0 <= first_word_after(store, segment.punch_in_seconds) - segment.punch_in_seconds <= LEAD_IN_LIMIT_S


@then(parsers.parse('the punch-in is placed after "{timecode}"'))
def _(store, timecode):
    assert the_segment(store).punch_in_seconds > READS(timecode)


@then("the lead-in is shorter than 1.0 second")
def _(store):
    segment = the_segment(store)
    assert first_word_after(store, segment.punch_in_seconds) - segment.punch_in_seconds < LEAD_IN_LIMIT_S


@then("no audio from the previous Block is included")
def _(store, run_up):
    segment = the_segment(store)
    previous = [word for word in words_of(store) if word["end"] <= run_up.seed_start]
    assert previous
    assert max(word["end"] for word in previous) <= segment.punch_in_seconds


@then("the punch-in is placed at least 250 ms away from the nearest audible sound")
def _(store):
    segment = the_segment(store)
    nearest = min(min(abs(word["start"] - segment.punch_in_seconds), abs(word["end"] - segment.punch_in_seconds)) for word in words_of(store))
    assert nearest >= QUIET_MARGIN_S


@given("there is no 250 ms of quiet anywhere in the run-up to the first word")
def _(store, run_up):
    run_up.reading_ends, run_up.first_word = run_up.seed_start - 0.05, run_up.seed_start + 0.05
    lays_out(store, run_up)


@then("the punch-in is placed at the quietest available point")
def _(store, run_up):
    segment = the_segment(store)
    assert run_up.reading_ends <= segment.punch_in_seconds <= run_up.first_word


@then("the reviewer is prompted to place it by hand")
def _(store):
    segment = the_segment(store)
    unclean = [warning for warning in segment.warnings if warning.startswith("no clean cut point found")]
    assert unclean
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    for warning in unclean:
        point = warning.rsplit(" ", 1)[-1]
        assert f'data-field="needs-checking-{point}"' in page


@given(parsers.parse('the audio around the chosen punch-in is "{condition}"'))
def _(store, run_up, condition):
    run_up.reading_ends = run_up.first_word - QUIET_BEFORE[condition]
    run_up.music_under = condition.startswith("music")
    lays_out(store, run_up)


@then(parsers.parse('the cut is graded "{grade}"'))
def _(store, grade):
    assert proposal_of(store).punch_in_grade == grade


@given(parsers.parse('the cut is graded "{grade}"'))
def _(store, run_up, grade):
    run_up.reading_ends = run_up.first_word - (QUIET_BEFORE["10 seconds of clean silence before the first word"] if grade == "easy" else 0.1)
    lays_out(store, run_up)
    recording = _analysis.recording_of(store)
    ProposesSegments(store=store)(recording)
    RefinesPunchIn(store=store)(recording)
    ScoresProposals(store=store)(recording)
    assert proposal_of(store).punch_in_grade == grade


@when("the Segment is offered for review", target_fixture="review_page")
def _(store):
    segment = the_segment(store)
    return _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)


@then("it is flagged as needing the punch-in checked by hand")
def _(store, review_page):
    assert "no clean cut point found at punch-in" in the_segment(store).warnings
    assert 'data-field="needs-checking-punch-in"' in review_page


@then(parsers.parse('the reason is stated, for example "{reason}"'))
def _(store, reason):
    segment = the_segment(store)
    proposal = _analysis.proposal_of(store, segment)
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    reasons = [warning for warning in segment.warnings if warning in page]
    reasons += [
        f"the {point} is graded {grade}"
        for point, grade in (("punch-in", proposal.punch_in_grade), ("punch-out", proposal.punch_out_grade))
        if grade != "easy" and f"the {point} is graded {grade}" in page
    ]
    assert reasons, "the review page states no reason for the flag"


@then("no flag is raised")
def _(store):
    assert the_segment(store).warnings == ()


@given(parsers.parse('the first words of the Block are "{words}"'))
def _(store, run_up, words):
    run_up.opening = words.lower().replace(",", "")
    lays_out(store, run_up)


@then(parsers.parse('the punch-in is placed immediately before "{phrase}"'))
def _(store, phrase):
    segment = the_segment(store)
    spoken = first_word_after(store, segment.punch_in_seconds)
    opening = [word for word in words_of(store) if word["start"] == spoken]
    assert [word["w"] for word in opening] == [phrase.split()[0].lower()]
    assert 0.0 <= spoken - segment.punch_in_seconds <= LEAD_IN_LIMIT_S


@then("the punch-in is placed immediately before that phrase")
def _(store, run_up):
    segment = the_segment(store)
    spoken = first_word_after(store, segment.punch_in_seconds)
    assert spoken == run_up.first_word
    assert 0.0 <= spoken - segment.punch_in_seconds <= LEAD_IN_LIMIT_S


@then("that counts as evidence for the punch-in")
def _(store, run_up):
    assert any(
        evidence.implies == "punch-in" and abs(evidence.timecode - the_segment(store).punch_in_seconds) < 0.001
        for evidence in proposal_of(store).evidence
    )


@given("the Block opens with a false start or a throat-clear")
def _(store, run_up):
    run_up.false_start = True
    lays_out(store, run_up)


@then("the punch-in is still placed before the first words")
def _(store, run_up):
    segment = the_segment(store)
    assert segment.punch_in_seconds <= run_up.first_word
    assert first_word_after(store, segment.punch_in_seconds) == run_up.first_word


@then("an alternative punch-in after the false start is offered as a candidate")
def _(store, run_up):
    false_start = [word for word in words_of(store) if word["start"] >= run_up.first_word][: len(FALSE_START.split())]
    after = false_start[-1]["end"]
    assert any(
        after <= candidate.timecode < after + 2.0 for candidate in proposal_of(store).punch_in_candidates
    )


@given(parsers.parse('a candidate falls at "{timecode}" during a word'))
def _(store, run_up, timecode):
    run_up.first_word = READS(timecode) - 0.15
    lays_out(store, run_up)


@then("the punch-in is moved to the nearest preceding silence")
def _(store, run_up):
    segment = the_segment(store)
    assert run_up.reading_ends <= segment.punch_in_seconds <= run_up.first_word


@then("no word is cut off")
def _(store):
    segment = the_segment(store)
    assert not [word for word in words_of(store) if word["start"] < segment.punch_in_seconds < word["end"]]


@then("the grade is shown to the reviewer")
def _(store):
    segment = the_segment(store)
    grade = proposal_of(store).punch_in_grade
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert f'data-field="punch-in-grade">{grade} to place<' in page


@then("the reviewer is expected to confirm it with a single preview")
def _(store):
    segment = the_segment(store)
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert 'data-field="needs-checking-punch-in"' not in page
    assert f'data-field="punch-in-grade">easy to place<' in page
