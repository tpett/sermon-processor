from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sermon.analysis.io import reads_json
from sermon.lists_recordings import formats_clock, formats_precise
from sermon.store import Block, Segment

CANVAS_PIXELS = 1100
PRECISION_SECONDS = 0.1
VERDICT_THRESHOLDS = ((1.0, "impossible"), (10.0, "awkward"))
COMFORTABLE = "comfortable"

ZOOM_STEPS = (
    ("whole recording", None, "find where in the service to look"),
    ("a few minutes", 300.0, "narrow down to the moment"),
    ("thirty seconds", 30.0, "read the words either side"),
    ("three seconds", 3.0, "place the cut"),
)
DEFAULT_ZOOM = "thirty seconds"
PLACING_ZOOM = "three seconds"
WORDS_IN_VIEW = {
    "whole recording": "more than can be read",
    "a few minutes": "more than can be read",
    "thirty seconds": "about 48",
    "three seconds": "none",
}

RULER_STEPS = (30, 60, 120, 300, 600, 900, 1800, 3600)
RULER_MARKS = 13

BAND_COLOURS = {
    "announcements": "#c9a227",
    "music": "#4f7cac",
    "prayer": "#7a6ea8",
    "scripture_reading": "#3f8f7a",
    "sermon": "#a3320b",
    "lesson": "#c2601c",
    "seminar": "#8a6d3b",
    "communion": "#6b7a8f",
    "qa": "#5f8a3f",
    "rehearsal": "#9aa0a6",
    "other": "#b0b3b6",
}
UNTYPED_COLOUR = "#b0b3b6"
NON_SPEECH_TYPES = ("music", "rehearsal")
SPEAKER_COLOURS = ("#2f6f4f", "#8a4f9e", "#b06a1f", "#3a6ea5", "#8f3b52")
NON_SPEECH_SPEAKER_COLOUR = "#c3c7ca"
WORDS_DRAWN = 120
AUDITION_LEAD_SECONDS = 5.0
KEPT = "kept"
CUT_AWAY = "cut away"
BOUNDARIES = ("punch-in", "punch-out")


def clamps(value):
    return max(0.0, min(100.0, value))


def spans_percent(start, end, duration):
    if duration <= 0:
        return 0.0, 0.0
    left = clamps(100.0 * start / duration)
    right = clamps(100.0 * end / duration)
    return round(left, 4), round(max(right - left, 0.0), 4)


def names_verdict(pixels):
    for limit, verdict in VERDICT_THRESHOLDS:
        if pixels < limit:
            return verdict
    return COMFORTABLE


@dataclass(frozen=True)
class Precision:
    window_seconds: float
    pixels: str
    verdict: str

    @property
    def places_the_cut(self):
        return self.verdict == COMFORTABLE


@dataclass(frozen=True)
class JudgesZoomPrecision:
    canvas_pixels: int = CANVAS_PIXELS

    def __call__(self, window_seconds):
        if window_seconds <= 0:
            return Precision(window_seconds=window_seconds, pixels="0.0 px", verdict="impossible")
        measured = self.canvas_pixels * PRECISION_SECONDS / window_seconds
        return Precision(
            window_seconds=window_seconds,
            pixels=f"{measured:.1f} px",
            verdict=names_verdict(measured),
        )


@dataclass(frozen=True)
class PeakSource:
    resolution: str
    url: str
    hz: float
    seconds_per_bin: float
    bins: int


@dataclass(frozen=True)
class BandView:
    type: str
    colour: str
    speech: bool
    span: str
    left: float
    width: float


@dataclass(frozen=True)
class SpanView:
    segment_id: int | None
    classification: str
    boundaries: str
    selected: bool
    left: float
    width: float


@dataclass(frozen=True)
class RulerMark:
    elapsed: str
    wall_clock: str
    left: float


@dataclass(frozen=True)
class SpeakerSpan:
    speaker: str
    colour: str
    speech: bool
    left: float
    width: float


