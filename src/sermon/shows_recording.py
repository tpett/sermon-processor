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
from sermon.lists_recordings import formats_clock, formats_recorded_at
from sermon.store import Artifact, Block, Job, Proposal, Recording, Segment, Store
from sermon.store import vocabularies

SIZE_UNITS = ("bytes", "KB", "MB", "GB", "TB")

PRE_REVIEW_PROGRESS = {
    "discovered": "Discovered in the object store; not downloaded or analysed yet",
    "downloading": "The source is being downloaded",
    "analyzing": "Analysis is running",
}

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


def formats_precise(seconds):
    hours, rest = divmod(float(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def formats_seconds(seconds):
    return f"{float(seconds):.2f} s"


@dataclass(frozen=True)
class BlockView:
    block_id: int | None
    type: str
    span: str
    start_seconds: float
    end_seconds: float
    summary: str | None


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
class SegmentView:
    segment_id: int
    classification: str
    span: str
    boundaries: str
    length: str
    confidence: str | None
    state: str


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
    peaks: tuple
    blocks: tuple
    selected_segment_id: int | None
    punch_in_seconds: float | None
    punch_out_seconds: float | None
    length_seconds: float | None
    gap_seconds: float | None
    zoom_steps: tuple
    short_tail: bool
    playhead_seconds: float
    preview_kind: str
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
    proposal: ProposalView | None = None


@dataclass(frozen=True)
class ShowsRecording:
    store: Store

    def __call__(
        self,
        recording_id,
        *,
        selected_segment_id=None,
        playhead_seconds=0.0,
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
        peaks = ()
        for artifact in self.store.lists(Artifact, recording_id=recording_id, kind="waveform_peaks"):
            try:
                peaks = tuple(float(value) for value in artifact.checksum.split(",") if value)
            except ValueError:
                peaks = ()
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
            )
            for block in sorted(
                self.store.lists(Block, recording_id=recording_id),
                key=lambda item: item.start_seconds,
            )
        )
        gap = None
        if selected is not None:
            later = [
                item.punch_in_seconds
                for item in segments
                if item.punch_in_seconds > selected.punch_out_seconds
            ]
            if later:
                gap = min(later) - selected.punch_out_seconds
        mp3_ready = any(
            item.state == "complete"
            for item in segments
        )
        transcript = ()
        doc = reads_json(self.store, recording, "transcript")
        if doc:
            transcript = tuple(
                (item["start"], item["end"], item.get("text", ""), item.get("speaker"))
                for item in doc.get("utterances", [])
            )
        proposal = self._proposal(selected)
        step, progress = self._progress(selected)
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
            segments=tuple(self._segment(segment) for segment in segments),
            actions=RECORDING_ACTIONS.get(recording.state, "Discard"),
            duration_seconds=recording.duration_seconds or 0.0,
            peaks=peaks,
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
            zoom_steps=("whole recording", "a few minutes", "thirty seconds", "three seconds"),
            short_tail=gap is not None and gap < SHORT_TAIL_SECONDS,
            playhead_seconds=playhead_seconds,
            preview_kind="preview",
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
            proposal=proposal_view,
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

    def _segment(self, segment):
        proposals = self.store.lists(Proposal, segment_id=segment.segment_id)
        confidence = proposals[0].classification_confidence if proposals else None
        return SegmentView(
            segment_id=segment.segment_id,
            classification=segment.classification,
            span=f"{formats_clock(segment.span_start_seconds)} – {formats_clock(segment.span_end_seconds)}",
            boundaries=f"{formats_clock(segment.punch_in_seconds)} – {formats_clock(segment.punch_out_seconds)}",
            length=formats_clock(segment.punch_out_seconds - segment.punch_in_seconds),
            confidence=confidence,
            state=segment.state,
        )
