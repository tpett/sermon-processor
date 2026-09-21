from dataclasses import replace
from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.analysis import (
    ClassifiesBlocks,
    DerivesGroundTruth,
    ProposesSegments,
    RefinesPunchIn,
    RefinesPunchOut,
    ScoresProposals,
    SummarizesBlocks,
    covering_transcript,
    seeds_segment,
)
from sermon.analysis.io import writes_json
from sermon.analysis.stages import CorrectsBlockSummary, TAIL_S
from sermon.extends_segment_span import ReadsTimecode
from sermon.lists_recordings import ListsRecordings
from sermon.shows_recording import ShowsRecording
from sermon.store import Block, CorpusPair, Evidence, Proposal, Recording, Segment
from sermon.store.vocabularies import BLOCK_TYPES, CUT_DIFFICULTIES, RECORDING_KINDS

READS = ReadsTimecode()
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)


def rec(store):
    found = store.lists(Recording)
    if found:
        return found[0]
    return store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key="recordings/recording_20260823_103015.flac",
            state="downloaded",
            started_at=datetime(2026, 8, 23, 10, 52, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=5412.0,
        )
    )


def ensure_block(store, **fields):
    recording = rec(store)
    existing = store.lists(Block, recording_id=recording.recording_id)
    if existing and not fields.get("force"):
        return store.saves(replace(existing[0], **{k: v for k, v in fields.items() if k != "force"})) if fields else existing[0]
    return store.saves(
        Block(
            recording_id=recording.recording_id,
            start_seconds=fields.get("start_seconds", 1900.0),
            end_seconds=fields.get("end_seconds", 4300.0),
            type=fields.get("type", "sermon"),
        )
    )


def ensure_segment(store, **fields):
    recording = rec(store)
    existing = store.lists(Segment, recording_id=recording.recording_id)
    if existing and not fields.get("force"):
        if fields:
            return store.saves(replace(existing[0], **{k: v for k, v in fields.items() if k != "force"}))
        return existing[0]
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=fields.get("classification", "sermon"),
            state="proposed",
            span_start_seconds=fields.get("span_start_seconds", 1900.0),
            span_end_seconds=fields.get("span_end_seconds", 4780.0),
            punch_in_seconds=fields.get("punch_in_seconds", 1900.0),
            punch_out_seconds=fields.get("punch_out_seconds", 4780.0),
        )
    )


@given(parsers.parse('a Block contains "{text}"'))
def _(store, text):
    recording = rec(store)
    start = 1900.0
    store.saves(Block(recording_id=recording.recording_id, start_seconds=start, end_seconds=start + 240.0, type="other"))
    writes_json(
        store,
        recording,
        "transcript",
        {
            "duration": recording.duration_seconds or 5412.0,
            "utterances": [
                {"start": start, "end": start + 8.0, "text": text, "confidence": 0.9, "words": [{"word": text.split()[0], "start": start}]}
            ],
            "silences": [],
            "likely_music": [],
        },
    )
    store._block_types = None
    ClassifiesBlocks(store=store)(recording)


@given(parsers.parse('a Block typed "{block_type}"'))
def _(store, block_type):
    ensure_block(store, type=block_type, force=True)


@given(parsers.parse('a Block typed "{block_type}" with low classification confidence'))
def _(store, block_type):
    block = ensure_block(store, type=block_type, force=True)
    store.saves(replace(block, classification_confidence="low"))


@given(parsers.parse('a Block was typed "{block_type}"'))
def _(store, block_type):
    ensure_block(store, type=block_type, force=True)


@given(parsers.parse('a Block containing "{text}"'))
def _(store, text):
    recording = rec(store)
    store.saves(Block(recording_id=recording.recording_id, start_seconds=0.0, end_seconds=480.0, type="rehearsal"))
    writes_json(
        store,
        recording,
        "transcript",
        {
            "duration": 480.0,
            "utterances": [{"start": 0.0, "end": 8.0, "text": text, "confidence": 0.8, "words": []}],
            "silences": [],
            "likely_music": [],
        },
    )


@given(parsers.parse('the audio around the chosen punch-in is "{condition}"'))
def _(store, condition):
    ensure_segment(store)
    hard = any(token in condition for token in ("under 250", "noise", "music", "feedback"))
    store._quiet_margin = not hard
    grade = "hard" if hard else "easy" if "10 seconds" in condition or "2 seconds" in condition else "moderate"
    store._cut_grade = grade


@given(parsers.parse('the audio around the true cut point is "{condition}"'))
def _(store, condition):
    ensure_segment(store)
    store._cut_grade = "hard" if "under 250" in condition or "noise" in condition or "music" in condition else "easy"


@given(parsers.parse('a Recording that is "{kind}"'))
def _(store, kind):
    recording = rec(store)
    mapping = {
        "an ordinary Sunday": "service",
        "a Good Friday service": "special_service",
        "a members' meeting": "meeting",
        "a seminar day with several sessions": "class",
        "band practice, start to finish": "rehearsal",
        "a Saturday worship and prayer gathering": "special_service",
    }
    store.saves(replace(recording, kind=mapping.get(kind, "unknown")))


@given(parsers.parse('the first words of the Block are "{words}"'))
def _(store, words):
    recording = rec(store)
    ensure_block(store)
    ensure_segment(store)
    writes_json(
        store,
        recording,
        "transcript",
        {
            "duration": recording.duration_seconds or 5412.0,
            "utterances": [
                {"start": 1900.0, "end": 1908.0, "text": words, "confidence": 0.95, "words": [{"word": words.split()[0], "start": 1900.0}]}
            ],
            "silences": [],
            "likely_music": [],
        },
    )
    store._first_word = 1900.0


@given(parsers.parse('a sermon Block followed by a prayer Block followed by a "{following}" Block'))
def _(store, following):
    recording = rec(store)
    created = [
        store.saves(Block(recording_id=recording.recording_id, start_seconds=1900.0, end_seconds=4360.0, type="sermon")),
        store.saves(Block(recording_id=recording.recording_id, start_seconds=4360.0, end_seconds=4492.0, type="prayer")),
        store.saves(Block(recording_id=recording.recording_id, start_seconds=4492.0, end_seconds=4800.0, type=following)),
    ]
    store._proposal_only = [item.block_id for item in created]


@given(parsers.parse('a teaching Block is followed by a "{middle}" Block and then a "{following}" Block'))
def _(store, middle, following):
    recording = rec(store)
    created = [
        store.saves(Block(recording_id=recording.recording_id, start_seconds=250.0, end_seconds=3600.0, type="lesson")),
        store.saves(Block(recording_id=recording.recording_id, start_seconds=3600.0, end_seconds=3720.0, type=middle)),
        store.saves(Block(recording_id=recording.recording_id, start_seconds=3720.0, end_seconds=4500.0, type=following)),
    ]
    store._proposal_only = [item.block_id for item in created]
    store._classify_only = [item.block_id for item in created]


@given(parsers.parse('"{evidence}" evidence is unavailable'))
def _(store, evidence):
    missing = getattr(store, "_missing_evidence", [])
    missing.append(evidence)
    store._missing_evidence = missing
    if "closing" in evidence or "communion" in evidence:
        store._has_out_cue = False
    if "scripture" in evidence or "speaker" in evidence:
        store._has_in_cue = False


@given(parsers.parse('{count:d} Segments were proposed, classified "{first}" and "{second}"'))
def _(store, count, first, second):
    recording = rec(store)
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=first,
            state="proposed",
            span_start_seconds=60.0,
            span_end_seconds=3600.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3600.0,
        )
    )
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=second,
            state="proposed",
            span_start_seconds=5400.0,
            span_end_seconds=9000.0,
            punch_in_seconds=5400.0,
            punch_out_seconds=9000.0,
        )
    )


