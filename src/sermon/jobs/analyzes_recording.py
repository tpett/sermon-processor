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
from sermon.analysis.transcribes_audio import AudioNotDecodable
from sermon.config import ModelEndpointUnreachable
from sermon.extends_segment_span import WidensProposedSpan
from sermon.jobs.generates_preview import GeneratesPreview
from sermon.jobs.generates_waveform_peaks import GeneratesWaveformPeaks
from sermon.jobs.probes_recording import ProbeResult, ProbesRecording
from sermon.raises_notification import TellsAnalysisFailed, TellsAnalysisOutcome
from sermon.store import Artifact, Job, LogEntry, Proposal, Recording, Segment, Store


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
OPTIONAL_STAGE_FAILED = "optional_stage_failed"
STAGE_ARTIFACTS = {
    "waveform": "waveform_peaks",
    "preview": "preview",
    "transcription": "transcript",
    "diarization": "diarization",
}


class StageFailed(RuntimeError):
    def __init__(self, stage, error="failed", *, permanent=False):
        super().__init__(error)
        self.stage = stage
        self.error = error
        self.permanent = permanent


def names_failure(error):
    stage = getattr(error, "stage", None)
    return str(error) if stage is None else f"{stage}: {error}"


def causes(error):
    while error is not None:
        yield error
        error = error.__cause__


def cannot_succeed_on_retry(error):
    chain = tuple(causes(error))
    return any(isinstance(link, AudioNotDecodable) for link in chain) and not any(
        isinstance(link, OSError) for link in chain
    )


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
    diarizes: object = None
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
        if self.only is not None and name != self.only and STAGE_ARTIFACTS.get(name) in cached:
            return
        try:
            self.stages(name)
            return self._works(recording, name)
        except ModelEndpointUnreachable:
            raise
        except Exception as error:
            if name not in OPTIONAL_STAGES:
                raise
            self.store.saves(
                LogEntry(
                    recording_id=recording.recording_id,
                    kind=OPTIONAL_STAGE_FAILED,
                    occurred_at=self.clock(),
                    correlation_id=f"analyze:{recording.recording_id}",
                    error=f"{name}: {error}",
                )
            )

    def _works(self, recording, name):
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
        if name == "preview":
            GeneratesPreview(store=self.store)(recording)
        if name == "transcription":
            TranscribesRecording(store=self.store, transcribes=self.transcribes)(recording)
        if name == "diarization":
            DiarizesRecording(store=self.store, diarizes=self.diarizes)(recording)
        if name == "blocking":
            DividesIntoBlocks(store=self.store, divides=self.divides)(recording)
        if name in REASONING_STAGES and self.reaches is not None:
            self.reaches()
        if name == "block_classification":
            ClassifiesBlocks(store=self.store)(recording)
        if name == "summarization":
            SummarizesBlocks(store=self.store)(recording)
        if name == "segment_proposal":
            ProposesSegments(store=self.store)(recording)
        if name == "boundary_refinement":
            RefinesPunchIn(store=self.store)(recording)
            RefinesPunchOut(store=self.store)(recording)
        if name == "scoring":
            ScoresProposals(store=self.store)(recording)

    def _fails(self, recording, reason, *, final):
        entered = "analysis_failed" if final else "downloaded"
        self.store.saves(
            replace(self.store.loads(Recording, recording.recording_id), state=entered)
        )
        self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=f"analyze:{recording.recording_id}",
                entered_state=entered,
                error=reason,
            )
        )
        if final:
            TellsAnalysisFailed(store=self.store, notifies=self.notifies, clock=self.clock)(
                recording, reason
            )

    def __call__(self, recording, *, final_attempt=True):
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
            self._fails(recording, f"{name}: {error}", final=final_attempt)
            raise
        except Exception as error:
            stage = getattr(error, "stage", name)
            permanent = cannot_succeed_on_retry(error)
            self._fails(recording, f"{stage}: {error}", final=final_attempt or permanent)
            raise StageFailed(stage, str(error), permanent=permanent) from error
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
        TellsAnalysisOutcome(store=self.store, notifies=self.notifies, clock=self.clock)(reviewed)
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
    diarizes: object = None
    divides: object = None
    recording_id: str | None = None
    job_id: int | None = None

    def __call__(self):
        job = [
            queued
            for queued in self.store.lists(Job, kind="analyze", state="queued")
            if self.recording_id in (None, queued.recording_id)
            and self.job_id in (None, queued.job_id)
        ][0]
        running = self.store.saves(replace(job, state="running", started_at=self.clock()))
        recording = self.store.loads(Recording, running.recording_id)
        attempts = (running.attempts or 0) + 1
        final = attempts >= running.max_attempts
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
                diarizes=self.diarizes,
                divides=self.divides,
            )(recording, final_attempt=final)
        except (StageFailed, ModelEndpointUnreachable) as error:
            stops = final or getattr(error, "permanent", False)
            self.store.saves(
                replace(
                    running,
                    state="failed" if stops else "queued",
                    last_error=names_failure(error),
                    attempts=attempts,
                    failed_permanently=stops,
                )
            )
            return
        self.store.saves(replace(running, state="succeeded"))
