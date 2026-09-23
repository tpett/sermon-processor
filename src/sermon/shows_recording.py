from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from sermon.analysis.io import reads_json
from sermon.draws_waveform import DrawsWaveform, WaveformView
from sermon.lists_recordings import formats_clock, formats_recorded_at
from sermon.store import Block, Proposal, Recording, Segment, Store

SIZE_UNITS = ("bytes", "KB", "MB", "GB", "TB")

PRE_REVIEW_PROGRESS = {
    "discovered": "Discovered in the object store; not downloaded or analysed yet",
    "downloading": "The source is being downloaded",
    "analyzing": "Analysis is running",
}

SHORT_TAIL_SECONDS = 1.5

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
    mp3_ready: bool
    transcript: tuple
    selected_transcript: tuple


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
    ):
        recording = self.store.loads(Recording, recording_id)
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
        transcript = ()
        doc = reads_json(self.store, recording, "transcript")
        if doc:
            transcript = tuple(
                (item["start"], item["end"], item.get("text", ""), item.get("speaker"))
                for item in doc.get("utterances", [])
            )
        gap = self._gap(selected, segments, transcript)
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
            waveform=DrawsWaveform(store=self.store)(
                recording,
                selected=selected,
                transcript=transcript,
                evidence=self._evidence(selected),
                zoom=zoom,
                centre_seconds=centre_seconds,
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
            mp3_ready=mp3_ready,
            transcript=transcript,
            selected_transcript=self._scoped(transcript, selected),
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

    def _evidence(self, selected):
        if selected is None:
            return ()
        proposals = self.store.lists(Proposal, segment_id=selected.segment_id)
        return proposals[0].evidence if proposals else ()

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