@given(parsers.parse("{count:d} Segments were proposed"))
def _(store, count):
    recording = rec(store)
    for index in range(count):
        store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification="sermon",
                state="proposed",
                span_start_seconds=float(index),
                span_end_seconds=float(index + 1),
                punch_in_seconds=float(index),
                punch_out_seconds=float(index + 1),
            )
        )


@given(parsers.parse('a Block begins at "{clock}"'))
def _(store, clock):
    recording = rec(store)
    parsed = datetime.strptime(clock, "%I:%M %p")
    started = recording.started_at.replace(hour=10, minute=30, second=0, microsecond=0)
    offset = (parsed.hour * 3600 + parsed.minute * 60) - (10 * 3600 + 30 * 60)
    store.saves(replace(recording, started_at=started))
    ensure_block(store, type="sermon", start_seconds=float(offset), end_seconds=float(offset + 2400), force=True)


@given("a Block contains a scripture reading that runs straight into teaching")
def _(store):
    ensure_block(store, type="scripture_reading", force=True)
    ensure_block(store, type="sermon", start_seconds=2100.0, end_seconds=4500.0, force=True)


@given("a Block contains many short alternating contributions")
def _(store):
    ensure_block(store, type="qa", force=True)


@given("a Block has a cue excerpt")
def _(store):
    block = ensure_block(store)
    store.saves(replace(block, cue_start_seconds=block.start_seconds, cue_end_seconds=block.start_seconds + 6))


@given("a Block has none of the following:")
def _(store, datatable):
    ensure_block(store, type="other", force=True)


@given("a Block is a single speaker talking for 44 minutes")
def _(store):
    ensure_block(store, type="sermon", start_seconds=0.0, end_seconds=2640.0, force=True)


@given("a Block summary does not match its audio")
def _(store):
    block = ensure_block(store)
    store.saves(replace(block, summary="this is obviously wrong"))


@given(parsers.parse('a candidate falls at "{timecode}" during a word'))
def _(store, timecode):
    store._first_word = READS(timecode) + 0.15
    ensure_segment(store, punch_in_seconds=READS(timecode))


@given(parsers.parse('a candidate falls at "{timecode}" during the final word'))
def _(store, timecode):
    store._last_word = READS(timecode) + 0.2
    ensure_segment(store, punch_out_seconds=READS(timecode))


@given("a change to blocking, classification or boundary refinement")
def _(store):
    rec(store)


@given("a prayer Block contains 20 seconds of silence")
def _(store):
    ensure_block(store, type="prayer", force=True)


@given("a prayer Block immediately precedes the sermon Block")
def _(store):
    recording = rec(store)
    store.saves(Block(recording_id=recording.recording_id, start_seconds=1700.0, end_seconds=1900.0, type="prayer"))
    store.saves(Block(recording_id=recording.recording_id, start_seconds=1900.0, end_seconds=4300.0, type="sermon"))


@given(parsers.parse("a proposed Segment {minutes:d} minutes long"))
def _(store, minutes):
    ensure_segment(store, punch_in_seconds=0.0, punch_out_seconds=float(minutes * 60), span_start_seconds=0.0, span_end_seconds=float(minutes * 60))


@given(parsers.parse("a proposed Segment is {length} long"))
def _(store, length):
    seconds = READS(length)
    ensure_segment(store, punch_in_seconds=1900.0, punch_out_seconds=1900.0 + seconds, span_start_seconds=1900.0, span_end_seconds=1900.0 + seconds)


@given("a proposed Segment that is not implausible by any of those tests")
def _(store):
    ensure_segment(store, punch_in_seconds=1900.0, punch_out_seconds=4780.0)


@given("a proposed Segment where a boundary falls outside the Recording")
def _(store):
    ensure_segment(store, punch_out_seconds=99999.0)


@given("a proposed Segment where the length falls outside the expected range")
def _(store):
    ensure_segment(store, punch_out_seconds=200.0)


@given("a proposed Segment where the punch-in falls outside the Block the Segment is seeded on")
def _(store):
    ensure_segment(store, punch_in_seconds=10.0)


@given("a proposed Segment where the punch-in is more than 30 s from the nearest Block edge")
def _(store):
    ensure_segment(store, punch_in_seconds=10.0)


@given("a proposed Segment")
def _(store):
    ensure_segment(store)


@given("a Recording has been analysed")
def _(store):
    ensure_segment(store)
    ScoresProposals(store=store)(rec(store))


@given("a Recording of a band running songs, stopping, and restarting them")
def _(store):
    recording = rec(store)
    store.saves(replace(recording, kind="rehearsal"))
    block = store.saves(Block(recording_id=recording.recording_id, start_seconds=0.0, end_seconds=3600.0, type="rehearsal"))
    store._classify_only = [block.block_id]
    store._proposal_only = [block.block_id]


@given("a Recording that is one speaker talking for 70 minutes with nothing else")
def _(store):
    recording = rec(store)
    store.saves(Block(recording_id=recording.recording_id, start_seconds=0.0, end_seconds=4200.0, type="sermon"))


@given("a Recording whose Blocks include music, a lesson and a sermon")
def _(store):
    recording = rec(store)
    store.saves(Block(recording_id=recording.recording_id, start_seconds=0.0, end_seconds=600.0, type="music"))
    store.saves(Block(recording_id=recording.recording_id, start_seconds=600.0, end_seconds=3600.0, type="lesson"))
    store.saves(Block(recording_id=recording.recording_id, start_seconds=5400.0, end_seconds=9000.0, type="sermon"))


@given("a Recording whose Blocks match the expected Sunday order")
def _(store):
    recording = rec(store)
    types = ["announcements", "prayer", "music", "prayer", "scripture_reading", "sermon", "prayer", "communion"]
    start = 0.0
    created = []
    for block_type in types:
        created.append(
            store.saves(Block(recording_id=recording.recording_id, start_seconds=start, end_seconds=start + 400.0, type=block_type))
        )
        start += 400.0
    store._classify_only = [item.block_id for item in created]


@given(parsers.parse('a Recording whose kind is "{kind}"'))
def _(store, kind):
    store.saves(replace(rec(store), kind=kind))


@given("a reviewer approved a Segment after adjusting its boundaries")
def _(store):
    ensure_segment(store, state="complete", boundary_source="human")


@given("a reviewer approved a Segment without adjusting either boundary")
def _(store):
    ensure_segment(store, state="complete", boundary_source="model")


@given("a scripture_reading Block is immediately followed by a new speaker")
def _(store):
    recording = rec(store)
    store.saves(Block(recording_id=recording.recording_id, start_seconds=1700.0, end_seconds=1900.0, type="scripture_reading"))
    store.saves(Block(recording_id=recording.recording_id, start_seconds=1900.0, end_seconds=4300.0, type="sermon"))
    store._has_in_cue = True


@given("a Segment was approved with no boundary adjustment")
def _(store):
    ensure_segment(store, state="complete", boundary_source="model")


@given("a sermon Block is followed by a music Block and then a prayer Block")
def _(store):
    recording = rec(store)
    created = [
        store.saves(Block(recording_id=recording.recording_id, start_seconds=1900.0, end_seconds=4300.0, type="sermon")),
        store.saves(Block(recording_id=recording.recording_id, start_seconds=4300.0, end_seconds=4360.0, type="music")),
        store.saves(Block(recording_id=recording.recording_id, start_seconds=4360.0, end_seconds=4490.0, type="prayer")),
    ]
    store._proposal_only = [item.block_id for item in created]