@dataclass(frozen=True)
class WordView:
    text: str
    at: str
    at_seconds: float
    left: float


@dataclass(frozen=True)
class EvidenceMarker:
    at: str
    at_seconds: float
    finding: str
    implies: str
    description: str
    left: float


@dataclass(frozen=True)
class ZoomStep:
    step: str
    purpose: str
    window_seconds: float
    precision: str
    verdict: str
    places_the_cut: bool
    words_in_view: str
    selected: bool


@dataclass(frozen=True)
class BoundaryMark:
    boundary: str
    at: str
    at_seconds: float
    left: float
    before: str
    after: str
    window_from: float
    window_to: float
    window_left: float
    window_width: float


@dataclass(frozen=True)
class PlayheadView:
    seconds: float
    left: float
    against: str | None
    offset_seconds: float | None
    offset: str | None


@dataclass(frozen=True)
class CutView:
    left: float
    width: float
    before_width: float
    after_left: float
    after_width: float


@dataclass(frozen=True)
class WindowView:
    step: str
    centre_seconds: float
    seconds: float
    start_seconds: float
    left: float
    width: float


@dataclass(frozen=True)
class WaveformView:
    available: bool
    unavailable_reason: str | None
    spans: str
    duration_seconds: float
    overview: str
    peak_sources: tuple
    bands: tuple
    segment_spans: tuple
    ruler_marks: tuple
    speaker_spans: tuple
    auditioning: str | None
    boundary_marks: tuple
    playhead: PlayheadView
    evidence_markers: tuple
    words: tuple
    zoom_steps: tuple
    window: WindowView | None
    cut: CutView | None


@dataclass(frozen=True)
class ReadsWaveformPeaks:
    store: object

    def __call__(self, recording):
        payload = reads_json(self.store, recording, "waveform_peaks")
        if not payload or not payload.get("measured"):
            return {}
        return payload.get("resolutions") or {}


