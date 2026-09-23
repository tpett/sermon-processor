from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from sermon.adjusts_punch_point import (
    EDITABLE_STATES,
    NUDGE_STEPS,
    reads_boundary_history,
    warns_about_length,
)
from sermon.analysis.io import reads_json
from sermon.analysis.progress import reads_stage_progress, reads_transcription_progress
from sermon.draws_waveform import DrawsWaveform, WaveformView
from sermon.jobs.analyzes_recording import STAGE_ORDER
from sermon.lists_recordings import formats_clock, formats_precise, formats_recorded_at
from sermon.pipeline.preview import MEDIA_TYPE as PREVIEW_MEDIA_TYPE
from sermon.store import Artifact, Block, Job, Proposal, Recording, Segment, Store
from sermon.store import vocabularies

SIZE_UNITS = ("bytes", "KB", "MB", "GB", "TB")

PRE_REVIEW_PROGRESS = {
    "discovered": "Discovered in the object store; not downloaded or analysed yet",
    "downloading": "The source is being downloaded",
    "analyzing": "Analysis is running",
}

ANALYSIS_STAGE_LABELS = {
    "envelope": "measuring the audio envelope",
    "probe": "probing the source",
    "waveform": "drawing the waveform",
    "preview": "rendering the seekable preview",
    "transcription": "transcribing the audio",
    "diarization": "separating the speakers",
    "blocking": "dividing the service into blocks",
    "block_classification": "classifying each block",
    "summarization": "summarising each block",
    "segment_proposal": "proposing Segments",
    "boundary_refinement": "refining the boundaries",
    "scoring": "scoring the proposals",
}

STAGES_WORTH_SHOWING = frozenset({"analyzing", "analysis_failed"})
NOT_PICKED_UP_YET = "no stage has started yet; the worker has not picked this up"

SHORT_TAIL_SECONDS = 1.5

RECORDING_ACTION_PATHS = {
    "Discard": "discard",
    "Restore": "restore",
    "Retry ingestion": "retry-ingestion",
    "Retry analysis": "retry-analysis",
    "Re-run analysis": "re-run-analysis",
    "Create segment": "create-segment",
    "Create segment by hand": "create-segment",
    "Split segment": "split-segment",
    "Merge segments": "merge-segments",
    "Archive whole recording": "archive-whole-recording",
}

RECORDING_ACTION_PROMPTS = {
    "Discard": ("reason",),
    "Split segment": ("at",),
    "Create segment": ("from", "to"),
    "Create segment by hand": ("from", "to"),
}

SEGMENT_ACTION_PATHS = {
    "Approve": "approve",
    "Skip": "skip",
    "Revisit": "reopen",
    "Revert to proposed": "reopen",
    "Cancel processing": "reopen",
}

SEGMENT_ACTIONS = {
    "proposed": ("Approve", "Skip"),
    "skipped": ("Approve", "Revisit"),
    "approved": ("Cancel processing",),
    "processing": ("Cancel processing",),
    "processing_failed": ("Revert to proposed",),
    "recut": ("Approve", "Skip"),
    "complete": (),
}

NOTICES = {
    "approved": "the Segment is approved and queued for processing",
    "not-ready": "the Segment is not ready for approval",
    "already-approved": "it has already been approved",
    "label-required": "a publication label is required before publishing",
    "skipped": "the Segment is skipped and stays available",
    "reopened": "the Segment has returned to proposed",
    "adjusted": "the adjustment is saved without approving",
    "reverted": "the boundaries have returned to the machine proposal",
    "discarded": "the Recording is discarded and its source is untouched",
    "discard-needs-confirm": "it contains a published segment; confirm to discard it",
    "restored": "the Recording is restored",
    "archived": "the whole Recording is kept as an archive copy",
    "reanalysis-queued": "Analysis will run again and will not overwrite your work",
    "split": "the Segment is split",
    "merged": "the Segments are merged",
    "created": "the Segment is created",
    "the punch-out must be after the punch-in": "the punch-out must be after the punch-in",
    "the boundary must fall within the Segment": "the boundary must fall within the Segment",
    "the selection is too short": "the selection is too short",
    "the boundaries cannot be changed once the Segment is approved": (
        "the boundaries cannot be changed once the Segment is approved"
    ),
    "no machine proposal is recorded for this Segment": (
        "no machine proposal is recorded for this Segment"
    ),
    "a Segment that has already rendered cannot be reopened": (
        "a Segment that has already rendered cannot be reopened"
    ),
    "it would overlap the neighbouring Segment": "it would overlap the neighbouring Segment",
}

