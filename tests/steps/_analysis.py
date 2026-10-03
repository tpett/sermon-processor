"""The analysis stages as the analyze job runs them, with every model seam held by a double.

Nothing here reasons, summarises or transcribes. A scenario lays out its Blocks,
the transcript is written to cover them, and the shipped stages run over both.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sermon.analysis import (
    ClassifiesBlocks,
    DividesIntoBlocks,
    ProposesSegments,
    RefinesPunchIn,
    RefinesPunchOut,
    ScoresProposals,
    SummarizesBlocks,
)
from sermon.analysis.io import reads_json, writes_json
from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.analyzes_recording import RunsAnalyzeJob
from sermon.sends_notification import SendsNotification
from sermon.store import Block, Job, Proposal, Recording, Segment

READS = ReadsTimecode()
RECORDING_ID = "recording_20260823_103015"
DURATION_S = 5412.0
UTTERANCE_S = 8.0
UTTERANCE_PERIOD_S = 12.0
WORD_S = 0.3
SPOKEN = {
    "announcements": "good morning and welcome there is coffee after the service",
    "prayer": "let us pray father we thank you for this day in jesus name amen",
    "music": "",
    "scripture_reading": "please stand for the reading of gods word from romans chapter eight",
    "sermon": "this morning we will look at what the apostle means by grace and what it asks of us",
    "lesson": "in this class we are working through the doctrine of the church",
    "seminar": "welcome to the second session of the seminar on church history",
    "communion": "come to the table all who trust in christ this is my body given for you",
    "qa": "does anyone have a question yes go ahead that is a good question",
    "rehearsal": "one two three four from the top again",
    "other": "we will get going in just a minute",
}
SUNDAY = (
    ("0:00:00", "0:04:00", "announcements"),
    ("0:04:00", "0:04:30", "prayer"),
    ("0:04:30", "0:24:00", "music"),
    ("0:24:00", "0:26:10", "prayer"),
    ("0:26:10", "0:31:40", "scripture_reading"),
    ("0:31:40", "1:12:40", "sermon"),
    ("1:12:40", "1:14:52", "prayer"),
    ("1:14:52", "1:20:00", "communion"),
    ("1:20:00", "1:26:00", "music"),
    ("1:26:00", "1:30:12", "prayer"),
)


class ModelCallRefused(RuntimeError):
    pass


def refuses_a_model_call(*_, **__):
    raise ModelCallRefused("the specification never calls a model; inject a double at the stage's seam")


def answers_a_summary_prompt(model, prompt, think=False):
    return {"summary": "a block of the service", "cue_quote": ""}, 0


def recording_of(store, duration=DURATION_S):
    recordings = store.lists(Recording)
    if recordings:
        return recordings[0]
    return store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=f"recordings/{RECORDING_ID}.flac",
            state="downloaded",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=duration,
        )
    )


def the_recording(store):
    recordings = store.lists(Recording)
    assert len(recordings) == 1, f"{len(recordings)} Recordings are stored"
    return recordings[0]


def words_over(start, end, text):
    words = []
    at = start
    for word in text.split():
        if at + WORD_S - 0.05 > end:
            break
        words.append({"w": word, "word": word, "start": round(at, 3), "end": round(at + WORD_S - 0.05, 3)})
        at += WORD_S
    return words


def utterances_over(start, end, text):
    spoken = []
    at = start
    while text and at < end - 0.5:
        stops = min(at + UTTERANCE_S, end - 0.5)
        words = words_over(at, stops, text)
        if words:
            stops = words[-1]["end"]
        spoken.append(
            {
                "start": round(at, 3),
                "end": round(stops, 3),
                "text": " ".join(word["w"] for word in words) or text,
                "confidence": 0.92,
                "speaker": "Speaker 1",
                "words": words,
            }
        )
        at += UTTERANCE_PERIOD_S
    return spoken


def transcript_over(recording, spans, duration=None):
    """A transcript whose speech starts exactly at every span's start, in the span's own words."""
    length = duration or recording.duration_seconds or DURATION_S
    utterances = []
    for start, end, kind, *spoken in spans:
        text = spoken[0] if spoken else SPOKEN.get(kind, SPOKEN["other"])
        utterances += utterances_over(float(start), float(end), text)
    utterances.sort(key=lambda item: item["start"])
    silences = [
        {"start": before["end"], "end": after["start"]}
        for before, after in zip(utterances, utterances[1:])
        if after["start"] - before["end"] >= 1.0
    ]
    return {
        "recording_id": recording.recording_id,
        "started_at": recording.started_at.isoformat(),
        "duration": length,
        "language": "en",
        "utterances": utterances,
        "silences": silences,
        "likely_music": [
            {"start": float(start), "end": float(end)} for start, end, kind, *_ in spans if kind == "music"
        ],
    }


def reads_rows(rows):
    return [(READS(start), READS(end), kind) for start, end, kind in rows]


def lays_out(store, recording, spans, *, typed=True):
    """The Recording holds exactly these Blocks and a transcript that covers them."""
    for segment in store.lists(Segment, recording_id=recording.recording_id):
        for proposal in store.lists(Proposal, segment_id=segment.segment_id):
            store.forgets(proposal)
        store.forgets(segment)
    for block in store.lists(Block, recording_id=recording.recording_id):
        store.forgets(block)
    writes_json(store, recording, "transcript", transcript_over(recording, spans))
    if not typed:
        return []
    return [
        store.saves(
            Block(recording_id=recording.recording_id, start_seconds=float(start), end_seconds=float(end), type=kind)
        )
        for start, end, kind, *_ in spans
    ]


def transcript_of(store, recording):
    return reads_json(store, recording, "transcript")


def divides_as(spans):
    """The reasoning stage's answer, given rather than asked for."""

    def divides(doc):
        return [
            {"start": float(start), "end": float(end), "type": kind, "confidence": 0.9, "evidence": "speaker change"}
            for start, end, kind, *_ in spans
        ]

    return divides