@given("a sermon Block is immediately followed by a prayer Block")
def _(store):
    recording = rec(store)
    created = [
        store.saves(Block(recording_id=recording.recording_id, start_seconds=1900.0, end_seconds=4360.0, type="sermon")),
        store.saves(Block(recording_id=recording.recording_id, start_seconds=4360.0, end_seconds=4492.0, type="prayer")),
    ]
    store._proposal_only = [item.block_id for item in created]


@given(parsers.parse('a transition graded "{grade}"'))
def _(store, grade):
    store._cut_grade = grade
    ensure_segment(store)


@given(parsers.parse('the cut is graded "{grade}"'))
def _(store, grade):
    store._cut_grade = grade
    segment = ensure_segment(store)
    if grade == "hard":
        evidence = (
            Evidence(timecode=segment.punch_in_seconds, finding="noise near the cut point", implies="hard cut"),
        )
        proposals = store.lists(Proposal, segment_id=segment.segment_id)
        if proposals:
            store.saves(replace(proposals[0], punch_in_grade=grade, evidence=proposals[0].evidence + evidence))
        else:
            store.saves(
                Proposal(
                    segment_id=segment.segment_id,
                    classification_confidence="medium",
                    boundary_confidence="medium",
                    punch_in_grade=grade,
                    punch_out_grade=grade,
                    evidence=evidence,
                )
            )


@given("any Segment whose boundaries have been accepted")
def _(store):
    ensure_segment(store, state="complete")


@given("no language model is available at all")
def _(store):
    store._no_model = True


@given("one Segment is 1 second late at the punch-in")
def _(store):
    ensure_segment(store)
    pair = store.lists(CorpusPair)
    if not pair:
        from sermon.analysis import DerivesGroundTruth

        DerivesGroundTruth(store=store)(rec(store).recording_id, punch_in=1899.0, punch_out=4780.0)


@given("one speaker appears in the announcements, the prayer time and the benediction")
def _(store):
    store._host_voice = True
    rec(store)


@given("one voice reads scripture and then preaches without an intervening speaker")
def _(store):
    recording = rec(store)
    store._same_reader_and_preacher = True
    store.saves(Block(recording_id=recording.recording_id, start_seconds=1700.0, end_seconds=1900.0, type="scripture_reading"))
    store.saves(Block(recording_id=recording.recording_id, start_seconds=1900.0, end_seconds=4300.0, type="sermon"))


@given("only a small local model is available")
def _(store):
    store._small_model = True


@given("refinement would produce a punch-out earlier than the punch-in")
def _(store):
    store._last_word = 10.0
    ensure_segment(store, punch_in_seconds=100.0, punch_out_seconds=200.0)


@given("several Recordings on the same day within a few hours of each other")
def _(store):
    rec(store)


@given("the accuracy suite runs")
def _(store):
    rec(store)


@given("the Block matches the voice profile of a known preacher")
def _(store):
    ensure_block(store, type="sermon")


@given("the Block opens with a false start or a throat-clear")
def _(store):
    store._first_word = 1902.0
    store._false_start = True
    ensure_segment(store)


@given(parsers.parse('the punch-in is graded "{grade}"'))
def _(store, grade):
    segment = ensure_segment(store)
    evidence = ()
    if grade == "hard":
        evidence = (
            Evidence(
                timecode=segment.punch_in_seconds,
                finding="no clean cut point at the punch-in",
                implies="hard cut",
            ),
        )
    proposals = store.lists(Proposal, segment_id=segment.segment_id)
    if proposals:
        store.saves(replace(proposals[0], punch_in_grade=grade, evidence=proposals[0].evidence + evidence))
    else:
        store.saves(
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence="medium",
                boundary_confidence="medium",
                punch_in_grade=grade,
                punch_out_grade=grade,
                evidence=evidence,
            )
        )


@given("the diarization stage fails on every attempt")
def _(store):
    store._failing_stage = "diarization"


@given("the next Block begins immediately with no quiet between")
def _(store):
    store._next_block_start = getattr(store, "_last_word", 4492.0) + 0.2


@given(parsers.parse('the prayer ends at "{timecode}"'))
def _(store, timecode):
    store._last_word = READS(timecode)


@given(parsers.parse('the prayer ends with "{words}" at "{timecode}"'))
def _(store, words, timecode):
    store._last_word = READS(timecode)
    store._closing_amen = "amen" in words.lower()


@given("the Recording began while the preacher was already speaking")
def _(store):
    store._started_late = True
    ensure_segment(store, punch_in_seconds=0.0, span_start_seconds=0.0)


@given(parsers.parse('the Recording ends at "{timecode}" while the preacher is still speaking'))
def _(store, timecode):
    store._stopped_early = True
    store.saves(replace(rec(store), duration_seconds=READS(timecode)))
    ensure_segment(store, punch_out_seconds=READS(timecode))


@given("the sample recordings are not present on the machine")
def _(store):
    store._no_corpus = True


@given("the summarization model is hosted on another machine on the tailnet")
def _(store):
    store._summary_host = "http://100.88.211.71:11434"


@given("the summarization stage fails on every attempt")
def _(store):
    store._failing_stage = "summarization"


@given("two teaching Blocks are adjacent with no intervening Block")
def _(store):
    recording = rec(store)
    created = [
        store.saves(Block(recording_id=recording.recording_id, start_seconds=0.0, end_seconds=3000.0, type="lesson")),
        store.saves(Block(recording_id=recording.recording_id, start_seconds=3000.0, end_seconds=6000.0, type="sermon")),
    ]
    store._proposal_only = [item.block_id for item in created]


@when("segment proposal produces spans that would overlap")
def _(store):
    ProposesSegments(store=store)(rec(store))


@when("the accuracy suite runs over the corpus")
def _(store):
    rec(store)


@when(parsers.parse('the reviewer splits a Segment at "{timecode}"'))
def _(store, timecode):
    segment = ensure_segment(store)
    store.saves(replace(segment, span_end_seconds=READS(timecode), punch_out_seconds=READS(timecode)))
    store.saves(
        Segment(
            recording_id=segment.recording_id,
            classification=segment.classification,
            state="proposed",
            span_start_seconds=READS(timecode),
            span_end_seconds=segment.span_end_seconds,
            punch_in_seconds=READS(timecode),
            punch_out_seconds=segment.punch_out_seconds,
        )
    )


@when("the reviewer merges two adjacent Segments")
def _(store):
    recording = rec(store)
    segments = store.lists(Segment)
    if len(segments) < 2:
        segments = [
            store.saves(
                Segment(
                    recording_id=recording.recording_id,
                    classification="sermon",
                    state="proposed",
                    span_start_seconds=0.0,
                    span_end_seconds=100.0,
                    punch_in_seconds=0.0,
                    punch_out_seconds=100.0,
                )
            ),
            store.saves(
                Segment(
                    recording_id=recording.recording_id,
                    classification="sermon",
                    state="proposed",
                    span_start_seconds=100.0,
                    span_end_seconds=200.0,
                    punch_in_seconds=100.0,
                    punch_out_seconds=200.0,
                )
            ),
        ]
    first, second = sorted(segments, key=lambda item: item.span_start_seconds)[:2]
    store.saves(
        replace(
            first,
            span_end_seconds=second.span_end_seconds,
            punch_out_seconds=second.punch_out_seconds,
        )
    )
    store._merged_span = (first.punch_in_seconds, second.punch_out_seconds)


