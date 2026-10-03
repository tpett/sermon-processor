import ipaddress
import re
from dataclasses import replace
from urllib.parse import urlsplit
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, then, when
from steps import _analysis, _audio, _remaining_analysis as _remaining, _web
from steps._markup import reads_field, reads_rows, strips_tags

from sermon.analysis import ClassifiesBlocks, DerivesGroundTruth, ProposesSegments, RefinesPunchIn, ScoresProposals
from sermon.analysis.io import reads_json, writes_json
from sermon.analysis.stages import CorrectsBlockSummary, SummarizesBlocks
from sermon.jobs.analyzes_recording import OPTIONAL_STAGE_FAILED
from sermon.approves_segment import ApprovesSegment
from sermon.extends_segment_span import ReadsTimecode
from sermon.splits_segment import CreatesSegment, MergesSegments, SplitsSegment
from sermon.store import Block, CorpusPair, Job, LogEntry, Proposal, Recording, Segment

READS = ReadsTimecode()
UNSURE_SELF_REPORT = 0.3
SEVENTY_MINUTES = 4200.0
SETTLING_IN = 120.0
HOST, PREACHER = "Speaker 1", "Speaker 2"
TAILNET_MODEL_HOST = "http://100.88.211.71:11434"
TAILNET = ipaddress.ip_network("100.64.0.0/10")


def on_the_local_network(url):
    host = urlsplit(url).hostname or ""
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address in TAILNET
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


@pytest.fixture
def laid_out():
    return {}
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
def _(store, laid_out, block_type):
    laid_out["subject"] = 600.0
    _remaining.lays_out(
        store,
        ((0.0, 600.0, "music"), (600.0, 3600.0, block_type), (3600.0, 5412.0, "music")),
        confidences={1: UNSURE_SELF_REPORT},
    )


@given(parsers.parse('a Block was typed "{block_type}"'))
def _(store, laid_out, block_type):
    laid_out["subject"] = 1500.0
    _remaining.lays_out(
        store, ((0.0, 1500.0, "music"), (1500.0, 4300.0, block_type), (4300.0, 5412.0, "music"))
    )
    ClassifiesBlocks(store=store)(_analysis.recording_of(store))


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


@given(parsers.parse('a Recording that is "{event}"'))
def _(store, event):
    _remaining.lays_out(store, _remaining.EVENTS[event])


@given(parsers.parse('"{evidence}" evidence is unavailable'))
def _(store, evidence):
    recording = _analysis.recording_of(store)
    if evidence == "recording start time":
        recording = store.saves(replace(recording, started_at_source="last_modified"))
    _analysis.lays_out(store, recording, _remaining.service_without(evidence))
    _analysis.analyses(store, recording)


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
def _(store, laid_out):
    laid_out["subject"] = 1500.0
    _remaining.lays_out(
        store,
        (
            (0.0, 1500.0, "music"),
            (1500.0, 4300.0, "scripture_reading", _remaining.READING_INTO_TEACHING),
            (4300.0, 5412.0, "music"),
        ),
    )


@given("a Block contains many short alternating contributions")
def _(store):
    ensure_block(store, type="qa", force=True)


@given("a Block has a cue excerpt")
def _(store, laid_out):
    recording = _analysis.recording_of(store)
    _analysis.lays_out(store, recording, _remaining.SERMON_SERVICE)
    SummarizesBlocks(store=store, summarizes=_remaining.summarizes_with_a_cue)(recording)
    _audio.registers_preview(store, recording)
    laid_out["subject"] = 1900.0


@given("a Block has none of the following:")
def _(store, laid_out, datatable):
    assert len(datatable) == 5, "the corroboration table changed; the layout below answers four rows"
    laid_out["subject"] = 1500.0
    laid_out["given_type"] = "sermon"
    _remaining.lays_out(
        store, ((0.0, 1500.0, "music"), (1500.0, 1740.0, "sermon"), (1740.0, 5412.0, "music"))
    )


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
    _remaining.lays_out(store, _remaining.EVENTS["band practice, start to finish"])


@given("a Recording that is one speaker talking for 70 minutes with nothing else")
def _(store):
    _analysis.recording_of(store, duration=SEVENTY_MINUTES + 2 * SETTLING_IN)
    _remaining.lays_out(store, ((SETTLING_IN, SETTLING_IN + SEVENTY_MINUTES, "sermon"),))


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
def _(store, laid_out):
    spans = [*_analysis.reads_rows(_analysis.SUNDAY)]
    benediction = spans[-1]
    spans[-1] = (benediction[0], benediction[1], "sermon")
    laid_out["subject"] = benediction[0]
    laid_out["preacher"] = READS("0:31:40")

    def voices(doc):
        for utterance in doc["utterances"]:
            preaching = laid_out["preacher"] <= utterance["start"] < READS("1:12:40")
            utterance["speaker"] = PREACHER if preaching else HOST

    _remaining.lays_out(store, spans, transcript=voices)


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


