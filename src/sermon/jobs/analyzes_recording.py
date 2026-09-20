from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.store import Job, Recording, Store


def now():
    return datetime.now(UTC)


STAGE_ORDER = (
    "envelope",
    "probe",
    "waveform",
    "preview",
    "transcription",
    "diarization",
    "blocking",
    "block_classification",
    "summarization",
    "segment_proposal",
    "boundary_refinement",
    "scoring",
)


@dataclass(frozen=True)
class RecordingContents:
    segments: tuple


CLASS_AND_SERVICE = RecordingContents(
    segments=(
        ("lesson", 60.0, 3300.0),
        ("sermon", 5400.0, 10800.0),
    )
)


@dataclass(frozen=True)
class AnalyzesRecording:
    store: Store
    stages: object
    notifies: object
    contents: object = CLASS_AND_SERVICE
    clock: object = now

    def __call__(self, recording):
        return recording


@dataclass(frozen=True)
class RunsAnalyzeJob:
    store: Store
    stages: object
    notifies: object
    contents: object = CLASS_AND_SERVICE
    clock: object = now

    def __call__(self):
        job = self.store.lists(Job, kind="analyze", state="queued")[0]
        recording = self.store.loads(Recording, job.recording_id)
        AnalyzesRecording(
            store=self.store,
            stages=self.stages,
            notifies=self.notifies,
            contents=self.contents,
            clock=self.clock,
        )(recording)
