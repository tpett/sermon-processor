from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from sermon.analysis.io import writes_json
from sermon.analysis.records_edges_inside_speech import RecordsEdgesInsideSpeech
from sermon.analysis.stages import (
    ClassifiesBlocks,
    DividesIntoBlocks,
    ProposesSegments,
    RefinesPunchIn,
    RefinesPunchOut,
    ScoresProposals,
    SummarizesBlocks,
    TranscribesRecording,
)
from sermon.pipeline import classify, segments
from sermon.pipeline.roots import requires_root
from sermon.store import Store

ASR_CONFIG = "whisper-large-v3-turbo+words"
CLASSIFIER = "qwen3.6:35b-mlx"
SUMMARIZER = "qwen3:4b"
SUMMARY_TEMPLATE = "summarize.v1.md"
SUMMARY_MIN_WORDS = 40
SUMMARY_MAX_CHARS = 14000
SUMMARY_LIMIT = 110
QUOTE_MIN_WORDS = 3
QUOTE_MIN_SCORE = 0.55
CUE_FALLBACK_S = 8.0


class TranscriptNotStored(FileNotFoundError):
    pass


@dataclass(frozen=True)
class BindsCorpusRoots:
    corpus_root: Path
    prompts_root: Path

    def __call__(self):
        segments.DATA_ROOT = Path(self.corpus_root)
        classify.DATA = Path(self.corpus_root)
        classify.PROMPTS = Path(self.prompts_root)


@dataclass(frozen=True)
class ReadsStoredTranscript:
    corpus_root: Path
    asr_config: str = ASR_CONFIG

    def __call__(self, recording_id):
        stored = Path(self.corpus_root) / "transcripts" / f"{recording_id}.{self.asr_config}.json"
        if not stored.is_file():
            raise TranscriptNotStored(
                f"no {self.asr_config} transcript for {recording_id} under {self.corpus_root}"
            )
        return json.loads(stored.read_text())


@dataclass(frozen=True)
class ReasonsOverTranscript:
    model: str = CLASSIFIER

    def __call__(self, doc):
        return classify.run_whole(self.model, doc)


@dataclass(frozen=True)
class DividesByReasoning:
    reasons: object = None

    def __call__(self, doc):
        return (self.reasons or ReasonsOverTranscript())(doc)["blocks"]


@dataclass(frozen=True)
class DerivesSpans:
    def __call__(self, blocks, doc):
        return segments.derive(blocks, doc, refine=False, tail=0.0)


@dataclass(frozen=True)
class ChoosesBoundaries:
    model_segments: object = ()

    def __call__(self, blocks, doc):
        return segments.choose(
            list(self.model_segments), segments.derive(blocks, doc), doc
        )


@dataclass(frozen=True)
class SummarizesOneBlock:
    model: str = SUMMARIZER

    def __call__(self, block, doc):
        spoken = [
            utterance
            for utterance in doc["utterances"]
            if block.start_seconds <= utterance["start"] < block.end_seconds
        ]
        text = " ".join(utterance["text"] for utterance in spoken).strip()
        if len(text.split()) < SUMMARY_MIN_WORDS:
            return None
        answered, _ = classify.call_json(self.model, self._prompt(block, text))
        if not answered:
            return None
        located = locates_quote(str(answered.get("cue_quote", "")), words_of(spoken))
        return (
            str(answered.get("summary", ""))[:SUMMARY_LIMIT],
            located or (block.start_seconds, min(block.start_seconds + CUE_FALLBACK_S, block.end_seconds)),
        )

    def _prompt(self, block, text):
        template = (
            requires_root(classify.__name__, "PROMPTS", classify.PROMPTS) / SUMMARY_TEMPLATE
        ).read_text()
        return (
            template.replace("{block_start}", classify.hms(block.start_seconds))
            .replace("{block_end}", classify.hms(block.end_seconds))
            .replace("{block_minutes}", f"{(block.end_seconds - block.start_seconds) / 60:.0f}")
            .replace("{block_text}", text[:SUMMARY_MAX_CHARS])
        )


def words_of(utterances):
    spoken = []
    for utterance in utterances:
        spoken.extend(utterance.get("words", ()))
    return spoken


def locates_quote(quote, words):
    wanted = re.sub(r"[^a-z0-9 ]", " ", quote.lower()).split()
    if len(wanted) < QUOTE_MIN_WORDS or not words:
        return None
    spoken = [word["w"].lower().strip(".,!?;:\"'") for word in words]
    best, score = None, 0.0
    for start in range(max(1, len(spoken) - len(wanted) + 1)):
        matched = difflib.SequenceMatcher(None, wanted, spoken[start:start + len(wanted)]).ratio()
        if matched > score:
            best, score = start, matched
    if best is None or score < QUOTE_MIN_SCORE:
        return None
    return words[best]["start"], words[min(len(words) - 1, best + len(wanted) - 1)]["end"]


@dataclass(frozen=True)
class ProposesFromStoredTranscript:
    store: Store
    corpus_root: Path
    prompts_root: Path
    model: str = CLASSIFIER
    summarizer: str | None = SUMMARIZER
    asr_config: str = ASR_CONFIG
    reasons: object = None

    def __call__(self, recording):
        BindsCorpusRoots(corpus_root=self.corpus_root, prompts_root=self.prompts_root)()
        doc = ReadsStoredTranscript(self.corpus_root, self.asr_config)(recording.recording_id)
        writes_json(self.store, recording, "transcript", doc)
        recording = TranscribesRecording(store=self.store)(recording)
        answer = (self.reasons or ReasonsOverTranscript(self.model))(doc)
        RecordsEdgesInsideSpeech(store=self.store)(recording, answer["blocks"], doc)
        DividesIntoBlocks(store=self.store, divides=lambda _: answer["blocks"])(recording)
        ClassifiesBlocks(store=self.store)(recording)
        if self.summarizer:
            SummarizesBlocks(
                store=self.store, summarizes=SummarizesOneBlock(self.summarizer)
            )(recording)
        ProposesSegments(store=self.store)(recording)
        chooses = ChoosesBoundaries(model_segments=answer.get("model_segments") or ())
        RefinesPunchIn(store=self.store, chooses=chooses)(recording)
        RefinesPunchOut(store=self.store, chooses=chooses)(recording)
        ScoresProposals(store=self.store)(recording)
        return answer