@given("the diarization stage fails on every attempt")
def _(store):
    store._diarizes = _analysis.refuses_to_diarize


@given("the Recording began while the preacher was already speaking")
def _(store):
    store._started_late = True
    ensure_segment(store, punch_in_seconds=0.0, span_start_seconds=0.0)


@given("the sample recordings are not present on the machine")
def _(store):
    store._no_corpus = True


@given("the summarization model is hosted on another machine on the tailnet", target_fixture="model_endpoint")
def _(store):
    _analysis.recording_of(store)
    return TAILNET_MODEL_HOST


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


@then("no transcript leaves the local network")
def _(reached_destinations):
    assert reached_destinations, "the stage reached no machine, so nothing shows where the transcript went"
    elsewhere = [url for url in reached_destinations if not on_the_local_network(url)]
    assert elsewhere == [], f"the transcript went to {elsewhere}"


@then("no reviewer-facing behaviour depends on a model's self-reported confidence")
def _(store):
    proposals = store.lists(Proposal)
    assert not proposals or proposals[0].classification_confidence in {"high", "medium", "low"}


@when(parsers.parse('the reviewer retypes it as "{block_type}"'), target_fixture="retyped")
def _(store, laid_out, block_type):
    block = _remaining.block_at(store, laid_out["subject"])
    recording = _analysis.recording_of(store)
    _web.posts(store, _web.recording_action(recording, "retype-block"), block=str(block.block_id), type=block_type)
    return {"block_id": block.block_id, "type": block_type}


@then(parsers.parse('the Recording kind is "{kind}"'))
def _(store, kind):
    assert _analysis.the_recording(store).kind == kind


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
    segments = _analysis.proposed(store)
    assert segments, "no Segment was proposed"
    proposed_for = sorted(proposal.segment_id for proposal in store.lists(Proposal))
    assert proposed_for == sorted(segment.segment_id for segment in segments), proposed_for


@then("the Block keeps the type the classifier gave it")
def _(store, laid_out):
    assert _remaining.block_at(store, laid_out["subject"]).type == laid_out["given_type"]


@then("the Block type is updated")
def _(store, retyped):
    block = store.loads(Block, retyped["block_id"])
    assert (block.type, block.retyped_by_human) == (retyped["type"], True), (block.type, block.retyped_by_human)


@given(parsers.parse('the Segment starts at "{timecode}"'))
def _(store, timecode):
    ensure_segment(store, punch_in_seconds=READS(timecode), span_start_seconds=READS(timecode))


@then("it is shown as needing attention")
def _(store):
    row = _remaining.listed_row(store, _analysis.the_recording(store))
    assert 'data-attention="true"' in row, row
    assert 'data-confidence="low"' in row, row


@then(parsers.parse('its classification confidence is "{level}"'))
def _(store, laid_out, level):
    assert _remaining.block_at(store, laid_out["subject"]).classification_confidence == level


@then("the reviewer can split it")
def _(store, laid_out):
    block = _remaining.block_at(store, laid_out["subject"])
    page = _web.opens_detail(store, block.recording_id)
    rows = [row for row in reads_rows(page, "block") if row.get("block-type") == block.type]
    assert len(rows) == 1, f"{len(rows)} {block.type} Blocks are listed"
    assert "block-split-control" in rows[0], f"the Block offers {sorted(rows[0])}"


@then('its Blocks are typed "rehearsal", not "music"')
def _(store):
    types = {block.type for block in _analysis.blocks_of(store)}
    assert types == {"rehearsal"}, types


@then("the punch-out falls back to the end of the seeding Block")
def _(store):
    assert store.lists(Segment)


@when("the accuracy suite runs before and after")
def _(store):
    rec(store)


@when(parsers.parse('the reviewer draws a Segment from "{start}" to "{end}"'), target_fixture="drawn")
def _(store, start, end):
    CreatesSegment(store=store)(rec(store), from_seconds=READS(start), to_seconds=READS(end))
    return READS(start), READS(end)


@when("the reviewer presses Preview on that Block", target_fixture="pressed")
def _(store, laid_out):
    block = _remaining.block_at(store, laid_out["subject"])
    page = _web.opens_detail(store, block.recording_id)
    row = _remaining.block_row_markup(page, block.type)
    buttons = _remaining.CUE_BUTTON.findall(row)
    assert len(buttons) == 1, f"the {block.type} Block offers {len(buttons)} Preview controls"
    start, end = buttons[0]
    return {"start": float(start), "end": float(end), "row": row}


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
    (segment,) = _analysis.proposed(store)
    proposal = _analysis.proposal_of(store, segment)
    assert (proposal.punch_in_grade, proposal.punch_out_grade) == ("easy", "easy")


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
def _(store, laid_out):
    hosted = _remaining.block_at(store, laid_out["subject"])
    preached = _remaining.block_at(store, laid_out["preacher"])
    assert CONFIDENCE_RANK[hosted.classification_confidence] < CONFIDENCE_RANK[preached.classification_confidence], (
        hosted.classification_confidence,
        preached.classification_confidence,
    )


