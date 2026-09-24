"""What the analyze job is doing right now, for the other container to read.

The web app and the worker are separate processes over one volume, so progress
cannot live in memory the way the playhead does. Stage edges go in the log, whose
`kind` is free text. Transcription's own fraction moves every few seconds for half
an hour, so it goes in one small JSON document that is overwritten in place.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sermon.store import LogEntry, layout


def now():
    return datetime.now(UTC)


STAGE_STARTED = "stage_started"
STAGE_COMPLETE = "stage_complete"
TRANSCRIPTION_PROGRESS = "analysis_progress"
REPORT_EVERY_SECONDS = 2.0


def correlation_for(recording):
    return f"analyze:{recording.recording_id}"


def kind_for(status, stage):
    return f"{status}:{stage}"


def reads_kind(kind):
    """The status and stage a progress log entry carries, or nothing."""
    status, _, stage = (kind or "").partition(":")
    if status not in (STAGE_STARTED, STAGE_COMPLETE) or not stage:
        return None
    return status, stage


@dataclass(frozen=True)
class RecordsStageProgress:
    """One log entry per stage edge, with how long the stage took."""

    store: object
    clock: object = now

    def started(self, recording, stage):
        return self._logs(recording, kind_for(STAGE_STARTED, stage))

    def completed(self, recording, stage, duration_seconds=None):
        return self._logs(
            recording, kind_for(STAGE_COMPLETE, stage), duration_seconds=duration_seconds
        )

    def _logs(self, recording, kind, duration_seconds=None):
        return self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind=kind,
                occurred_at=self.clock(),
                correlation_id=correlation_for(recording),
                duration_seconds=duration_seconds,
            )
        )


def reads_stage_progress(store, recording):
    """Each stage the log mentions, by its last word: blocking runs twice."""
    seen = {}
    for entry in store.lists(LogEntry, recording_id=recording.recording_id):
        read = reads_kind(entry.kind)
        if read is None:
            continue
        status, stage = read
        seen[stage] = {
            "state": "complete" if status == STAGE_COMPLETE else "running",
            "duration_seconds": entry.duration_seconds,
            "occurred_at": entry.occurred_at,
        }
    return seen


def progress_path(store, recording):
    return store.resolves_path(layout.progress_path(recording.recording_id))


def writes_transcription_progress(store, recording, payload):
    """Replace the document atomically: the page may be reading it right now."""
    path = progress_path(store, recording)
    path.parent.mkdir(parents=True, exist_ok=True)
    writing = path.with_name(f"{path.name}.writing")
    writing.write_text(json.dumps(payload, sort_keys=True))
    os.replace(writing, path)
    return path


def reads_transcription_progress(store, recording):
    path = progress_path(store, recording)
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


@dataclass
class ReportsTranscriptionProgress:
    """Called from inside the recogniser's loop, not after it.

    Throttled on wall clock; a change of chunk always gets through.
    """

    store: object
    every: float = REPORT_EVERY_SECONDS
    clock: object = time.monotonic
    stamps: object = now
    last: list = field(default_factory=list)

    def __call__(self, recording, *, chunk, chunks, recognised_seconds, duration_seconds):
        if not self._is_due(chunk):
            return None
        fraction = None
        if duration_seconds:
            fraction = round(min(1.0, max(0.0, recognised_seconds / duration_seconds)), 4)
        return writes_transcription_progress(
            self.store,
            recording,
            {
                "stage": "transcription",
                "chunk": chunk,
                "chunks": chunks,
                "recognised_seconds": round(float(recognised_seconds), 1),
                "duration_seconds": round(float(duration_seconds or 0.0), 1),
                "fraction": fraction,
                "updated_at": self.stamps().isoformat(),
            },
        )

    def _is_due(self, chunk):
        at = self.clock()
        if self.last and self.last[0] == chunk and at - self.last[1] < self.every:
            return False
        self.last[:] = (chunk, at)
        return True
