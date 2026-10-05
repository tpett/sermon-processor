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
KEPT = "kept: titled by a reviewer"


def when_of(recording):
    return recording.started_at.strftime("%Y-%m-%d %H:%M")


@dataclass(frozen=True)
class NamesStoredRecordings:
    """Names recordings analysed before titling existed, from their stored Blocks and Segments alone.

    One line per recording: when it started, the kind, the title, any label it suggests.
    """

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
            if not self._analysed(recording):
                continue
            held = self.store.loads(RecordingTitle, recording.recording_id)
            if held is not None and held.edited_by_human:
                self.prints(f"{when_of(recording)}  {recording.kind or '-'}  {held.title}  ({KEPT})  [{recording.recording_id}]")
                continue
            if held is not None and not (self.again or self.only):
                continue
            if self._names(recording, glossary):
                named += 1
        self.prints(f"{'would name' if self.dry_run else 'named'} {named} recording{'' if named == 1 else 's'}")
        return named

    def _analysed(self, recording):
        if self.only and recording.recording_id not in self.only:
            return False
        if recording.state in NOT_NAMED_STATES:
            return False
        return bool(self.store.lists(Block, recording_id=recording.recording_id))

    def _names(self, recording, glossary):
        unlabelled = {
            one.segment_id
            for one in self.store.lists(Segment, recording_id=recording.recording_id)
            if not one.label
        }
        infers = InfersTitle if self.dry_run else TitlesRecording
        try:
            titling = infers(store=self.store, asks=self.asks, glossary=glossary)(recording)
        except TitleNotInferred as failed:
            self.prints(f"{when_of(recording)}  not named: {failed}  [{recording.recording_id}]")
            return False
        labels = "; ".join(
            f"{label} ({segment.classification})"
            for segment, label in self._labels(recording, titling, unlabelled, glossary)
        )
        self.prints(
            f"{when_of(recording)}  {titling.kind}  {titling.title or '(no title)'}"
            f"{f'  label: {labels}' if labels else ''}  [{recording.recording_id}]"
        )
        return True

    def _labels(self, recording, titling, unlabelled, glossary):
        suggests = SuggestsNamedLabel(store=self.store, glossary=glossary)
        for segment in self.store.lists(Segment, recording_id=recording.recording_id):
            if segment.segment_id not in unlabelled:
                continue
            label = suggests.suggests(segment, titling) if self.dry_run else segment.label
            if label:
                yield segment, label
