from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.analysis.titles_recording import TITLE_LIMIT
from sermon.store import LogEntry, RecordingTitle, Store

EMPTY_TITLE = "a title cannot be empty"


def now():
    return datetime.now(UTC)


class TitleRejected(ValueError):
    pass


@dataclass(frozen=True)
class RetitlesRecording:
    """The reviewer's own title, which analysis never replaces."""

    store: Store
    clock: object = now

    def __call__(self, recording, title, *, actor="reviewer"):
        written = " ".join((title or "").split())[:TITLE_LIMIT]
        if not written:
            raise TitleRejected(EMPTY_TITLE)
        held = self.store.loads(RecordingTitle, recording.recording_id)
        titled = self.store.saves(
            RecordingTitle(
                recording_id=recording.recording_id,
                title=written,
                series=held.series if held else None,
                edited_by_human=True,
            )
        )
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="title_change",
                occurred_at=self.clock(),
                correlation_id=f"retitle:{recording.recording_id}",
                actor=actor,
            )
        )
        return titled