WHOLE_SPAN_NOTE = "the whole span will be kept"

PROCESSING_STEP = {
    "queued": "queued for processing",
    "running": "rendering the MP3",
    "succeeded": "processing is complete",
    "failed": "processing failed",
    "cancelled": "processing was cancelled",
}
# features/interface/waveform_review.feature, "Auditioning a boundary":
# playback starts 5 seconds before the boundary and stops 5 seconds after it.
PREVIEW_LEAD_SECONDS = 5.0
PREVIEW_UNAVAILABLE = (
    "The seekable preview has not been rendered, so there is nothing to play yet. "
    "The waveform, the transcript and the boundary controls are unaffected."
)

RECORDING_ACTIONS = {
    "discovered": "Discard",
    "downloading": "Discard",
    "ingest_failed": "Retry ingestion, Discard",
    "analyzing": "Discard",
    "analysis_failed": "Retry analysis, Create segment by hand, Discard",
    "awaiting_review": "Re-run analysis, Split segment, Merge segments, Create segment, Archive whole recording, Discard",
    "reviewed": "Create segment, Archive whole recording, Discard",
    "discarded": "Restore",
    "ignored": "Discard",
}


def formats_size(size_bytes):
    size = float(size_bytes)
    for unit in SIZE_UNITS:
        if size < 1024 or unit == SIZE_UNITS[-1]:
            return f"{size:.0f} bytes" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024


def formats_container(object_key):
    return PurePosixPath(object_key).suffix.lstrip(".").upper() or "recording"


def formats_source_format(recording):
    container = formats_container(recording.object_key)
    if recording.sample_rate is None:
        return f"{container}, not measured yet"
    measured = [container, f"{recording.sample_rate / 1000:g} kHz"]
    if recording.bits_per_raw_sample:
        measured.append(f"{recording.bits_per_raw_sample}-bit")
    if recording.channels is None:
        return " ".join(measured)
    shape = "channel 1 only" if recording.channels == 1 else f"{recording.channels} channels"
    return f"{' '.join(measured)}, {shape}"


def formats_seconds(seconds):
    return f"{float(seconds):.2f} s"


def formats_signed(seconds):
    """A signed offset, so a reviewer reads which side of the cut they are on.

    U+2212 MINUS SIGN rather than a hyphen: at a glance in a large readout a
    hyphen reads as a dash, and the sign is the whole point of the number.
    """
    value = float(seconds)
    if abs(value) < 0.005:
        return "0.00 s"
    sign = "+" if value > 0 else "\u2212"
    return f"{sign}{abs(value):.2f} s"


def formats_recognised(reported):
    """What transcription has heard so far, as the worker last wrote it down."""
    if not reported:
        return None
    said = []
    if reported.get("chunks"):
        said.append(f"chunk {reported.get('chunk')} of {reported.get('chunks')}")
    if reported.get("fraction") is not None:
        said.append(f"{round(reported['fraction'] * 100)}% of the audio recognised")
    if reported.get("recognised_seconds") is not None:
        said.append(
            f"{formats_clock(reported['recognised_seconds'])} "
            f"of {formats_clock(reported.get('duration_seconds') or 0)}"
        )
    return ", ".join(said) or None


def formats_took(seconds):
    if seconds is None:
        return None
    if seconds < 60:
        return f"{round(float(seconds), 1):g} s"
    return formats_clock(seconds)


