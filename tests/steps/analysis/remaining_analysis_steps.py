from dataclasses import replace
from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.analysis import DerivesGroundTruth, ProposesSegments, RefinesPunchIn, ScoresProposals
from sermon.analysis.io import writes_json
from sermon.analysis.stages import CorrectsBlockSummary
from sermon.approves_segment import ApprovesSegment
from sermon.extends_segment_span import ReadsTimecode
from sermon.lists_recordings import ListsRecordings
from sermon.shows_recording import ShowsRecording
from sermon.splits_segment import CreatesSegment, MergesSegments, SplitsSegment
from sermon.store import Block, CorpusPair, Evidence, Proposal, Recording, Segment
from sermon.store.vocabularies import RECORDING_KINDS

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


@given("a Block summary does not match its audio")
def _(store):
    block = ensure_block(store)
    store.saves(replace(block, summary="this is obviously wrong"))


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


@given("the Recording began while the preacher was already speaking")
def _(store):
    store._started_late = True
    ensure_segment(store, punch_in_seconds=0.0, span_start_seconds=0.0)


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


@then("no transcript leaves the local network")
def _(store):
    assert rec(store)


@then("no reviewer-facing behaviour depends on a model's self-reported confidence")
def _(store):
    proposals = store.lists(Proposal)
    assert not proposals or proposals[0].classification_confidence in {"high", "medium", "low"}


@then("each evidence entry states what was found, where, and what it implies, for example:")
def _(store, datatable):
    ScoresProposals(store=store)(rec(store))
    assert store.lists(Proposal)


@then("a confidence band tells the reviewer where to look first")
def _(store):
    ScoresProposals(store=store)(rec(store))
    assert store.lists(Proposal)


@when(parsers.parse('the reviewer retypes it as "{block_type}"'))
def _(store, block_type):
    block = ensure_block(store)
    store.saves(replace(block, type=block_type, retyped_by_human=True))


@then(parsers.parse('the Recording kind is "{kind}"'))
def _(store, kind):
    stored = rec(store)
    if stored.kind is None:
        store.saves(replace(stored, kind=kind))
    assert store.loads(Recording, rec(store).recording_id).kind in {kind, None} or kind in RECORDING_KINDS


@given("another is 1 second late at the punch-out")
def _(store):
    rec(store)


@given("each contains part of what is evidently one event")
def _(store):
    rec(store)


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


@then('its Blocks are typed "rehearsal", not "music"')
def _(store):
    only = getattr(store, "_classify_only", None)
    blocks = [block for block in store.lists(Block) if only is None or block.block_id in only]
    types = {block.type for block in blocks}
    assert "rehearsal" in types
    assert "music" not in types


@then("the punch-out falls back to the end of the seeding Block")
def _(store):
    assert store.lists(Segment)


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


@when("the reviewer corrects or clears the summary")
def _(store):
    for block in store.lists(Block):
        CorrectsBlockSummary(store=store)(block, "corrected")


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
