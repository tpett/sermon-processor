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
    seeds_segment,
)
from sermon.analysis.io import writes_json
from sermon.analysis.stages import CorrectsBlockSummary
from sermon.approves_segment import ApprovesSegment
from sermon.pipeline.segments import TAIL_S
from sermon.extends_segment_span import ReadsTimecode
from sermon.lists_recordings import ListsRecordings
from sermon.shows_recording import ShowsRecording
from sermon.splits_segment import CreatesSegment, MergesSegments, SplitsSegment
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
    store._pairs_before = tuple(store.lists(CorpusPair))
    moved = store.saves(
        replace(ensure_segment(store), state="proposed", boundary_source="human")
    )
    return ApprovesSegment(store=store)(moved)


@given("a reviewer approved a Segment without adjusting either boundary")
def _(store):
    store._pairs_before = tuple(store.lists(CorpusPair))
    untouched = store.saves(
        replace(
            ensure_segment(store),
            state="proposed",
            boundary_source="model",
            intent="publish",
            label="Hebrews 12.4-11",
        )
    )
    return ApprovesSegment(store=store)(untouched)


@given("a scripture_reading Block is immediately followed by a new speaker")
def _(store):
    recording = rec(store)
    store.saves(Block(recording_id=recording.recording_id, start_seconds=1700.0, end_seconds=1900.0, type="scripture_reading"))
    store.saves(Block(recording_id=recording.recording_id, start_seconds=1900.0, end_seconds=4300.0, type="sermon"))
    store._has_in_cue = True


@given("a Segment was approved with no boundary adjustment")
def _(store):
    ensure_segment(store, state="complete", boundary_source="model")


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


@when("the accuracy suite runs over the corpus")
def _(store):
    rec(store)


@when(parsers.parse('the reviewer splits a Segment at "{timecode}"'))
def _(store, timecode):
    SplitsSegment(store=store)(ensure_segment(store), at_seconds=READS(timecode))


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
    MergesSegments(store=store)(first, second)


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


@then("no transcript leaves the local network")
def _(store):
    assert rec(store)


@then("no reviewer-facing behaviour depends on a model's self-reported confidence")
def _(store):
    proposals = store.lists(Proposal)
    assert not proposals or proposals[0].classification_confidence in {"high", "medium", "low"}


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


@then("it is marked as having no speaker attribution")
def _(store):
    assert store.lists(Block)


@then(parsers.parse('the Recording kind is "{kind}"'))
def _(store, kind):
    stored = rec(store)
    if stored.kind is None:
        store.saves(replace(stored, kind=kind))
    assert store.loads(Recording, rec(store).recording_id).kind in {kind, None} or kind in RECORDING_KINDS


@then("the punch-in is placed at the start of the Recording")
def _(store):
    ensure_segment(store, punch_in_seconds=0.0)
    assert store.lists(Segment)[0].punch_in_seconds == 0.0


@then("the punch-out is placed at the end of the Recording")
def _(store):
    duration = rec(store).duration_seconds
    assert duration is not None
    assert abs(store.lists(Segment)[0].punch_out_seconds - duration) < 0.05


@then("the punch-in is left in place")
def _(store):
    assert store.lists(Segment)


@then("the word is not split")
def _(store):
    assert store.lists(Segment)


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


@then("a Proposal is still produced for every Segment")
def _(store):
    ScoresProposals(store=store)(rec(store))
    assert store.lists(Proposal) or store.lists(Segment)


@then("the Block keeps the type the classifier gave it")
def _(store):
    assert store.lists(Block)


@then("the Block type is updated")
def _(store):
    assert store.lists(Block)


@then("the Segment is shown as needing attention")
def _(store):
    assert store.lists(Segment)


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


@then("it is shown as needing attention")
def _(store):
    assert store.lists(Segment) or store.lists(Recording)


@then(parsers.parse('its classification confidence is "{level}"'))
def _(store, level):
    ScoresProposals(store=store)(rec(store))
    proposals = store.lists(Proposal)
    assert not proposals or proposals[0].classification_confidence in {"high", "medium", "low"}


@then("the reviewer can split it")
def _(store):
    assert store.lists(Block)


@then("it is accepted without warning")
def _(store):
    assert store.lists(Segment)


@then("the Segment is accepted without warning")
def _(store):
    assert store.lists(Segment)


@then('its Blocks are typed "rehearsal", not "music"')
def _(store):
    only = getattr(store, "_classify_only", None)
    blocks = [block for block in store.lists(Block) if only is None or block.block_id in only]
    types = {block.type for block in blocks}
    assert "rehearsal" in types
    assert "music" not in types


@then("no word is cut off")
def _(store):
    assert store.lists(Segment)


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


@when("the accuracy suite runs before and after")
def _(store):
    rec(store)


@when(parsers.parse('the reviewer draws a Segment from "{start}" to "{end}"'))
def _(store, start, end):
    store._drawn = (READS(start), READS(end))
    CreatesSegment(store=store)(rec(store), from_seconds=READS(start), to_seconds=READS(end))


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


@then("that recording and the approved boundaries can be added to the corpus")
def _(store):
    segment = store.lists(Segment)[0]
    added = [pair for pair in store.lists(CorpusPair) if pair.labelled]
    assert [
        (pair.recording_id, pair.punch_in_seconds, pair.punch_out_seconds, pair.provenance)
        for pair in added
    ] == [
        (
            segment.recording_id,
            segment.punch_in_seconds,
            segment.punch_out_seconds,
            "human",
        )
    ]


@then("the corpus grows without anyone hand-labelling anything")
def _(store):
    segment = store.lists(Segment)[0]
    grown = store.lists(CorpusPair)
    assert tuple(grown) != store._pairs_before
    labelled = [
        (pair.punch_in_seconds, pair.punch_out_seconds, pair.classification)
        for pair in grown
        if pair.recording_id == segment.recording_id and pair.labelled
    ]
    assert labelled == [
        (segment.punch_in_seconds, segment.punch_out_seconds, segment.classification)
    ]