def divides(store, recording, spans):
    return DividesIntoBlocks(store=store, divides=divides_as(spans))(recording)


def classifies(store, recording):
    return ClassifiesBlocks(store=store)(recording)


def summarizes_as(answers):
    def summarizes(block, doc):
        answered = answers.get(block.type)
        if answered is None:
            return None
        return answered, (block.start_seconds, min(block.start_seconds + 8.0, block.end_seconds))

    return summarizes


def summarizes(store, recording, answers):
    return SummarizesBlocks(store=store, summarizes=summarizes_as(answers))(recording)


def proposes(store, recording):
    """The analyze job's segment_proposal, boundary_refinement and scoring stages, as it calls them."""
    ProposesSegments(store=store)(recording)
    RefinesPunchIn(store=store)(recording)
    RefinesPunchOut(store=store)(recording)
    ScoresProposals(store=store)(recording)
    return sorted(
        store.lists(Segment, recording_id=recording.recording_id), key=lambda item: item.punch_in_seconds
    )


def analyses(store, recording, sent=None):
    """The analyze job as the worker builds it when no corpus is named: the stage walk."""
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}:{len(store.lists(Job))}",
            queued_at=datetime(2026, 8, 23, 16, 0, tzinfo=UTC),
        )
    )
    RunsAnalyzeJob(
        store=store,
        stages=lambda _name: None,
        notifies=SendsNotification(store=store, sends=(sent if sent is not None else []).append),
        recording_id=recording.recording_id,
    )()
    ran = store.lists(Job, recording_id=recording.recording_id, kind="analyze")[-1]
    assert ran.state == "succeeded", f"the analyze job {ran.state}: {ran.last_error}"
    return proposed(store, recording)


def proposed(store, recording=None):
    criteria = {} if recording is None else {"recording_id": recording.recording_id}
    return sorted(store.lists(Segment, **criteria), key=lambda item: item.span_start_seconds)


def blocks_of(store, recording=None):
    criteria = {} if recording is None else {"recording_id": recording.recording_id}
    return sorted(store.lists(Block, **criteria), key=lambda item: item.start_seconds)


def proposal_of(store, segment):
    found = store.lists(Proposal, segment_id=segment.segment_id)
    assert found, f"Segment {segment.segment_id} carries no Proposal"
    return found[0]