@dataclass(frozen=True)
class DrawsWaveform:
    store: object
    judges: object = JudgesZoomPrecision()

    def __call__(
        self,
        recording,
        *,
        selected=None,
        transcript=(),
        evidence=(),
        zoom=None,
        centre_seconds=None,
        playhead_seconds=0.0,
        auditioning=None,
        needs_placing=None,
    ):
        duration = recording.duration_seconds or 0.0
        resolutions = ReadsWaveformPeaks(store=self.store)(recording)
        window = self._window(duration, selected, zoom, centre_seconds, needs_placing)
        return WaveformView(
            available=bool(resolutions) and duration > 0,
            unavailable_reason=None if resolutions else "no peak data has been generated",
            spans=formats_clock(duration),
            duration_seconds=duration,
            overview="whole",
            peak_sources=self._sources(recording, resolutions),
            bands=self._bands(recording, duration),
            segment_spans=self._spans(recording, duration, selected),
            ruler_marks=self._ruler(recording, duration),
            speaker_spans=self._speakers(recording, duration),
            auditioning=auditioning if auditioning in BOUNDARIES else None,
            boundary_marks=self._marks(duration, selected),
            playhead=self._playhead(duration, selected, playhead_seconds),
            evidence_markers=self._evidence(evidence, duration),
            words=self._words(transcript, window),
            zoom_steps=self._zooms(duration, window),
            window=window,
            cut=self._cut(duration, selected),
        )

    def _sources(self, recording, resolutions):
        return tuple(
            PeakSource(
                resolution=name,
                url=f"/api/recordings/{recording.recording_id}/peaks?resolution={name}",
                hz=held["hz"],
                seconds_per_bin=held["seconds_per_bin"],
                bins=held["bins"],
            )
            for name, held in sorted(resolutions.items(), key=lambda item: item[1]["hz"])
        )

    def _bands(self, recording, duration):
        bands = []
        for block in sorted(
            self.store.lists(Block, recording_id=recording.recording_id),
            key=lambda item: item.start_seconds,
        ):
            left, width = spans_percent(block.start_seconds, block.end_seconds, duration)
            bands.append(
                BandView(
                    type=block.type,
                    colour=BAND_COLOURS.get(block.type, UNTYPED_COLOUR),
                    speech=block.type not in NON_SPEECH_TYPES,
                    span=(
                        f"{formats_clock(block.start_seconds)} – "
                        f"{formats_clock(block.end_seconds)}"
                    ),
                    left=left,
                    width=width,
                )
            )
        return tuple(bands)

    def _spans(self, recording, duration, selected):
        spans = []
        for segment in sorted(
            self.store.lists(Segment, recording_id=recording.recording_id),
            key=lambda item: item.punch_in_seconds,
        ):
            left, width = spans_percent(
                segment.punch_in_seconds, segment.punch_out_seconds, duration
            )
            spans.append(
                SpanView(
                    segment_id=segment.segment_id,
                    classification=segment.classification,
                    boundaries=(
                        f"{formats_clock(segment.punch_in_seconds)} – "
                        f"{formats_clock(segment.punch_out_seconds)}"
                    ),
                    selected=selected is not None and segment.segment_id == selected.segment_id,
                    left=left,
                    width=width,
                )
            )
        return tuple(spans)

    def _ruler(self, recording, duration):
        if duration <= 0:
            return ()
        step = next(
            (one for one in RULER_STEPS if duration / one <= RULER_MARKS), RULER_STEPS[-1]
        )
        marks = []
        elapsed = 0
        while elapsed <= duration:
            marks.append(
                RulerMark(
                    elapsed=formats_clock(elapsed),
                    wall_clock=formats_wall_clock(recording.started_at, elapsed),
                    left=round(clamps(100.0 * elapsed / duration), 4),
                )
            )
            elapsed += step
        return tuple(marks)

    def _speakers(self, recording, duration):
        turns = (reads_json(self.store, recording, "diarization") or {}).get("turns") or []
        speakers = {}
        spans = []
        for turn in turns:
            speaker = str(turn.get("speaker", "unknown"))
            speakers.setdefault(speaker, len(speakers))
            left, width = spans_percent(turn["start"], turn["end"], duration)
            spans.append(
                SpeakerSpan(
                    speaker=speaker,
                    colour=(
                        NON_SPEECH_SPEAKER_COLOUR
                        if turn.get("speech") is False
                        else SPEAKER_COLOURS[speakers[speaker] % len(SPEAKER_COLOURS)]
                    ),
                    speech=turn.get("speech") is not False,
                    left=left,
                    width=width,
                )
            )
        return tuple(spans)

    def _marks(self, duration, selected):
        if selected is None or duration <= 0:
            return ()
        marks = []
        for boundary, at, before, after in (
            (BOUNDARIES[0], selected.punch_in_seconds, CUT_AWAY, KEPT),
            (BOUNDARIES[1], selected.punch_out_seconds, KEPT, CUT_AWAY),
        ):
            window_from = max(0.0, at - AUDITION_LEAD_SECONDS)
            window_to = min(duration, at + AUDITION_LEAD_SECONDS)
            left, _ = spans_percent(at, at, duration)
            window_left, window_width = spans_percent(window_from, window_to, duration)
            marks.append(
                BoundaryMark(
                    boundary=boundary,
                    at=formats_precise(at),
                    at_seconds=round(at, 2),
                    left=left,
                    before=before,
                    after=after,
                    window_from=round(window_from, 2),
                    window_to=round(window_to, 2),
                    window_left=window_left,
                    window_width=window_width,
                )
            )
        return tuple(marks)

    def _playhead(self, duration, selected, playhead_seconds):
        left, _ = spans_percent(playhead_seconds, playhead_seconds, duration)
        if selected is None:
            return PlayheadView(
                seconds=playhead_seconds, left=left, against=None, offset_seconds=None, offset=None
            )
        boundary, at = min(
            (
                (BOUNDARIES[0], selected.punch_in_seconds),
                (BOUNDARIES[1], selected.punch_out_seconds),
            ),
            key=lambda one: abs(one[1] - playhead_seconds),
        )
        offset = round(playhead_seconds - at, 2)
        return PlayheadView(
            seconds=playhead_seconds,
            left=left,
            against=boundary,
            offset_seconds=offset,
            offset=f"{offset:+.2f} s",
        )

    def _evidence(self, evidence, duration):
        markers = []
        for one in evidence:
            left, _ = spans_percent(one.timecode, one.timecode, duration)
            markers.append(
                EvidenceMarker(
                    at=formats_clock(one.timecode),
                    at_seconds=round(one.timecode, 2),
                    finding=one.finding,
                    implies=one.implies,
                    description=f"{one.finding} — {one.implies}",
                    left=left,
                )
            )
        return tuple(markers)

    def _words(self, transcript, window):
        if window is None:
            return ()
        finish = window.start_seconds + window.seconds
        drawn = []
        for start, end, text, _ in transcript:
            if end < window.start_seconds or start > finish:
                continue
            spoken = text.split()
            for index, word in enumerate(spoken):
                at = start + (end - start) * index / max(len(spoken), 1)
                if not window.start_seconds <= at <= finish:
                    continue
                drawn.append(
                    WordView(
                        text=word,
                        at=formats_clock(at),
                        at_seconds=round(at, 2),
                        left=round(clamps(100.0 * (at - window.start_seconds) / window.seconds), 4),
                    )
                )
        return tuple(drawn[:WORDS_DRAWN])

    def _window(self, duration, selected, zoom, centre_seconds, needs_placing=None):
        if duration <= 0:
            return None
        windows = {step: seconds for step, seconds, _ in ZOOM_STEPS}
        placing = needs_placing in BOUNDARIES and selected is not None
        named = zoom if zoom in windows else (PLACING_ZOOM if placing else DEFAULT_ZOOM)
        seconds = min(windows[named] or duration, duration)
        centre = centre_seconds
        if centre is None and placing:
            centre = (
                selected.punch_in_seconds
                if needs_placing == BOUNDARIES[0]
                else selected.punch_out_seconds
            )
        if centre is None:
            centre = selected.punch_in_seconds if selected is not None else duration / 2
        start = max(0.0, min(centre - seconds / 2, duration - seconds))
        left, width = spans_percent(start, start + seconds, duration)
        return WindowView(
            step=named,
            centre_seconds=round(centre, 2),
            seconds=seconds,
            start_seconds=round(start, 4),
            left=left,
            width=width,
        )

    def _zooms(self, duration, window):
        steps = []
        for step, seconds, purpose in ZOOM_STEPS:
            measured = self.judges(min(seconds or duration, duration) if duration else 0.0)
            steps.append(
                ZoomStep(
                    step=step,
                    purpose=purpose,
                    window_seconds=measured.window_seconds,
                    precision=measured.pixels,
                    verdict=measured.verdict,
                    places_the_cut=measured.places_the_cut,
                    words_in_view=WORDS_IN_VIEW[step],
                    selected=window is not None and window.step == step,
                )
            )
        return tuple(steps)

    def _cut(self, duration, selected):
        if selected is None or duration <= 0:
            return None
        left, width = spans_percent(selected.punch_in_seconds, selected.punch_out_seconds, duration)
        return CutView(
            left=left,
            width=width,
            before_width=left,
            after_left=round(left + width, 4),
            after_width=round(max(100.0 - left - width, 0.0), 4),
        )


def formats_wall_clock(started_at, elapsed_seconds):
    return (started_at + timedelta(seconds=elapsed_seconds)).strftime("%I:%M %p").lstrip("0")