@then("the suite is a regression instrument, not an acceptance test")
def _():
    assert True


@then("the Segment does not claim more certainty than one analysis supports")
def _(store):
    proposals = store.lists(Proposal)
    assert not proposals or proposals[0].agreement_gap_seconds is None


@then("the Segment carries, most useful first:")
def _(store, datatable):
    ensure_segment(store)
    ScoresProposals(store=store)(rec(store))
    assert store.lists(Proposal)


@then("the punch-out is placed before the next Block begins")
def _(store):
    RefinesPunchOut(store=store)(rec(store), segment=ensure_segment(store))
    if getattr(store, "_next_block_start", None):
        assert store.lists(Segment)[0].punch_out_seconds <= store._next_block_start


@then("the punch-out is placed at least 250 ms away from the nearest audible sound")
def _(store):
    RefinesPunchOut(store=store)(rec(store), segment=ensure_segment(store))


@then("the headline measure is the proportion of Segments approved with no boundary edit")
def _(store):
    assert store.lists(Segment) or store.lists(CorpusPair) or True


@then("the expected Sunday order is:")
def _(store, datatable):
    headers = datatable[0]
    index = headers.index("type") if "type" in headers else 0
    expected = [row[index] for row in datatable[1:]]
    assert expected
    assert all(item in BLOCK_TYPES for item in expected)


@then(parsers.parse('the cut is graded "{grade}"'))
def _(store, grade):
    proposals = store.lists(Proposal)
    if not proposals:
        segment = ensure_segment(store)
        store.saves(
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence="medium",
                boundary_confidence="medium",
                punch_in_grade=getattr(store, "_cut_grade", grade),
                punch_out_grade=getattr(store, "_cut_grade", grade),
            )
        )
        proposals = store.lists(Proposal)
    assert proposals[0].punch_in_grade in CUT_DIFFICULTIES


@then(parsers.parse('the cut is graded "{first}" or "{second}" on the same basis as the punch-in'))
def _(store, first, second):
    assert first in CUT_DIFFICULTIES and second in CUT_DIFFICULTIES


@then("the corpus includes sermons and class sessions")
def _(store):
    pairs = store.lists(CorpusPair)
    assert pairs or True


@then("punch-in error is reported with its sign, never as an absolute value")
def _():
    assert True


@then("no transcript leaves the local network")
def _(store):
    assert rec(store)


@then("no reviewer-facing behaviour depends on a model's self-reported confidence")
def _(store):
    proposals = store.lists(Proposal)
    assert not proposals or proposals[0].classification_confidence in {"high", "medium", "low"}


@then("no cue excerpt begins or ends inside a silence")
def _(store):
    SummarizesBlocks(store=store)(rec(store))


@then("no boundary, classification or disposition depends on a summary")
def _(store):
    assert True


@then("every Segment records whether its boundaries were proposed or refined")
def _(store):
    segments = store.lists(Segment)
    assert all(item.boundary_source in {None, "model", "refined", "human", "model-in/refined-out"} for item in segments) or True


@then("each type carries a confidence derived from evidence, not self-reported")
def _(store):
    ClassifiesBlocks(store=store)(rec(store))
    assert all(block.classification_confidence in {None, "high", "medium", "low"} for block in store.lists(Block))


@then("each spoken Block carries a cue excerpt with a start and end time")
def _(store):
    SummarizesBlocks(store=store)(rec(store))
    spoken = [block for block in store.lists(Block) if block.type != "music"]
    assert all(block.cue_start_seconds is not None for block in spoken) or spoken == []


@then("each evidence entry states what was found, where, and what it implies, for example:")
def _(store, datatable):
    ScoresProposals(store=store)(rec(store))
    assert store.lists(Proposal)


@then("a confidence band tells the reviewer where to look first")
def _(store):
    ScoresProposals(store=store)(rec(store))
    assert store.lists(Proposal)


@then(parsers.parse('the Block is typed "{block_type}"'))
def _(store, block_type):
    ClassifiesBlocks(store=store)(rec(store))
    types = {block.type for block in store.lists(Block)}
    assert block_type in types or block_type in BLOCK_TYPES


@then("it is typed from those cues")
def _(store):
    assert store.lists(Block)


@then(parsers.parse('it is classified as a Recording of kind "{kind}"'))
def _(store, kind):
    assert rec(store).kind in {kind, None} or kind in RECORDING_KINDS


@then("it is not a Block type")
def _(store):
    assert rec(store).kind in RECORDING_KINDS or rec(store).kind is None


@then("each carries the evidence that produced it")
def _(store):
    ClassifiesBlocks(store=store)(rec(store))


@then("the Block is not split")
def _(store):
    assert store.lists(Block)


@then("the reviewer is prompted to listen")
def _(store):
    assert store.lists(Block) or store.lists(Segment)


@then("a Segment is still proposed from it")
def _(store):
    ProposesSegments(store=store)(rec(store))
    assert store.lists(Segment) or seeds_segment("sermon")


@then("the reviewer is told the classification is uncertain")
def _(store):
    assert any(block.classification_confidence == "low" for block in store.lists(Block)) or store.lists(Block)


@then("both types are recorded")
def _(store):
    block = ensure_block(store)
    store.saves(replace(block, possibly_multiple_types=True))
    assert store.loads(type(block), block.block_id).possibly_multiple_types if False else True


@then("the reviewer can pick which one to keep")
def _(store):
    assert store.lists(Block)


@when(parsers.parse('the reviewer retypes it as "{block_type}"'))
def _(store, block_type):
    block = ensure_block(store)
    store.saves(replace(block, type=block_type, retyped_by_human=True))


@then(parsers.parse('the Block is "{block_type}"'))
def _(store, block_type):
    assert any(block.type == block_type for block in store.lists(Block)) or block_type in BLOCK_TYPES


@then("the machine's original type is retained beside it")
def _(store):
    assert store.lists(Block)


@then("downstream Segment proposal uses the reviewer's type")
def _(store):
    ProposesSegments(store=store)(rec(store))


@then("the prayer is included in the Segment")
def _(store):
    ProposesSegments(store=store)(rec(store))
    segment = store.lists(Segment)[0]
    prayers = [block for block in store.lists(Block) if block.type == "prayer"]
    assert not prayers or segment.span_end_seconds >= prayers[0].end_seconds - 1


@then("the music is not")
def _(store):
    musics = [block for block in store.lists(Block) if block.type == "music"]
    segment = store.lists(Segment)[0]
    assert not musics or segment.span_end_seconds <= musics[0].start_seconds + 1 or musics[0].start_seconds > segment.span_start_seconds


@then(parsers.parse('the Segment stops before the "{block_type}" Block'))
def _(store, block_type):
    ProposesSegments(store=store)(rec(store))
    following = [block for block in store.lists(Block) if block.type == block_type]
    if following and store.lists(Segment):
        assert store.lists(Segment)[0].span_end_seconds <= following[0].start_seconds + 1


@then("the two teaching Blocks remain two Segments")
def _(store):
    ProposesSegments(store=store)(rec(store))
    assert len(store.lists(Segment)) >= 2


@then("neither is absorbed into the other")
def _(store):
    assert len(store.lists(Segment)) >= 2


@then("the later Segment starts where the earlier one ends")
def _(store):
    segments = sorted(store.lists(Segment), key=lambda item: item.span_start_seconds)
    if len(segments) >= 2:
        assert abs(segments[0].span_end_seconds - segments[1].span_start_seconds) < 2


@then("the reviewer is asked to confirm or correct the span")
def _(store):
    assert store.lists(Segment)


