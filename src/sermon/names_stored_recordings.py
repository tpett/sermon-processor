from __future__ import annotations

from dataclasses import dataclass

from sermon.analysis.titles_recording import (
    InfersTitle,
    SuggestsNamedLabel,
    TitleNotInferred,
    TitlesRecording,
)
from sermon.glossary import ReadsGlossary
from sermon.store import Block, Recording, RecordingTitle, Segment, Store

NOT_NAMED_STATES = frozenset({"discarded", "ignored"})


@dataclass(frozen=True)
class NamesStoredRecordings:
    """Names recordings analysed before titling existed, from their stored Blocks and Segments alone."""

    store: Store
    prints: object = print
    asks: object = None
    glossary: object = None
    dry_run: bool = False
    again: bool = False
    only: tuple = ()

    def __call__(self):
        glossary = self.glossary or ReadsGlossary()()
        named = 0
        for recording in self.store.lists(Recording):
            if not self._wanted(recording):
                continue
            if self._names(recording, glossary):
                named += 1
        self.prints(f"{'would name' if self.dry_run else 'named'} {named} recording{'' if named == 1 else 's'}")
        return named

    def _wanted(self, recording):
        if self.only and recording.recording_id not in self.only:
            return False
        if recording.state in NOT_NAMED_STATES:
            return False
        if not self.store.lists(Block, recording_id=recording.recording_id):
            return False
        held = self.store.loads(RecordingTitle, recording.recording_id)
        return self.again or self.only or held is None or held.edited_by_human

    def _names(self, recording, glossary):
        held = self.store.loads(RecordingTitle, recording.recording_id)
        unlabelled = {
            one.segment_id
            for one in self.store.lists(Segment, recording_id=recording.recording_id)
            if not one.label
        }
        infers = InfersTitle if self.dry_run else TitlesRecording
        try:
            titling = infers(store=self.store, asks=self.asks, glossary=glossary)(recording)
        except TitleNotInferred as failed:
            self.prints(f"{recording.recording_id}  not named: {failed}")
            return False
        kept = held is not None and held.edited_by_human
        title = held.title if kept else titling.title
        self.prints(f"{recording.recording_id}  {titling.kind}  {title or '(no title)'}")
        if kept:
            self.prints(f"{recording.recording_id}  kept the reviewer's title")
        for segment, label in self._labels(recording, titling, title, unlabelled, glossary):
            self.prints(f"{recording.recording_id}    {segment.classification}: {label}")
        return True

    def _labels(self, recording, titling, title, unlabelled, glossary):
        suggests = SuggestsNamedLabel(store=self.store, glossary=glossary)
        for segment in self.store.lists(Segment, recording_id=recording.recording_id):
            if segment.segment_id not in unlabelled:
                continue
            label = suggests.suggests(segment, titling, title) if self.dry_run else segment.label
            if label:
                yield segment, label