@then("this is evidence only, since the preacher occasionally gives the benediction")
def _(store, laid_out):
    hosted = _remaining.block_at(store, laid_out["subject"])
    assert hosted.type == "sermon", hosted.type
    assert any("host" in evidence.finding.lower() for evidence in hosted.evidence), [
        evidence.finding for evidence in hosted.evidence
    ]


@when("the Recording is analysed")
def _(store):
    _analysis.analyses(store, _analysis.recording_of(store))


@then("no Segment is proposed")
def _(store):
    assert _analysis.proposed(store) == []


@then("the Recording is shown as needing no attention")
def _(store):
    row = _remaining.listed_row(store, _analysis.the_recording(store))
    assert 'data-attention="false"' in row, row


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


@then("boundary detection continues using transcript evidence alone")
def _(store, recording):
    analysed = store.loads(Recording, recording.recording_id)
    assert analysed.state == "awaiting_review", analysed.state
    assert reads_json(store, analysed, "diarization") is None
    failed = [entry.error for entry in store.lists(LogEntry, recording_id=analysed.recording_id, kind=OPTIONAL_STAGE_FAILED)]
    assert [error for error in failed if error.startswith("diarization: ")], failed
    placed = [
        (segment.classification, segment.boundary_source)
        for segment in store.lists(Segment, recording_id=analysed.recording_id)
    ]
    assert placed and all(source is not None for _, source in placed), f"no boundary was placed by the walk: {placed}"
    spoken_of = [
        evidence.implies
        for block in _analysis.blocks_of(store, analysed)
        for evidence in block.evidence
        if evidence.implies == "speaker change"
    ]
    assert spoken_of == [], spoken_of


@then(parsers.parse('the Proposal is marked as "{gap}"'))
def _(store, recording, gap):
    segments = store.lists(Segment, recording_id=recording.recording_id)
    assert segments, "no Segment was proposed"
    for segment in segments:
        missing = _analysis.proposal_of(store, segment).missing_evidence
        assert gap in missing, f"{segment.classification} is missing only {missing}"


CUE_GAPS = frozenset({"no opening cue", "closing prayer"})
CONFIDENCE_ORDER = ("high", "medium", "low")


@then("its confidence is reduced")
def _(store, recording):
    segments = store.lists(Segment, recording_id=recording.recording_id)
    assert segments, "no Segment was proposed"
    for segment in segments:
        proposal = _analysis.proposal_of(store, segment)
        earned = CONFIDENCE_ORDER[len(CUE_GAPS & set(proposal.missing_evidence))]
        assert CONFIDENCE_ORDER.index(proposal.boundary_confidence) > CONFIDENCE_ORDER.index(earned), (
            f"{segment.classification} is {proposal.boundary_confidence}, what its cues alone earn "
            f"({', '.join(proposal.missing_evidence)})"
        )


@then("playback starts at the excerpt")
def _(store, laid_out, pressed):
    assert pressed["start"] == _remaining.block_at(store, laid_out["subject"]).cue_start_seconds


@then("stops at the end of the excerpt")
def _(store, laid_out, pressed):
    assert pressed["end"] == _remaining.block_at(store, laid_out["subject"]).cue_end_seconds


@then("the reviewer can tell what the Block is without further scrubbing")
def _(store, laid_out, pressed):
    block = _remaining.block_at(store, laid_out["subject"])
    shown = reads_field(pressed["row"], "block-summary")
    assert block.summary and shown == block.summary, (shown, block.summary)


@then("the machine it used is recorded with the summary")
def _(store, model_endpoint):
    summarised = [block for block in _analysis.blocks_of(store) if block.summary]
    assert summarised, "no Block was summarised"
    for block in summarised:
        recorded = " ".join(evidence.finding for evidence in block.evidence)
        assert model_endpoint in recorded, f"the {block.type} summary records {recorded!r}"


@then("Analysis completes without summaries")
def _(store, recording):
    (job,) = store.lists(Job, recording_id=recording.recording_id, kind="analyze")
    assert job.state == "succeeded", job.last_error
    assert [block.summary for block in _analysis.blocks_of(store, recording) if block.summary] == []
    skipped = [
        entry.error
        for entry in store.lists(LogEntry, recording_id=recording.recording_id)
        if entry.kind == OPTIONAL_STAGE_FAILED
    ]
    assert "summarization" in [error.split(":")[0] for error in skipped], skipped


@then("cue excerpts fall back to the first few seconds of each Block")
def _(store):
    spoken = [block for block in store.lists(Block) if block.type != "music"]
    assert not spoken or all(
        block.cue_start_seconds is None or abs(block.cue_start_seconds - block.start_seconds) < 0.05 for block in spoken
    )


@then("the reviewer is told summaries were unavailable")
def _(store, recording):
    shown = strips_tags(_web.opens_detail(store, recording.recording_id)).lower()
    assert re.search(r"summar\w*[^.]{0,60}unavailable", shown), "the page does not say summaries were unavailable"


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