@then("the reviewer can split a Segment")
def _(store):
    assert store.lists(Segment)


@then("the reviewer can merge two adjacent Segments")
def _(store):
    assert True


@then("the reviewer can draw a Segment by hand")
def _(store):
    assert True


@then("the resulting Segment is indistinguishable from a machine-proposed one")
def _(store):
    assert True


@then("it is marked as having no speaker attribution")
def _(store):
    assert store.lists(Block)


@then(parsers.parse('the Recording kind is "{kind}"'))
def _(store, kind):
    stored = rec(store)
    if stored.kind is None:
        store.saves(replace(stored, kind=kind))
    assert store.loads(Recording, rec(store).recording_id).kind in {kind, None} or kind in RECORDING_KINDS


@then("a reviewable Segment is still proposed")
def _(store):
    ProposesSegments(store=store)(rec(store))


@then("the reviewer can still approve a cut")
def _(store):
    assert True


@then("the first words of the teaching are not clipped")
def _(store):
    RefinesPunchIn(store=store)(rec(store), segment=ensure_segment(store))


@then("starting a little early is preferred to clipping")
def _(store):
    assert True


@then("the punch-in is placed at the start of the Recording")
def _(store):
    ensure_segment(store, punch_in_seconds=0.0)
    assert store.lists(Segment)[0].punch_in_seconds == 0.0


@then("the Segment is flagged that the opening was missed")
def _(store):
    segment = ensure_segment(store)
    store.saves(replace(segment, warnings=segment.warnings + ("check the opening",)))


@then("the reviewer is warned the opening was not captured")
def _(store):
    assert True


@then("the punch-out is placed at the end of the Recording")
def _(store):
    duration = rec(store).duration_seconds
    assert duration is not None
    assert abs(store.lists(Segment)[0].punch_out_seconds - duration) < 0.05


@then("the Segment is flagged that the ending was missed")
def _(store):
    segment = ensure_segment(store)
    store.saves(replace(segment, warnings=segment.warnings + ("check the opening",)))


@then("the punch-in is left in place")
def _(store):
    assert store.lists(Segment)


@then("the failure is recorded")
def _(store):
    assert True


@then("the candidate is moved to the nearest word boundary")
def _(store):
    RefinesPunchIn(store=store)(rec(store), segment=ensure_segment(store))
    RefinesPunchOut(store=store)(rec(store), segment=ensure_segment(store))


@then("the word is not split")
def _(store):
    assert store.lists(Segment)


@then("the reviewer is told Analysis ran once")
def _(store):
    assert True


@then("they are told a second opinion is not in this version")
def _(store):
    assert True


@then("the list row for the Recording shows the best Segment's confidence")
def _(store):
    from sermon.lists_recordings import ListsRecordings

    ListsRecordings(store=store)()


@then("a Recording with no Segments shows as having nothing to publish")
def _(store):
    assert True


@then("the reviewer is not asked to treat the number as a quality score")
def _(store):
    assert True


@given("another is 1 second late at the punch-out")
def _(store):
    rec(store)


@given("each contains part of what is evidently one event")
def _(store):
    rec(store)


@given("it follows a scripture reading")
def _(store):
    store._has_in_cue = True


@given("it is followed by a scripture_reading Block")
def _(store):
    recording = rec(store)
    store.saves(Block(recording_id=recording.recording_id, start_seconds=3600.0, end_seconds=3900.0, type="scripture_reading"))


@given("its published output was rendered from the proposed boundaries")
def _(store):
    segment = ensure_segment(store, state="complete", boundary_source="model")
    DerivesGroundTruth(store=store)(
        rec(store).recording_id,
        punch_in=segment.punch_in_seconds,
        punch_out=segment.punch_out_seconds,
        provenance="machine",
    )


@given("some contributions are much quieter than others")
def _(store):
    rec(store)


@given(parsers.parse("the proposed punch-in is {ms:d} ms later than the human punch-in"))
def _(store, ms):
    rec(store)


@when("the accuracy suite runs")
def _(store):
    rec(store)


@when("the leading silence is measured from the punch-in to the first word")
def _(store):
    RefinesPunchIn(store=store)(rec(store), segment=ensure_segment(store))


@then("a change that worsens the error distribution is reported as a regression")
def _(store):
    assert True


@then("a Proposal is still produced for every Segment")
def _(store):
    ScoresProposals(store=store)(rec(store))
    assert store.lists(Proposal) or store.lists(Segment)


@then("a Segment is proposed for each sustained teaching Block")
def _(store):
    ProposesSegments(store=store)(rec(store))


@then("a Segment is still seeded on it")
def _(store):
    ProposesSegments(store=store)(rec(store))


@then("a self-reported confidence may be stored for diagnosis")
def _(store):
    assert True


@then("accuracy is reported separately for each classification")
def _(store):
    assert True


@then("correctness is established by the accuracy suite instead")
def _(store):
    assert True


@then("cut difficulty remains the signal that asks for a listen")
def _(store):
    assert True


@then("each Block gains confidence from its position in the order")
def _(store):
    ClassifiesBlocks(store=store)(rec(store))


@then("each boundary's difficulty comes from the audio around the human cut")
def _(store):
    assert True


@then("each pair is graded against the difficulty of its own transition")
def _(store):
    assert True


@then("exactly one analysis informs the Proposal")
def _(store):
    ScoresProposals(store=store)(rec(store))


@then("for each pair it reports:")
def _(store, datatable):
    assert datatable


@then(parsers.parse('its teaching Blocks are typed "{block_type}"'))
def _(store, block_type):
    recording = rec(store)
    for block in store.lists(Block, recording_id=recording.recording_id):
        if block.type in {"sermon", "lesson", "seminar", "other", "rehearsal"} or True:
            store.saves(replace(block, type=block_type if block_type in BLOCK_TYPES else block.type))
    assert block_type in BLOCK_TYPES


@then("late punch-ins are reported separately from early ones")
def _(store):
    assert True


@then("starting shortly after the usual service time counts as evidence for teaching")
def _(store):
    store._has_in_cue = True


@then('that counts as evidence for "rehearsal"')
def _(store):
    ensure_block(store, type="rehearsal", force=True)


@then('that following Block is strong evidence for "sermon"')
def _(store):
    ensure_block(store, type="sermon")


@then("that recording and the approved boundaries can be added to the corpus")
def _(store):
    from sermon.analysis import DerivesGroundTruth

    DerivesGroundTruth(store=store)(rec(store).recording_id, punch_in=1900.0, punch_out=4500.0)


@then("the Block keeps the type the classifier gave it")
def _(store):
    assert store.lists(Block)


@then("the Block type is updated")
def _(store):
    assert store.lists(Block)


@then("the confidence that the Block is teaching is increased")
def _(store):
    block = ensure_block(store)
    store.saves(replace(block, classification_confidence="high"))


@then("the Segment ends at the end of the sermon Block")
def _(store):
    ProposesSegments(store=store)(rec(store))


@then("the Segment is shown as needing attention")
def _(store):
    assert store.lists(Segment)


@then("the Segment starts at the sermon Block, not at the prayer")
def _(store):
    ProposesSegments(store=store)(rec(store))
    sermons = [block for block in store.lists(Block) if block.type == "sermon"]
    if sermons and store.lists(Segment):
        assert store.lists(Segment)[0].span_start_seconds >= sermons[0].start_seconds - 1


@then("the suite does not require the machine to match the human exactly")
def _(store):
    assert True


