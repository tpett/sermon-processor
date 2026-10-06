from __future__ import annotations

import base64
import re
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from sermon.analysis.io import reads_json
from sermon.analysis.stages import LABEL_LIMIT, LABELLED_BY_PASSAGE
from sermon.config import ModelEndpointUnreachable
from sermon.glossary import ReadsGlossary
from sermon.pipeline import classify, scripture
from sermon.store import Block, Recording, RecordingTitle, Segment, Store
from sermon.store.vocabularies import RECORDING_KINDS

TITLER = "qwen3.6:35b-mlx"
TITLE_TEMPLATE = Path(__file__).with_name("prompts") / "titles.v1.md"
TITLE_LIMIT = 120
SUMMARY_SHOWN = 160
NAMED_BY_CLASS = frozenset({"lesson", "seminar"})
NAMED_BY_TITLE = frozenset({"meeting"})
UNKNOWN_KIND = "unknown"
EMPTY_KIND = "empty"
MEETING_KIND = "meeting"
SILENCE_TITLE = "Silence or noise"
CLASS_ALONE = "the class held in it"
MEETING_NAME = "Members Meeting"
DISTINCT_UTTERANCES_OF_SPEECH = 20
SOUNDING_DBFS = -30.0
SOUNDING_SECONDS_OF_CONTENT = 30.0
POSSESSIVE_NAME = re.compile(r"\b[A-Z][a-z]+['’]s\b")
MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
    "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
DATES = (
    re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"),
    re.compile(rf"\b(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b", re.IGNORECASE),
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{MONTHS})\b(?:,?\s+\d{{4}})?", re.IGNORECASE),
    re.compile(rf"\b(?:{MONTHS})\.?\s+\d{{4}}\b", re.IGNORECASE),
    re.compile(r"\b(?:19|20)\d{2}\b"),
)
SEPARATORS = " -–—,:;/|"
PASSAGE_GIVEN = "For a service, end the title with its passage, {}. Name no other passage."
NO_PASSAGE = (
    "No passage was found, so the title names no passage at all; an ordinary service"
    " is then just \"Sunday Service\"."
)
PLACEHOLDER = re.compile(r"<[^>]*>")
DOTTED_VERSE = re.compile(r"(\d)\.(\d)")
COLON_VERSE = re.compile(r"(\d):(\d)")


class TitleNotInferred(RuntimeError):
    pass


@dataclass(frozen=True)
class Titling:
    kind: str
    title: str | None
    series: str | None = None
    topic: str | None = None


def clock(seconds):
    total = int(seconds or 0)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def spoken_passage(label):
    return DOTTED_VERSE.sub(r"\1:\2", label) if label else None


def written_passage(label):
    return COLON_VERSE.sub(r"\1.\2", label)


def keeps_passages_shown(title, shown):
    """Drops any part of the title naming a passage the model was not shown."""
    known = {(one.book, one.chapter) for one in scripture.references_in(shown)}
    books = {book for book, _ in known}

    def supported(reference):
        if reference.chapter is None:
            return reference.book in books
        return (reference.book, reference.chapter) in known

    kept = [
        part
        for part in title.split(" - ")
        if all(supported(one) for one in scripture.references_in(part))
    ]
    return " - ".join(kept)


def shortened(title):
    """A title cut at a separator rather than inside a word or a verse."""
    if len(title) <= TITLE_LIMIT:
        return title.strip(SEPARATORS)
    cut = next((at for at in (title.rfind(mark, 0, TITLE_LIMIT) for mark in (", ", " - ")) if at > 0), -1)
    return (title[:cut] if cut > 0 else title[:TITLE_LIMIT]).strip(SEPARATORS)


def sounding_seconds(peaks):
    """How long the measured waveform rises above SOUNDING_DBFS; None when it was never measured."""
    detail = ((peaks or {}).get("resolutions") or {}).get("detail")
    if not (peaks or {}).get("measured") or not detail:
        return None
    level = peaks.get("full_scale", 127) * 10 ** (SOUNDING_DBFS / 20)
    lows, highs = (np.frombuffer(base64.b64decode(detail[edge]), dtype=np.int8).astype(np.int16) for edge in ("min", "max"))
    return float((np.maximum(-lows, highs) >= level).sum() * detail["seconds_per_bin"])