def running_stage(stages):
    return next((stage for stage in stages if stage.state == "running"), None)


def names_running_stage(stages, running):
    if not stages:
        return None
    return NOT_PICKED_UP_YET if running is None else running.label


def counts_complete(stages):
    if not stages:
        return None
    done = len([stage for stage in stages if stage.state == "complete"])
    return f"{done} of {len(stages)} stages complete"


def artifact_url(path):
    return f"/api/artifacts/{path}"


def bounds_window(at_seconds, duration_seconds, lead=PREVIEW_LEAD_SECONDS):
    start = max(0.0, at_seconds - lead)
    end = at_seconds + lead
    if duration_seconds:
        end = min(float(duration_seconds), end)
    return start, end


@dataclass(frozen=True)
class PreviewWindow:
    """One audition: a boundary with the seconds either side of it."""

    kind: str
    label: str
    at_seconds: float
    start_seconds: float
    end_seconds: float

    @property
    def length_seconds(self):
        return self.end_seconds - self.start_seconds



@dataclass(frozen=True)
class BlockView:
    block_id: int | None
    type: str
    span: str
    start_seconds: float
    end_seconds: float
    summary: str | None
    cue_start_seconds: float | None
    cue_end_seconds: float | None


@dataclass(frozen=True)
class ActionView:
    name: str
    url: str
    prompts: tuple


@dataclass(frozen=True)
class BoundaryView:
    field: str
    seconds: float
    focused: bool
    url: str


# features/interface/waveform_review.feature, "A cut light shows the exact
# instant". Within this many seconds of the boundary the light reads "at": the
# instant itself, not a side of it. 50 ms is under the 100 ms the spec calls the
# placeable precision, so the light never claims the cut before it happens.
CUT_LIGHT_TOLERANCE_SECONDS = 0.05


@dataclass(frozen=True)
class CutLightView:
    """Which side of a boundary the playhead is on, and how far off it is.

    A punch-in keeps what follows it and discards what precedes it; a punch-out
    is the other way round. Getting that backwards would tell the reviewer the
    wrong thing with total confidence, so the two sides are named per boundary
    rather than assumed.
    """

    boundary: str
    at_seconds: float
    at: str
    offset_seconds: float
    offset: str
    state: str
    discards: str
    keeps: str
    side: str
    tolerance_seconds: float


@dataclass(frozen=True)
class CheckView:
    point: str
    grade: str


@dataclass(frozen=True)
class EvidenceView:
    timecode: float
    at: str
    finding: str
    implies: str


@dataclass(frozen=True)
class ProposalView:
    classification_confidence: str
    boundary_confidence: str
    punch_in_grade: str
    punch_out_grade: str
    agreement_gap_seconds: float | None
    evidence: tuple
    missing_evidence: tuple
    needs_checking: tuple


@dataclass(frozen=True)
class StageView:
    name: str
    label: str
    state: str
    detail: str | None
    took: str | None


@dataclass(frozen=True)
class SegmentView:
    segment_id: int
    classification: str
    span: str
    boundaries: str
    length: str
    confidence: str | None
    state: str
    punch_in_seconds: float
    punch_out_seconds: float
    cue_start_seconds: float | None
    cue_end_seconds: float | None