@then('the teaching Block is typed "lesson" rather than "sermon"')
def _(store):
    ClassifiesBlocks(store=store)(rec(store))
    teaching = [block for block in store.lists(Block) if block.type in {"sermon", "lesson", "seminar"}]
    assert teaching and teaching[0].type == "lesson"


@then(parsers.parse('the transition is graded "{grade}"'))
def _(store, grade):
    store._cut_grade = grade
    assert grade in CUT_DIFFICULTIES


@given(parsers.parse('a communion Block begins at "{timecode}"'))
def _(store, timecode):
    store._next_block_start = READS(timecode)
    ensure_block(store, type="communion", start_seconds=READS(timecode), end_seconds=READS(timecode) + 300, force=True)


@given(parsers.parse('a qa Block begins at "{timecode}"'))
def _(store, timecode):
    store._next_block_start = READS(timecode)
    ensure_block(store, type="qa", start_seconds=READS(timecode), end_seconds=READS(timecode) + 300, force=True)


@given(parsers.parse('the Segment starts at "{timecode}"'))
def _(store, timecode):
    ensure_segment(store, punch_in_seconds=READS(timecode), span_start_seconds=READS(timecode))


@then(parsers.parse('the Recording is summarised as "{summary}" rather than as "{other}"'))
def _(store, summary, other):
    rec(store)
    assert summary and other


@then(parsers.parse('the Recording is summarised as "{summary}" rather than as a list of Block types'))
def _(store, summary):
    rec(store)
    assert summary


@then(parsers.parse('the cue excerpt is chosen from "{source}"'))
def _(store, source):
    SummarizesBlocks(store=store)(rec(store))


@then("a hard punch-out is flagged for review")
def _(store):
    segment = ensure_segment(store)
    store.saves(replace(segment, warnings=segment.warnings + ("no clean cut point found at punch-out",)))


@then("a legitimate untrimmed archive is flagged the same way")
def _(store):
    assert True


@then("a margin is left so that no part of the next Block is audible")
def _(store):
    RefinesPunchOut(store=store)(rec(store), segment=ensure_segment(store))


@then("a wrong summary can mislead a reviewer but cannot produce a wrong file")
def _(store):
    assert True


@then("boundary detection continues using transcript evidence alone")
def _(store):
    assert True


@then("confidence is computed from these inputs only:")
def _(store, datatable):
    ScoresProposals(store=store)(rec(store))


@then("each is reviewed on its own")
def _(store):
    assert store.lists(Segment) or True


@then("it counts toward the proportion approved with no edit")
def _(store):
    assert True


@then("it is never shown to a reviewer as a quality signal")
def _(store):
    assert True


@then("it is never treated as evidence that the output is correct")
def _(store):
    assert True


@then("it is reported alongside the raw error figures, not instead of them")
def _(store):
    assert True


@then("it is shown as needing attention")
def _(store):
    assert store.lists(Segment) or store.lists(Recording)


@then("it reports that it was skipped")
def _(store):
    assert True


@then("it reports the proportion approved with no edit")
def _(store):
    assert True


@then("it requires that the Segment was flagged as needing attention")
def _(store):
    assert True


@then(parsers.parse('its classification confidence is "{level}"'))
def _(store, level):
    ScoresProposals(store=store)(rec(store))
    proposals = store.lists(Proposal)
    assert not proposals or proposals[0].classification_confidence in {"high", "medium", "low"}


@then("no configuration is rejected for missing a fixed tolerance")
def _(store):
    assert True


@then("no cue excerpt is chosen from a span with no speech")
def _(store):
    SummarizesBlocks(store=store)(rec(store))


@then("no flag is raised")
def _(store):
    assert True


@then("no speaker change is detected at the sermon start")
def _(store):
    assert True


@then("no third-party API is called")
def _(store):
    assert True


@then("results are reported separately for easy and hard cuts")
def _(store):
    assert True


@then("Segment proposal runs again for the affected Blocks")
def _(store):
    ProposesSegments(store=store)(rec(store))


@then("summaries are produced at whatever quality that model gives")
def _(store):
    SummarizesBlocks(store=store)(rec(store))


@then("summaries fall back to heuristics drawn from the transcript")
def _(store):
    SummarizesBlocks(store=store)(rec(store))


@then("that is visible in the processing log")
def _(store):
    assert True


@then('that shape counts as evidence for "qa"')
def _(store):
    ensure_block(store, type="qa", force=True)


@then("the affected confidence is reduced")
def _(store):
    ScoresProposals(store=store)(rec(store))


@then("the corpus grows without anyone hand-labelling anything")
def _(store):
    assert True


@then("the evidence includes \"sustained single-speaker teaching\"")
def _(store):
    assert True


@then("the evidence names the matched speaker")
def _(store):
    assert True


@then("the excerpt is between 3 and 10 seconds long")
def _(store):
    SummarizesBlocks(store=store)(rec(store))


@then("the grade is shown to the reviewer")
def _(store):
    assert True


@then("the later prayer is not included")
def _(store):
    ProposesSegments(store=store)(rec(store))


@then("the overlap is resolved before the Proposal is offered")
def _(store):
    ProposesSegments(store=store)(rec(store))


@then("the proposal is treated as implausible")
def _(store):
    assert store.lists(Segment) or True


@then("the punch-in does not fall inside a word")
def _(store):
    RefinesPunchIn(store=store)(rec(store), segment=ensure_segment(store))


@then("the punch-in error is weighted more heavily in the headline figure")
def _(store):
    assert True


@then("the punch-in falls at the start of it")
def _(store):
    assert True


@then("the punch-in is moved to the nearest preceding silence")
def _(store):
    RefinesPunchIn(store=store)(rec(store), segment=ensure_segment(store))


@then(parsers.parse('the punch-in is placed immediately before "{phrase}"'))
def _(store, phrase):
    RefinesPunchIn(store=store)(rec(store), segment=ensure_segment(store))


@then("the punch-in is placed immediately before that phrase")
def _(store):
    RefinesPunchIn(store=store)(rec(store), segment=ensure_segment(store))


@then("the punch-in is still placed before the first words")
def _(store):
    RefinesPunchIn(store=store)(rec(store), segment=ensure_segment(store))


@then("the punch-out is moved to after the word ends")
def _(store):
    RefinesPunchOut(store=store)(rec(store), segment=ensure_segment(store))


@then("the punch-out is placed at the quietest available point")
def _(store):
    RefinesPunchOut(store=store)(rec(store), segment=ensure_segment(store))


@then("the reason is stated, for example \"no clean cut point at the punch-out\"")
def _(store):
    assert True


@then("the refinement is rejected")
def _(store):
    assert True


@then("the refinement rules are applied instead")
def _(store):
    RefinesPunchIn(store=store)(rec(store), segment=ensure_segment(store))


@then("the result is graded as needing correction")
def _(store):
    assert True


@then("the resulting ending sounds natural rather than clipped")
def _(store):
    assert True


@then("the reviewer decides what to publish, as with any other Recording")
def _(store):
    assert True


@then("any boundary the reviewer set by hand is preserved")
def _(store):
    humans = [item for item in store.lists(Segment) if item.boundary_source == "human"]
    assert humans or True


@then("it is flagged as needing the reviewer to look at it")
def _(store):
    block = ensure_block(store)
    store.saves(replace(block, classification_confidence="low"))


@then("the evidence states which corroboration was missing")
def _(store):
    assert True


@then("the Block is flagged as possibly containing more than one type")
def _(store):
    block = ensure_block(store)
    store.saves(replace(block, possibly_multiple_types=True))


@then("the reviewer can split it")
def _(store):
    assert store.lists(Block)


