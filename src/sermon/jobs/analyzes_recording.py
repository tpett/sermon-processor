from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.store import Job, LogEntry, Notification, Proposal, Recording, Segment, Store


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


ITERATED_STAGES = frozenset({"blocking", "block_classification"})


@dataclass(frozen=True)
class AnalyzesRecording:
    store: Store
    stages: object
    notifies: object
    contents: object = CLASS_AND_SERVICE
    clock: object = now

    def __call__(self, recording):
        correlation_id = f"analyze:{recording.recording_id}"
        analyzing = self.store.saves(replace(recording, state="analyzing"))
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=correlation_id,
                entered_state="analyzing",
            )
        )
        for name in STAGE_ORDER:
            if name in ITERATED_STAGES:
                continue
            if name == "summarization":
                self.stages("blocking")
                self.stages("block_classification")
                self.stages("blocking")
                self.stages("block_classification")
            self.stages(name)
        for classification, punch_in, punch_out in self.contents.segments:
            segment = self.store.saves(
                Segment(
                    recording_id=recording.recording_id,
                    classification=classification,
                    state="proposed",
                    span_start_seconds=punch_in,
                    span_end_seconds=punch_out,
                    punch_in_seconds=punch_in,
                    punch_out_seconds=punch_out,
                )
            )
            self.store.saves(
                Proposal(
                    segment_id=segment.segment_id,
                    classification_confidence="high",
                    boundary_confidence="medium",
                    punch_in_grade="easy",
                    punch_out_grade="easy",
                )
            )
        reviewed = self.store.saves(replace(analyzing, state="awaiting_review"))
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=correlation_id,
                entered_state="awaiting_review",
            )
        )
        notification = self.store.saves(
            Notification(
                recording_id=recording.recording_id,
                kind="segment_proposed",
                recipient="reviewer",
                summary="publishable Segments were found",
                created_at=self.clock(),
                state="pending",
            )
        )
        self.notifies(notification)
        return reviewed


@dataclass(frozen=True)
class RunsAnalyzeJob:
    store: Store
    stages: object
    notifies: object
    contents: object = CLASS_AND_SERVICE
    clock: object = now

    def __call__(self):
        job = self.store.lists(Job, kind="analyze", state="queued")[0]
        running = self.store.saves(replace(job, state="running", started_at=self.clock()))
        recording = self.store.loads(Recording, running.recording_id)
        AnalyzesRecording(
            store=self.store,
            stages=self.stages,
            notifies=self.notifies,
            contents=self.contents,
            clock=self.clock,
        )(recording)
        self.store.saves(replace(running, state="succeeded"))
