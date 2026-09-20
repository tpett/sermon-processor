from __future__ import annotations

from dataclasses import dataclass

from sermon.lists_recordings import formats_clock, formats_recorded_at
from sermon.store import Artifact, Block, Proposal, Recording, Segment, Store

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
    object_key: str
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
    playhead_seconds: float
    preview_kind: str
    mp3_ready: bool


@dataclass(frozen=True)
class ShowsRecording:
    store: Store

    def __call__(self, recording_id, *, selected_segment_id=None, playhead_seconds=0.0):
        recording = self.store.loads(Recording, recording_id)
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
            (block.type, block.start_seconds, block.end_seconds, block.summary)
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
        return RecordingView(
            recording_id=recording.recording_id,
            recorded_at=formats_recorded_at(recording.started_at),
            duration=formats_clock(recording.duration_seconds or 0),
            state=recording.state,
            object_key=recording.object_key,
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
            playhead_seconds=playhead_seconds,
            preview_kind="preview",
            mp3_ready=mp3_ready,
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