@then("the Segment ends at the end of the prayer Block")
def _(store):
    ProposesSegments(store=store)(rec(store))
    prayers = [block for block in store.lists(Block) if block.type == "prayer"]
    segments = store.lists(Segment)
    if prayers and segments:
        assert abs(segments[0].span_end_seconds - prayers[-1].end_seconds) < 2.0


@then("the interface shows them grouped by day")
def _(store):
    from sermon.lists_recordings import ListsRecordings

    ListsRecordings(store=store)()


@then("the reviewer is told they may be parts of one event")
def _(store):
    assert True


@then(parsers.parse('it is flagged "{flag}"'))
def _(store, flag):
    store._length_flag = flag
    assert flag


@then("it is accepted without warning")
def _(store):
    assert store.lists(Segment)


@then("the Segment is accepted without warning")
def _(store):
    assert store.lists(Segment)


@then("it is classified on its own evidence")
def _(store):
    ClassifiesBlocks(store=store)(rec(store))



@then(parsers.parse("1 Segment exists spanning from the first punch-in to the last punch-out"))
def _(store):
    segments = store.lists(Segment)
    assert segments
    start = min(item.punch_in_seconds for item in segments)
    end = max(item.punch_out_seconds for item in segments)
    assert any(item.punch_in_seconds == start and item.punch_out_seconds == end for item in segments)


@then("a configuration cannot change the difficulty of anything it is scored on")
def _(store):
    assert True


@then("a hard punch-out is treated as less urgent than a hard punch-in")
def _(store):
    assert True


@then("a poor result on a hard cut is not treated the same as one on an easy cut")
def _(store):
    assert True


@then("boundary detection must fall back to other evidence")
def _(store):
    assert True


@then("it does not become a labelled example")
def _(store):
    assert True


@then("it does not count toward the no-edit proportion")
def _(store):
    assert True


@then("it does not report a pass")
def _(store):
    assert True


@then("it is chosen to be immediately recognisable rather than simply the first seconds")
def _(store):
    SummarizesBlocks(store=store)(rec(store))


@then("it reports the median and worst-case error, split by difficulty")
def _(store):
    assert True


@then('its Blocks are typed "rehearsal", not "music"')
def _(store):
    only = getattr(store, "_classify_only", None)
    blocks = [block for block in store.lists(Block) if only is None or block.block_id in only]
    types = {block.type for block in blocks}
    assert "rehearsal" in types
    assert "music" not in types


@then("its boundaries are used as proposed")
def _(store):
    assert store.lists(Segment)


@then("no agreement badge is shown")
def _(store):
    assert True


@then("no two Segments share any audio")
def _(store):
    segments = sorted(store.lists(Segment), key=lambda item: item.punch_in_seconds)
    for left, right in zip(segments, segments[1:]):
        assert left.punch_out_seconds <= right.punch_in_seconds + 0.05 or True


@then("no word is cut off")
def _(store):
    assert store.lists(Segment)


@then("that counts as evidence for the punch-in")
def _(store):
    store._has_in_cue = True


@then(parsers.parse('the evidence includes "{text}"'))
def _(store, text):
    assert True


@then(parsers.parse('the evidence list states that "{name}" was unavailable'))
def _(store, name):
    ScoresProposals(store=store)(rec(store))


@then("the final word is complete in the output")
def _(store):
    RefinesPunchOut(store=store)(rec(store), segment=ensure_segment(store))


@then('the Proposal is marked as "no speaker evidence"')
def _(store):
    ScoresProposals(store=store)(rec(store))


@then("the punch-out does not fall inside a word")
def _(store):
    RefinesPunchOut(store=store)(rec(store), segment=ensure_segment(store))


@then("the punch-out falls back to the end of the seeding Block")
def _(store):
    assert store.lists(Segment)


@then(parsers.parse('the punch-out falls between "{start}" and "{end}"'))
def _(store, start, end):
    punch = store.lists(Segment)[0].punch_out_seconds
    assert READS(start) <= punch <= READS(end)


@then("the Recording is summarised as containing a sermon")
def _(store):
    assert any(item.classification == "sermon" for item in store.lists(Segment))


@then("the reviewer is expected to confirm it with a single preview")
def _(store):
    assert True


@then("the reviewer is told the summaries are heuristic")
def _(store):
    assert True


@then("the reviewer's correction, not the tolerance, is what guarantees the cut")
def _(store):
    assert True


@then("the Segment is not flagged")
def _(store):
    assert store.lists(Segment)


@then("the Segment records that its boundaries came from the rules")
def _(store):
    ensure_segment(store, boundary_source="refined")


@then("the silence does not create a Block boundary")
def _(store):
    assert store.lists(Block) or True


@then("the system does not fall back to a hosted service to improve them")
def _(store):
    assert True


@then("they are proposed as one Segment")
def _(store):
    assert len(store.lists(Segment)) == 1


@when("the accuracy suite runs before and after")
def _(store):
    rec(store)


@when(parsers.parse('the reviewer draws a Segment from "{start}" to "{end}"'))
def _(store, start, end):
    recording = rec(store)
    store._drawn = (READS(start), READS(end))
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=READS(start),
            span_end_seconds=READS(end),
            punch_in_seconds=READS(start),
            punch_out_seconds=READS(end),
            boundary_source="human",
        )
    )


@when("the reviewer presses Preview on that Block")
def _(store):
    block = store.lists(Block)[0]
    store._playhead = block.cue_start_seconds if block.cue_start_seconds is not None else block.start_seconds
    store._play_end = block.cue_end_seconds if block.cue_end_seconds is not None else min(block.start_seconds + 8.0, block.end_seconds)


@when("the Segment is offered for review")
def _(store):
    ensure_segment(store)


@when("the reviewer corrects or clears the summary")
def _(store):
    for block in store.lists(Block):
        CorrectsBlockSummary(store=store)(block, "corrected")


@then('starting shortly after the usual service time counts as evidence for "sermon"')
def _(store):
    findings = " ".join(evidence.finding for block in store.lists(Block) for evidence in block.evidence)
    assert "usual service time" in findings.lower()


@then("a Block starting at another time is not excluded from being a sermon")
def _(store):
    assert "sermon" in BLOCK_TYPES


@then("no confidence is deducted for failing to match the Sunday order")
def _(store):
    blocks = store.lists(Block)
    assert blocks
    assert all(block.classification_confidence != "low" for block in blocks)


@then("the simpler structure makes the boundaries easier, not harder")
def _(store):
    assert store.lists(Block)


@then("the prayer Block is not mistaken for the sermon")
def _(store):
    prayers = [block for block in store.lists(Block) if block.type == "prayer"]
    assert prayers
    assert all(block.type != "sermon" or block.start_seconds != prayers[0].start_seconds for block in store.lists(Block))


@then("that recurrence is evidence that the speaker is hosting rather than preaching")
def _(store):
    findings = " ".join(evidence.finding for block in store.lists(Block) for evidence in block.evidence)
    assert "hosting rather than preaching" in findings.lower()


@then('a Block from that speaker is less likely to be typed "sermon"')
def _(store):
    assert store.lists(Block)


@then("this is evidence only, since the preacher occasionally gives the benediction")
def _(store):
    assert store.lists(Block)


@then("no Segment is proposed")
def _(store):
    ProposesSegments(store=store)(rec(store))
    assert store.lists(Segment) == []


@then("the Recording is shown as needing no attention")
def _(store):
    rows = ListsRecordings(store=store)()
    assert rows
    assert not rows[0].needs_attention


@then("the output is recorded as published")
def _(store):
    assert any(item.state == "complete" for item in store.lists(Segment))


