from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.analysis import (
    ClassifiesBlocks,
    DiarizesRecording,
    DividesIntoBlocks,
    ProposesSegments,
    RefinesPunchIn,
    RefinesPunchOut,
    ScoresProposals,
    SummarizesBlocks,
    TranscribesRecording,
)
from sermon.analysis.progress import RecordsStageProgress
from sermon.config import ModelEndpointUnreachable
from sermon.extends_segment_span import WidensProposedSpan
from sermon.jobs.generates_preview import GeneratesPreview
from sermon.pipeline.preview import PreviewUnavailable
from sermon.jobs.generates_waveform_peaks import GeneratesWaveformPeaks
from sermon.jobs.probes_recording import ProbeResult, ProbesRecording
from sermon.store import Artifact, Block, Job, LogEntry, Notification, Proposal, Recording, Segment, Store, layout


def now():
    return datetime.now(UTC)


def _elapsed(began, ended):
    if not isinstance(began, datetime) or not isinstance(ended, datetime):
        return None
    return round((ended - began).total_seconds(), 3)


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
NOTHING_FABRICATED = RecordingContents(segments=())


ITERATED_STAGES = ("blocking", "block_classification")
WALK = (
    STAGE_ORDER[: STAGE_ORDER.index("blocking")]
    + ITERATED_STAGES * 2
    + STAGE_ORDER[STAGE_ORDER.index("block_classification") + 1 :]
)
REASONING_STAGES = frozenset({"block_classification", "summarization"})
OPTIONAL_STAGES = frozenset({"waveform", "preview", "summarization", "diarization"})
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
    contents: object = NOTHING_FABRICATED
    clock: object = now
    reaches: object = None
    only: str | None = None
    measures: object = None
    analyses: object = None
    transcribes: object = None
    divides: object = None

    def _run_stage(self, recording, name):
        records = RecordsStageProgress(store=self.store, clock=self.clock)
        records.started(recording, name)
        began = self.clock()
        outcome = self._performs_stage(self.store.loads(Recording, recording.recording_id), name)
        records.completed(recording, name, _elapsed(began, self.clock()))
        return outcome

    def _performs_stage(self, recording, name):
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
        if name == "probe":
            measures = self.measures or (
                lambda item: ProbeResult(
                    duration_seconds=item.duration_seconds or 0.0,
                    sample_rate=item.sample_rate or 44100,
                    channels=item.channels or 1,
                    bits_per_raw_sample=item.bits_per_raw_sample,
                    channel_levels=item.channel_levels,
                    integrated_loudness_lufs=item.integrated_loudness_lufs,
                    true_peak_dbtp=item.true_peak_dbtp,
                    loudness_range_lu=item.loudness_range_lu,
                    dynamic_range_db=item.dynamic_range_db,
                    active_fraction=item.active_fraction,
                )
            )
            probed = ProbesRecording(store=self.store, measures=measures)(recording)
            if probed.state == "ignored":
                return "stop"
        if name == "waveform":
            GeneratesWaveformPeaks(store=self.store, clock=self.clock)(recording)
            return
        if name == "preview":
            try:
                GeneratesPreview(store=self.store)(recording)
            except PreviewUnavailable:
                return
            return
        if name == "transcription":
            TranscribesRecording(store=self.store, transcribes=self.transcribes)(recording)
            return
        if name == "diarization":
            try:
                DiarizesRecording(store=self.store)(recording)
            except StageFailed:
                pass
            return
        if name == "blocking":
            DividesIntoBlocks(store=self.store, divides=self.divides)(recording)
            return
        if name == "block_classification":
            if self.reaches is not None:
                self.reaches()
            ClassifiesBlocks(store=self.store)(recording)
            return
        if name == "summarization":
            if self.reaches is not None:
                self.reaches()
            SummarizesBlocks(store=self.store)(recording)
            return
        if name == "segment_proposal":
            ProposesSegments(store=self.store)(recording)
            return
        if name == "boundary_refinement":
            RefinesPunchIn(store=self.store)(recording)
            RefinesPunchOut(store=self.store)(recording)
            return
        if name == "scoring":
            ScoresProposals(store=self.store)(recording)
            return
        if name in REASONING_STAGES and self.reaches is not None:
            self.reaches()
        if artifact_kind and artifact_kind not in cached:
            self.store.saves(
                Artifact(
                    recording_id=recording.recording_id,
                    kind=artifact_kind,
                    path=layout.artifact_path(recording.recording_id, artifact_kind),
                    size_bytes=1,
                    checksum="0.0" if artifact_kind == "waveform_peaks" else name,
                )
            )
        if name == "blocking" and not self.store.lists(Block, recording_id=recording.recording_id):
            DividesIntoBlocks(store=self.store)(recording)

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
            if self.analyses is not None:
                self.analyses(analyzing)
            else:
                for name in WALK:
                    if self._run_stage(analyzing, name) == "stop":
                        return self.store.loads(Recording, recording.recording_id)
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
            self.store.saves(
                replace(self.store.loads(Recording, recording.recording_id), state="analysis_failed")
            )
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
        analyzed = self.store.loads(Recording, recording.recording_id)
        if not self.store.lists(Segment, recording_id=recording.recording_id):
            for classification, punch_in, punch_out in self.contents.segments:
                segment = self.store.saves(
                    WidensProposedSpan(store=self.store)(
                        Segment(
                            recording_id=recording.recording_id,
                            classification=classification,
                            state="proposed",
                            span_start_seconds=punch_in,
                            span_end_seconds=punch_out,
                            punch_in_seconds=punch_in,
                            punch_out_seconds=punch_out,
                        ),
                        analyzed.duration_seconds,
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
        reviewed = self.store.saves(replace(analyzed, state="awaiting_review"))
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=correlation_id,
                entered_state="awaiting_review",
            )
        )
        if self.store.lists(Segment, recording_id=recording.recording_id):
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
    contents: object = NOTHING_FABRICATED
    clock: object = now
    reaches: object = None
    only: str | None = None
    measures: object = None
    analyses: object = None
    transcribes: object = None
    divides: object = None
    recording_id: str | None = None

    def __call__(self):
        job = [
            queued
            for queued in self.store.lists(Job, kind="analyze", state="queued")
            if self.recording_id in (None, queued.recording_id)
        ][0]
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
                measures=self.measures,
                analyses=self.analyses,
                transcribes=self.transcribes,
                divides=self.divides,
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