def hears_nothing(blocks, doc, peaks=None):
    """Near-silent audio, or no music and almost nothing said: what a stray trigger or a mic check leaves."""
    sounding = sounding_seconds(peaks)
    if sounding is not None and sounding < SOUNDING_SECONDS_OF_CONTENT:
        return True
    if doc is None or any(block.type == "music" for block in blocks):
        return False
    said = {" ".join(one.get("text", "").lower().split()) for one in doc.get("utterances", ())}
    return len(said - {""}) < DISTINCT_UTTERANCES_OF_SPEECH


def without_names(text):
    return " ".join(POSSESSIVE_NAME.sub(" ", text).split()).strip(SEPARATORS)


def capitalised(text):
    return text[:1].upper() + text[1:] if text else None


def named_meeting(topic):
    return f"{MEETING_NAME} - {topic}" if topic else MEETING_NAME


def without_dates(text):
    text = PLACEHOLDER.sub(" ", text)
    for pattern in DATES:
        text = pattern.sub(" ", text)
    text = re.sub(r"\(\s*\)", " ", text)
    text = re.sub(r"\s+([-–—])(?:\s*[-–—])+\s+", r" \1 ", text)
    return " ".join(text.split()).strip(SEPARATORS)


@dataclass(frozen=True)
class DescribesRecording:
    """The text the model is shown: never audio, never the date."""

    glossary: object

    def evidence(self, blocks, segments):
        return f"{self._blocks(blocks)}\n{self._segments(segments)}"

    def __call__(self, recording, blocks, segments, template=None):
        template = TITLE_TEMPLATE.read_text() if template is None else template
        passages = [spoken_passage(one.label) for one in segments if one.classification in LABELLED_BY_PASSAGE and one.label]
        return (
            template.replace("{blocks}", self._blocks(blocks))
            .replace("{segments}", self._segments(segments))
            .replace("{weekday}", recording.started_at.strftime("%A"))
            .replace("{start_time}", recording.started_at.strftime("%H:%M"))
            .replace("{duration}", clock(recording.duration_seconds))
            .replace("{glossary}", self._names())
            .replace("{passage}", PASSAGE_GIVEN.format(passages[0]) if passages else NO_PASSAGE)
        )

    def _blocks(self, blocks):
        lines = []
        for block in blocks:
            line = f"{clock(block.start_seconds)}–{clock(block.end_seconds)}  {block.type}"
            if block.summary:
                line += f": {' '.join(block.summary.split())[:SUMMARY_SHOWN]}"
            lines.append(line)
        return "\n".join(lines) or "(nothing was found in it)"

    def _segments(self, segments):
        lines = []
        for segment in segments:
            line = f"{segment.classification} {clock(segment.punch_in_seconds)}–{clock(segment.punch_out_seconds)}"
            if segment.label:
                line += f", passage or label {spoken_passage(segment.label)}"
            lines.append(line)
        return "\n".join(lines) or "(none)"

    def _names(self):
        return "\n".join(f"{acronym} = {name}" for acronym, name in self.glossary.names.items()) or "(none)"


@dataclass(frozen=True)
class AsksModelForTitle:
    model: str = TITLER

    def __call__(self, prompt):
        try:
            answered, _ = classify.call_json(self.model, prompt)
        except ModelEndpointUnreachable as unreachable:
            raise TitleNotInferred(str(unreachable)) from unreachable
        return answered


def _text(answer, key):
    value = answer.get(key)
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip(SEPARATORS + "\"'")
    return cleaned if cleaned and cleaned.lower() not in {"null", "none"} else None