@dataclass(frozen=True)
class RecordingView:
    recording_id: str
    recorded_at: str
    duration: str
    state: str
    progress: str | None
    reason: str | None
    object_key: str
    container: str
    size: str
    format: str
    size_bytes: int
    sample_rate: int | None
    bits_per_raw_sample: int | None
    channels: int | None
    capture_device: str | None
    warnings: tuple
    segments: tuple
    actions: str
    duration_seconds: float
    waveform: WaveformView
    blocks: tuple
    selected_segment_id: int | None
    punch_in_seconds: float | None
    punch_out_seconds: float | None
    length_seconds: float | None
    gap_seconds: float | None
    short_tail: bool
    playhead_seconds: float
    preview_kind: str
    preview_ready: bool
    preview_url: str | None
    preview_media_type: str
    preview_duration_seconds: float | None
    preview_size_bytes: int | None
    preview_unavailable: str | None
    preview_lead_seconds: float
    preview_windows: tuple
    cue_excerpts: tuple
    mp3_ready: bool
    transcript: tuple
    selected_transcript: tuple
    notice: str | None
    recording_actions: tuple
    segment_actions: tuple
    selected_state: str | None
    intent: str | None
    intent_choices: tuple
    label: str | None
    boundary_controls: str
    boundaries: tuple
    focused_boundary: str | None
    nudge_steps: tuple
    proposed_punch_in_seconds: float | None
    proposed_punch_out_seconds: float | None
    length_warning: str | None
    alternatives: tuple
    whole_span_note: str | None
    processing_step: str | None
    processing_progress: str | None
    cut_light: CutLightView | None = None
    proposal: ProposalView | None = None
    analysis_stages: tuple = ()
    analysis_stage: str | None = None
    analysis_detail: str | None = None
    analysis_completed: str | None = None