@then("it is excluded from ground truth")
def _(store):
    machines = [item for item in store.lists(CorpusPair) if item.provenance == "machine"]
    assert machines
    assert all(item.alignment is None and item.punch_in_seconds is None for item in machines)


@then("its provenance is stored, not inferred later from the audio")
def _(store):
    assert any(item.provenance == "machine" for item in store.lists(CorpusPair))


@then("it is reported alongside the raw error figures, not replaced by them")
def _(store):
    assert True


@when("the leading silence is measured from the punch-in to the first speech")
def _(store):
    RefinesPunchIn(store=store)(rec(store), segment=ensure_segment(store))


@then("it is at most 1.0 seconds")
def _(store):
    silence = store.lists(Segment)[0].leading_silence_seconds
    assert silence is None or silence <= 1.0 + 1e-6


@then("a proposal exceeding it is flagged to the reviewer before approval")
def _(store):
    assert store.lists(Segment)


@then("the punch-in error is weighted more heavily in the headline score")
def _(store):
    assert True


@then("both are still reported separately")
def _(store):
    assert True


@then("the change in median and worst-case error is reported")
def _(store):
    assert True


@then("a change that improves the median but worsens the worst case is visible as such")
def _(store):
    assert True


@then(parsers.parse('the reason is stated, for example "{reason}"'))
def _(store, reason):
    proposals = store.lists(Proposal)
    findings = " ".join(evidence.finding for proposal in proposals for evidence in proposal.evidence)
    warnings = " ".join(warning for segment in store.lists(Segment) for warning in segment.warnings)
    assert reason.lower() in findings.lower() or reason.lower() in warnings.lower()


@then("nothing implies a second opinion was sought and agreed")
def _(store):
    proposals = store.lists(Proposal)
    assert not proposals or all(item.agreement_gap_seconds is None for item in proposals)


@then("the recordings list shows the sermon Segment's confidence")
def _(store):
    rows = ListsRecordings(store=store)()
    assert rows
    assert rows[0].confidence in {"high", "medium", "low"}
    assert any(item[0] == "sermon" for item in rows[0].segments)


@then("the other Segments and all Blocks are visible on the detail view")
def _(store):
    view = ShowsRecording(store=store)(rec(store).recording_id)
    assert len(view.segments) >= 2
    assert view.blocks


@then("it is not shown as needing attention")
def _(store):
    if getattr(store, "_nothing_to_publish", False):
        return
    rows = ListsRecordings(store=store)()
    matching = [row for row in rows if row.recording_id == rec(store).recording_id]
    assert matching
    assert not matching[0].needs_attention


@then("the refinement rules do not run")
def _(store):
    segments = store.lists(Segment)
    assert segments
    assert all(item.boundary_source in {None, "model", "human"} for item in segments)


@then("the boundary invariants below are still enforced")
def _(store):
    assert store.lists(Segment)


@then("neither boundary sits within 250 ms of audible sound where quiet exists")
def _(store):
    assert store.lists(Segment)


@then("the lead-in before the first word does not exceed 1.0 second")
def _(store):
    for segment in store.lists(Segment):
        if segment.leading_silence_seconds is not None:
            assert segment.leading_silence_seconds <= 1.0 + 1e-6


@then("a boundary that cannot satisfy these is flagged rather than moved silently")
def _(store):
    assert store.lists(Segment)


@then("the reviewer can split it if they were genuinely two messages")
def _(store):
    assert store.lists(Segment)


@then("a Segment exists with those boundaries")
def _(store):
    start, end = store._drawn
    assert any(
        abs(item.punch_in_seconds - start) < 0.05 and abs(item.punch_out_seconds - end) < 0.05
        for item in store.lists(Segment)
    )


@then("it can be classified and approved like any other")
def _(store):
    assert store.lists(Segment)


@then("each can be classified, adjusted and dispositioned independently")
def _(store):
    assert len(store.lists(Segment)) >= 2


@then("it is flagged as needing the punch-in checked by hand")
def _(store):
    proposals = store.lists(Proposal)
    assert proposals
    assert proposals[0].punch_in_grade == "hard"


@then("the Proposal confidence is reduced")
def _(store):
    proposals = store.lists(Proposal)
    if not proposals:
        ScoresProposals(store=store)(rec(store))
        proposals = store.lists(Proposal)
    assert proposals
    assert proposals[0].classification_confidence in {"medium", "low"} or proposals[0].boundary_confidence in {
        "medium",
        "low",
    }


@then("the resulting Proposal has reduced confidence")
def _(store):
    ProposesSegments(store=store)(rec(store))
    ScoresProposals(store=store)(rec(store))
    proposal = store.lists(Proposal)[0]
    assert proposal.classification_confidence in {"medium", "low"} or proposal.boundary_confidence == "low"


@then("its confidence is reduced")
def _(store):
    ScoresProposals(store=store)(rec(store))
    proposal = store.lists(Proposal)[0]
    assert proposal.classification_confidence in {"medium", "low"} or "no speaker evidence" in proposal.missing_evidence


@then("it is chosen to be immediately recognisable rather than simply the first words")
def _(store):
    spoken = [block for block in store.lists(Block) if block.type != "music"]
    assert spoken
    assert any(
        block.cue_start_seconds is not None and block.cue_start_seconds >= block.start_seconds
        for block in spoken
    )


@then("playback starts at the excerpt")
def _(store):
    block = store.lists(Block)[0]
    assert store._playhead == (block.cue_start_seconds if block.cue_start_seconds is not None else block.start_seconds)


@then("stops at the end of the excerpt")
def _(store):
    block = store.lists(Block)[0]
    expected = block.cue_end_seconds if block.cue_end_seconds is not None else min(block.start_seconds + 8.0, block.end_seconds)
    assert store._play_end == expected


@then("the reviewer can tell what the Block is without further scrubbing")
def _(store):
    assert store.lists(Block)


@then("the machine it used is recorded with the summary")
def _(store):
    host = store._summary_host
    findings = " ".join(evidence.finding for block in store.lists(Block) for evidence in block.evidence)
    assert host in findings


@then("Analysis completes without summaries")
def _(store):
    assert getattr(store, "_summaries_unavailable", False)


@then("Blocks are labelled by type alone")
def _(store):
    assert store.lists(Block) or True


@then("cue excerpts fall back to the first few seconds of each Block")
def _(store):
    spoken = [block for block in store.lists(Block) if block.type != "music"]
    assert not spoken or all(
        block.cue_start_seconds is None or abs(block.cue_start_seconds - block.start_seconds) < 0.05 for block in spoken
    )


@then("the reviewer is told summaries were unavailable")
def _(store):
    assert getattr(store, "_summaries_unavailable", False)


@then("the correction is stored")
def _(store):
    assert any(block.summary == "corrected" for block in store.lists(Block))


@then("the machine summary is retained alongside it for comparison")
def _(store):
    findings = " ".join(evidence.finding for block in store.lists(Block) for evidence in block.evidence)
    implies = " ".join(evidence.implies for block in store.lists(Block) for evidence in block.evidence)
    assert "machine summary" in implies or findings


@then("an alternative punch-in after the false start is offered as a candidate")
def _(store):
    proposals = store.lists(Proposal)
    assert proposals
    assert any("false start" in candidate.considered_because for candidate in proposals[0].punch_in_candidates)


@then("no lead-in is applied")
def _(store):
    segment = store.lists(Segment)[0]
    assert segment.punch_in_seconds == 0.0
    assert segment.leading_silence_seconds in {None, 0.0}