@dataclass(frozen=True)
class InfersTitle:
    """What the recording is, from what analysis already stored. Writes nothing."""

    store: Store
    asks: object = None
    glossary: object = None

    def __call__(self, recording):
        glossary = self.glossary or ReadsGlossary()()
        blocks = sorted(self.store.lists(Block, recording_id=recording.recording_id), key=lambda one: one.start_seconds)
        segments = sorted(self.store.lists(Segment, recording_id=recording.recording_id), key=lambda one: one.punch_in_seconds)
        heard = reads_json(self.store, recording, "transcript")
        if hears_nothing(blocks, heard, reads_json(self.store, recording, "waveform_peaks")):
            return Titling(kind=EMPTY_KIND, title=SILENCE_TITLE)
        describes = DescribesRecording(glossary)
        answer = (self.asks or AsksModelForTitle())(describes(recording, blocks, segments))
        if not isinstance(answer, dict) or not ({"kind", "title"} & set(answer)):
            raise TitleNotInferred("the model named neither a kind nor a title")
        kind = (_text(answer, "kind") or "").lower()
        kind = kind if kind in RECORDING_KINDS else UNKNOWN_KIND
        shown = describes.evidence(blocks, segments)
        topic = _text(answer, "topic")
        topic = capitalised(topic and without_names(keeps_passages_shown(topic, shown)))
        if kind == EMPTY_KIND:
            return Titling(kind=kind, title=SILENCE_TITLE)
        if kind == MEETING_KIND:
            return Titling(kind=kind, title=named_meeting(topic), topic=topic)
        return Titling(
            kind=kind,
            title=self._titled(_text(answer, "title"), glossary, segments, shown),
            series=_text(answer, "series") and glossary.spells_out(_text(answer, "series")),
            topic=topic,
        )

    def _titled(self, title, glossary, segments, shown):
        if title is None:
            return None
        title = glossary.spells_out(without_names(without_dates(title)))
        for segment in segments:
            if segment.classification in LABELLED_BY_PASSAGE and segment.label:
                title = title.replace(segment.label, spoken_passage(segment.label))
        return shortened(keeps_passages_shown(title, shown)) or None


@dataclass(frozen=True)
class SuggestsNamedLabel:
    """A label for a class or meeting, from its name and topic; never over one already there."""

    store: Store
    glossary: object

    def __call__(self, recording, titling):
        suggested = []
        for segment in self.store.lists(Segment, recording_id=recording.recording_id):
            if segment.label or segment.classification in LABELLED_BY_PASSAGE:
                continue
            label = self.suggests(segment, titling)
            if label:
                suggested.append(self.store.saves(replace(segment, label=label)))
        return tuple(suggested)

    def suggests(self, segment, titling):
        if segment.classification not in NAMED_BY_CLASS | NAMED_BY_TITLE:
            return None
        if titling.kind == MEETING_KIND or segment.classification in NAMED_BY_TITLE:
            named = named_meeting(titling.topic)
        else:
            named = self._class_label(titling)
        if named is None:
            return None
        return written_passage(named)[:LABEL_LIMIT].strip(SEPARATORS) or None

    def _class_label(self, titling):
        series = self.glossary.abbreviates(titling.series) if titling.series else None
        named = [part for part in (series, titling.topic) if part]
        return " - ".join(named) or None


@dataclass(frozen=True)
class TitlesRecording:
    """The analyze walk's last stage: the Recording's kind, its title, and the labels they imply."""

    store: Store
    asks: object = None
    glossary: object = None

    def __call__(self, recording):
        glossary = self.glossary or ReadsGlossary()()
        titling = InfersTitle(store=self.store, asks=self.asks, glossary=glossary)(recording)
        current = self.store.loads(Recording, recording.recording_id)
        if titling.kind != UNKNOWN_KIND or current.kind is None:
            self.store.saves(replace(current, kind=titling.kind))
        held = self.store.loads(RecordingTitle, recording.recording_id)
        if titling.title and not (held and held.edited_by_human):
            held = self.store.saves(
                RecordingTitle(recording_id=recording.recording_id, title=titling.title, series=titling.series)
            )
        SuggestsNamedLabel(store=self.store, glossary=glossary)(recording, titling)
        return titling