@dataclass(frozen=True)
class ShowsRecording:
    store: Store

    def __call__(
        self,
        recording_id,
        *,
        selected_segment_id=None,
        playhead_seconds=0.0,
        zoom=None,
        centre_seconds=None,
        auditioning=None,
        notice=None,
        focused_boundary=None,
    ):
        recording = self.store.loads(Recording, recording_id)
        if recording is None:
            return None
        segments = self.store.lists(Segment, recording_id=recording_id)
        segments = sorted(segments, key=lambda segment: segment.span_start_seconds)
        selected = None
        if selected_segment_id is not None:
            selected = self.store.loads(Segment, selected_segment_id)
        elif segments:
            selected = segments[0]
        blocks = tuple(
            BlockView(
                block_id=block.block_id,
                type=block.type,
                span=(
                    f"{formats_clock(block.start_seconds)} – "
                    f"{formats_clock(block.end_seconds)}"
                ),
                start_seconds=block.start_seconds,
                end_seconds=block.end_seconds,
                summary=block.summary,
                cue_start_seconds=block.cue_start_seconds,
                cue_end_seconds=block.cue_end_seconds,
            )
            for block in sorted(
                self.store.lists(Block, recording_id=recording_id),
                key=lambda item: item.start_seconds,
            )
        )
        mp3_ready = any(
            item.state == "complete"
            for item in segments
        )
        duration_seconds = recording.duration_seconds or 0.0
        previews = self.store.lists(Artifact, recording_id=recording_id, kind="preview")
        preview = previews[-1] if previews else None
        preview_duration = None
        if preview is not None:
            preview_duration = (preview.render_settings or {}).get("duration_seconds")
        windows = ()
        if selected is not None:
            windows = tuple(
                PreviewWindow(
                    kind=kind,
                    label=label,
                    at_seconds=at,
                    start_seconds=bounds_window(at, duration_seconds)[0],
                    end_seconds=bounds_window(at, duration_seconds)[1],
                )
                for kind, label, at in (
                    ("punch-in", "Preview the punch-in", selected.punch_in_seconds),
                    ("punch-out", "Preview the punch-out", selected.punch_out_seconds),
                )
            )
        transcript = ()
        doc = reads_json(self.store, recording, "transcript")
        if doc:
            transcript = tuple(
                (item["start"], item["end"], item.get("text", ""), item.get("speaker"))
                for item in doc.get("utterances", [])
            )
        gap = self._gap(selected, segments, transcript)
        proposal = self._proposal(selected)
        step, progress = self._progress(selected)
        stages = self._analysis_stages(recording)
        running = running_stage(stages)
        cut_light = self._cut_light(selected, playhead_seconds)
        proposal_view = None
        if selected is not None:
            proposal_view = self._proposal_view(selected)
        return RecordingView(
            recording_id=recording.recording_id,
            recorded_at=formats_recorded_at(recording.started_at),
            duration=formats_clock(recording.duration_seconds or 0),
            state=recording.state,
            progress=PRE_REVIEW_PROGRESS.get(recording.state),
            reason=recording.skip_reason,
            object_key=recording.object_key,
            container=formats_container(recording.object_key),
            size=formats_size(recording.size_bytes),
            format=formats_source_format(recording),
            size_bytes=recording.size_bytes,
            sample_rate=recording.sample_rate,
            bits_per_raw_sample=recording.bits_per_raw_sample,
            channels=recording.channels,
            capture_device=recording.capture_device,
            warnings=recording.warnings,
            segments=tuple(
                self._segment(segment, self.store.lists(Block, recording_id=recording_id))
                for segment in segments
            ),
            actions=RECORDING_ACTIONS.get(recording.state, "Discard"),
            duration_seconds=duration_seconds,
            waveform=DrawsWaveform(store=self.store)(
                recording,
                selected=selected,
                transcript=transcript,
                evidence=() if proposal_view is None else proposal_view.evidence,
                zoom=zoom,
                centre_seconds=centre_seconds,
                playhead_seconds=playhead_seconds,
                auditioning=auditioning,
                needs_placing=(
                    None
                    if proposal_view is None or not proposal_view.needs_checking
                    else proposal_view.needs_checking[0].point
                ),
            ),
            blocks=blocks,
            selected_segment_id=None if selected is None else selected.segment_id,
            punch_in_seconds=None if selected is None else selected.punch_in_seconds,
            punch_out_seconds=None if selected is None else selected.punch_out_seconds,
            length_seconds=(
                None
                if selected is None
                else selected.punch_out_seconds - selected.punch_in_seconds
            ),
            gap_seconds=gap,
            short_tail=gap is not None and gap < SHORT_TAIL_SECONDS,
            playhead_seconds=playhead_seconds,
            preview_kind="preview",
            preview_ready=preview is not None,
            preview_url=None if preview is None else artifact_url(preview.path),
            preview_media_type=PREVIEW_MEDIA_TYPE,
            preview_duration_seconds=preview_duration,
            preview_size_bytes=None if preview is None else preview.size_bytes,
            preview_unavailable=None if preview is not None else PREVIEW_UNAVAILABLE,
            preview_lead_seconds=PREVIEW_LEAD_SECONDS,
            preview_windows=windows,
            cue_excerpts=tuple(
                block for block in blocks if block.cue_start_seconds is not None
            ),
            mp3_ready=mp3_ready,
            transcript=transcript,
            selected_transcript=self._scoped(transcript, selected),
            notice=NOTICES.get(notice),
            recording_actions=self._recording_actions(recording),
            segment_actions=self._segment_actions(selected),
            selected_state=None if selected is None else selected.state,
            intent=self._intent(selected),
            intent_choices=vocabularies.SEGMENT_INTENTS,
            label=None if selected is None else selected.label,
            boundary_controls=self._boundary_controls(selected),
            boundaries=self._boundaries(selected, focused_boundary),
            focused_boundary=focused_boundary,
            nudge_steps=NUDGE_STEPS,
            proposed_punch_in_seconds=proposal[0],
            proposed_punch_out_seconds=proposal[1],
            length_warning=(
                None
                if selected is None
                else warns_about_length(selected.punch_in_seconds, selected.punch_out_seconds)
            ),
            alternatives=self._alternatives(selected),
            whole_span_note=(
                WHOLE_SPAN_NOTE
                if selected is not None and selected.intent == "archive"
                else None
            ),
            processing_step=step,
            processing_progress=progress,
            cut_light=cut_light,
            proposal=proposal_view,
            analysis_stages=stages,
            analysis_stage=names_running_stage(stages, running),
            analysis_detail=None if running is None else running.detail,
            analysis_completed=counts_complete(stages),
        )

    def _recording_actions(self, recording):
        offered = RECORDING_ACTIONS.get(recording.state, "Discard").split(", ")
        return tuple(
            ActionView(
                name=name,
                url=(
                    f"/recordings/{recording.recording_id}/actions/"
                    f"{RECORDING_ACTION_PATHS[name]}"
                ),
                prompts=RECORDING_ACTION_PROMPTS.get(name, ()),
            )
            for name in offered
        )

    def _segment_actions(self, selected):
        if selected is None:
            return ()
        return tuple(
            ActionView(
                name=name,
                url=(
                    f"/recordings/{selected.recording_id}/segments/"
                    f"{selected.segment_id}/{SEGMENT_ACTION_PATHS[name]}"
                ),
                prompts=(),
            )
            for name in SEGMENT_ACTIONS.get(selected.state, ())
        )

    def _intent(self, selected):
        if selected is None:
            return None
        if selected.intent is not None:
            return selected.intent
        return "publish" if selected.classification == "sermon" else "archive"

    def _boundary_controls(self, selected):
        if selected is None:
            return "none"
        if selected.state not in EDITABLE_STATES:
            return "read-only"
        if self._intent(selected) == "archive":
            return "collapsed"
        return "editable"

    def _boundaries(self, selected, focused_boundary):
        if selected is None:
            return ()
        held = (("punch-in", selected.punch_in_seconds), ("punch-out", selected.punch_out_seconds))
        return tuple(
            BoundaryView(
                field=field,
                seconds=seconds,
                focused=field == focused_boundary,
                url=(
                    f"/recordings/{selected.recording_id}/segments/"
                    f"{selected.segment_id}/boundaries/{field}"
                ),
            )
            for field, seconds in held
        )

    def _gap(self, selected, segments, transcript):
        if selected is None:
            return None
        follows = [
            item.punch_in_seconds
            for item in segments
            if item.punch_in_seconds > selected.punch_out_seconds
        ]
        follows += [
            start for start, _, _, _ in transcript if start > selected.punch_out_seconds
        ]
        return min(follows) - selected.punch_out_seconds if follows else None

    def _cut_light(self, selected, playhead_seconds):
        if selected is None:
            return None
        boundaries = (
            ("punch-in", selected.punch_in_seconds),
            ("punch-out", selected.punch_out_seconds),
        )
        boundary, at = min(
            boundaries, key=lambda pair: abs(playhead_seconds - pair[1])
        )
        offset = playhead_seconds - at
        if abs(offset) <= CUT_LIGHT_TOLERANCE_SECONDS:
            state = "at"
        elif offset < 0:
            state = "before"
        else:
            state = "after"
        # A punch-in opens the published audio, so what precedes it is thrown
        # away. A punch-out closes it, so what precedes it is what was kept.
        if boundary == "punch-in":
            discards, keeps = "before the cut", "after the cut"
        else:
            discards, keeps = "after the cut", "before the cut"
        if state == "at":
            side = "on the cut"
        elif f"{state} the cut" == keeps:
            side = "kept"
        else:
            side = "discarded"
        return CutLightView(
            boundary=boundary,
            at_seconds=at,
            at=formats_precise(at),
            offset_seconds=offset,
            offset=formats_signed(offset),
            state=state,
            discards=discards,
            keeps=keeps,
            side=side,
            tolerance_seconds=CUT_LIGHT_TOLERANCE_SECONDS,
        )

    def _proposal_view(self, selected):
        proposals = [
            item
            for item in self.store.lists(Proposal, segment_id=selected.segment_id)
            if item.superseded_by is None
        ]
        if not proposals:
            return None
        proposal = proposals[-1]
        needs_checking = tuple(
            CheckView(point=name, grade=grade)
            for name, grade in (
                ("punch-in", proposal.punch_in_grade),
                ("punch-out", proposal.punch_out_grade),
            )
            if grade != "easy"
        )
        return ProposalView(
            classification_confidence=proposal.classification_confidence,
            boundary_confidence=proposal.boundary_confidence,
            punch_in_grade=proposal.punch_in_grade,
            punch_out_grade=proposal.punch_out_grade,
            agreement_gap_seconds=proposal.agreement_gap_seconds,
            evidence=tuple(
                EvidenceView(
                    timecode=item.timecode,
                    at=formats_precise(item.timecode),
                    finding=item.finding,
                    implies=item.implies,
                )
                for item in sorted(proposal.evidence, key=lambda item: item.timecode)
            ),
            missing_evidence=tuple(proposal.missing_evidence),
            needs_checking=needs_checking,
        )

    def _proposal(self, selected):
        if selected is None:
            return (None, None)
        machine = [
            entry
            for entry in reads_boundary_history(self.store, selected.segment_id)
            if entry.boundary_source != "human"
        ]
        if not machine:
            return (selected.punch_in_seconds, selected.punch_out_seconds)
        return (machine[0].punch_in_seconds, machine[0].punch_out_seconds)

    def _alternatives(self, selected):
        if selected is None:
            return ()
        return tuple(
            (candidate.timecode, candidate.considered_because)
            for proposal in self.store.lists(Proposal, segment_id=selected.segment_id)
            for candidate in proposal.punch_in_candidates
        )

    def _analysis_stages(self, recording):
        """The checklist the worker's log supports, never work done here."""
        if recording.state not in STAGES_WORTH_SHOWING:
            return ()
        logged = reads_stage_progress(self.store, recording)
        stages = []
        for name in STAGE_ORDER:
            recorded = logged.get(name)
            state = "pending" if recorded is None else recorded["state"]
            if state == "running" and recording.state == "analysis_failed":
                state = "failed"
            took = None if recorded is None else recorded["duration_seconds"]
            stages.append(
                StageView(
                    name=name,
                    label=ANALYSIS_STAGE_LABELS[name],
                    state=state,
                    detail=self._stage_detail(recording, name, state),
                    took=formats_took(took),
                )
            )
        return tuple(stages)

    def _stage_detail(self, recording, name, state):
        if name != "transcription" or state != "running":
            return None
        return formats_recognised(reads_transcription_progress(self.store, recording))

    def _progress(self, selected):
        if selected is None:
            return (None, None)
        jobs = self.store.lists(Job, segment_id=selected.segment_id, kind="render")
        if not jobs:
            return (None, None)
        job = jobs[-1]
        return (
            PROCESSING_STEP.get(job.state),
            f"attempt {max(job.attempts, 1)} of {job.max_attempts}",
        )

    def _scoped(self, transcript, selected):
        if selected is None:
            return transcript
        return tuple(
            item
            for item in transcript
            if item[1] > selected.punch_in_seconds and item[0] < selected.punch_out_seconds
        )

    def _seeding_block(self, blocks, segment):
        """The Block whose cue excerpt stands for this Segment."""
        overlapping = [
            block
            for block in blocks
            if block.start_seconds is not None
            and block.end_seconds is not None
            and block.end_seconds > segment.span_start_seconds
            and block.start_seconds < segment.span_end_seconds
        ]
        same_type = [block for block in overlapping if block.type == segment.classification]
        for block in same_type or overlapping:
            if block.cue_start_seconds is not None:
                return block
        return None

    def _segment(self, segment, blocks=()):
        proposals = self.store.lists(Proposal, segment_id=segment.segment_id)
        confidence = proposals[0].classification_confidence if proposals else None
        seeding = self._seeding_block(blocks, segment)
        return SegmentView(
            segment_id=segment.segment_id,
            classification=segment.classification,
            span=f"{formats_clock(segment.span_start_seconds)} – {formats_clock(segment.span_end_seconds)}",
            boundaries=f"{formats_clock(segment.punch_in_seconds)} – {formats_clock(segment.punch_out_seconds)}",
            length=formats_clock(segment.punch_out_seconds - segment.punch_in_seconds),
            confidence=confidence,
            state=segment.state,
            punch_in_seconds=segment.punch_in_seconds,
            punch_out_seconds=segment.punch_out_seconds,
            cue_start_seconds=None if seeding is None else seeding.cue_start_seconds,
            cue_end_seconds=None if seeding is None else seeding.cue_end_seconds,
        )
