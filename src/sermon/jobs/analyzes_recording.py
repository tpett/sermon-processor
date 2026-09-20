from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.config import ModelEndpointUnreachable
from sermon.jobs.generates_waveform_peaks import GeneratesWaveformPeaks
from sermon.store import Artifact, Block, Job, LogEntry, Notification, Proposal, Recording, Segment, Store


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
REASONING_STAGES = frozenset({"block_classification", "summarization"})
OPTIONAL_STAGES = frozenset({"waveform"})
STAGE_ARTIFACTS = {
    "envelope": "envelope",
    "waveform": "waveform_peaks",
    "preview": "preview",
    "transcription": "transcript",
    "diarization": "diarization",
}


class StageFailed(RuntimeError):
    def __init__(self, stage, error="failed"):
        super().__init__(error)
        self.stage = stage
        self.error = error


@dataclass(frozen=True)
class AnalyzesRecording:
    store: Store
    stages: object
    notifies: object
    contents: object = CLASS_AND_SERVICE
    clock: object = now
    reaches: object = None
    only: str | None = None

    def _run_stage(self, recording, name):
        cached = {
            artifact.kind
            for artifact in self.store.lists(Artifact, recording_id=recording.recording_id)
        }
        artifact_kind = STAGE_ARTIFACTS.get(name)
        if self.only is not None and name != self.only and artifact_kind in cached:
            return
        try:
            self.stages(name)
        except StageFailed:
            if name in OPTIONAL_STAGES:
                return
            raise
        if name == "waveform":
            GeneratesWaveformPeaks(store=self.store, clock=self.clock)(recording)
            return
        if name in REASONING_STAGES and self.reaches is not None:
            self.reaches()
        if artifact_kind and artifact_kind not in cached:
            self.store.saves(
                Artifact(
                    recording_id=recording.recording_id,
                    kind=artifact_kind,
                    path=f"{recording.recording_id}/{artifact_kind}",
                    size_bytes=1,
                    checksum="0.0" if artifact_kind == "waveform_peaks" else name,
                )
            )
        if name == "blocking" and not self.store.lists(Block, recording_id=recording.recording_id):
            self.store.saves(
                Block(
                    recording_id=recording.recording_id,
                    start_seconds=0.0,
                    end_seconds=recording.duration_seconds or 0.0,
                    type="sermon",
                )
            )

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
        name = "envelope"
        try:
            for name in STAGE_ORDER:
                if name in ITERATED_STAGES:
                    continue
                if name == "summarization":
                    self._run_stage(analyzing, "blocking")
                    self._run_stage(analyzing, "block_classification")
                    self._run_stage(analyzing, "blocking")
                    self._run_stage(analyzing, "block_classification")
                self._run_stage(analyzing, name)
        except ModelEndpointUnreachable as error:
            self.store.saves(
                LogEntry(
                    recording_id=recording.recording_id,
                    kind="state_change",
                    occurred_at=self.clock(),
                    correlation_id=correlation_id,
                    error=str(error),
                )
            )
            raise
        except Exception as error:
            stage = getattr(error, "stage", name)
            self.store.saves(replace(analyzing, state="analysis_failed"))
            self.store.saves(
                LogEntry(
                    recording_id=recording.recording_id,
                    kind="state_change",
                    occurred_at=self.clock(),
                    correlation_id=correlation_id,
                    entered_state="analysis_failed",
                    error=f"{stage}: {error}",
                )
            )
            raise StageFailed(stage, str(error)) from error
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
    reaches: object = None
    only: str | None = None

    def __call__(self):
        job = self.store.lists(Job, kind="analyze", state="queued")[0]
        running = self.store.saves(replace(job, state="running", started_at=self.clock()))
        recording = self.store.loads(Recording, running.recording_id)
        try:
            AnalyzesRecording(
                store=self.store,
                stages=self.stages,
                notifies=self.notifies,
                contents=self.contents,
                clock=self.clock,
                reaches=self.reaches,
                only=self.only,
            )(recording)
        except StageFailed as error:
            self.store.saves(
                replace(
                    running,
                    state="failed",
                    last_error=str(error),
                    attempts=(running.attempts or 0) + 1,
                )
            )
            return
        except ModelEndpointUnreachable as error:
            self.store.saves(
                replace(
                    running,
                    state="failed",
                    last_error=str(error),
                    attempts=(running.attempts or 0) + 1,
                )
            )
            return
        self.store.saves(replace(running, state="succeeded"))
