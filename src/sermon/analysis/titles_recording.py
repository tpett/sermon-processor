from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from sermon.analysis.stages import LABEL_LIMIT, LABELLED_BY_PASSAGE
from sermon.config import ModelEndpointUnreachable
from sermon.glossary import ReadsGlossary
from sermon.pipeline import classify
from sermon.store import Block, Recording, RecordingTitle, Segment, Store
from sermon.store.vocabularies import RECORDING_KINDS

TITLER = "qwen3.6:35b-mlx"
TITLE_TEMPLATE = Path(__file__).with_name("prompts") / "titles.v1.md"
TITLE_LIMIT = 80
SUMMARY_SHOWN = 160
NAMED_BY_CLASS = frozenset({"lesson", "seminar"})
NAMED_BY_TITLE = frozenset({"meeting"})
UNKNOWN_KIND = "unknown"
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


def without_dates(text):
    for pattern in DATES:
        text = pattern.sub(" ", text)
    text = re.sub(r"\(\s*\)", " ", text)
    text = re.sub(r"\s+([-–—])(?:\s*[-–—])+\s+", r" \1 ", text)
    return " ".join(text.split()).strip(SEPARATORS)


@dataclass(frozen=True)
class DescribesRecording:
    """The text the model is shown: never audio, never the date."""

    glossary: object

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
            .replace("{passage}", passages[0] if passages else "(no passage was found)")
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
        prompt = DescribesRecording(glossary)(recording, blocks, segments)
        answer = (self.asks or AsksModelForTitle())(prompt)
        if not isinstance(answer, dict) or not ({"kind", "title"} & set(answer)):
            raise TitleNotInferred("the model named neither a kind nor a title")
        kind = (_text(answer, "kind") or "").lower()
        return Titling(
            kind=kind if kind in RECORDING_KINDS else UNKNOWN_KIND,
            title=self._titled(_text(answer, "title"), glossary, segments),
            series=_text(answer, "series") and glossary.spells_out(_text(answer, "series")),
            topic=_text(answer, "topic"),
        )

    def _titled(self, title, glossary, segments):
        if title is None:
            return None
        title = glossary.spells_out(without_dates(title))
        for segment in segments:
            if segment.classification in LABELLED_BY_PASSAGE and segment.label:
                title = title.replace(segment.label, spoken_passage(segment.label))
        return title[:TITLE_LIMIT].strip(SEPARATORS) or None


@dataclass(frozen=True)
class SuggestsNamedLabel:
    """A label for a class or meeting, from its name and topic; never over one already there."""

    store: Store
    glossary: object

    def __call__(self, recording, titling, title):
        suggested = []
        for segment in self.store.lists(Segment, recording_id=recording.recording_id):
            if segment.label or segment.classification in LABELLED_BY_PASSAGE:
                continue
            label = self.suggests(segment, titling, title)
            if label:
                suggested.append(self.store.saves(replace(segment, label=label)))
        return tuple(suggested)

    def suggests(self, segment, titling, title):
        named = self._class_label(titling)
        if named is None and segment.classification in NAMED_BY_TITLE and title:
            named = self.glossary.abbreviates(title)
        if named is None or segment.classification not in NAMED_BY_CLASS | NAMED_BY_TITLE:
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
        SuggestsNamedLabel(store=self.store, glossary=glossary)(
            recording, titling, held.title if held else None
        )
        return titling
