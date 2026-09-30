from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from sermon.pipeline import audio
from sermon.pipeline.render import probe_format

COARSE_HZ = 100
FINE_HZ = 1_000
PROBE_SECONDS = 60.0
PROBE_AT = (0.10, 0.30, 0.50, 0.70, 0.90)
FINE_SEARCH_SECONDS = 4.0

MIN_COARSE_NCC = 0.30
MIN_COARSE_PEAK_RATIO = 1.5
MIN_PROBE_NCC = 0.30
USABLE_PROBES = 2
FITTABLE_PROBES = 3
MAX_FIT_RESIDUAL_SECONDS = 0.06
MAX_DRIFT_PPM = 400.0
NEGATIVE_OFFSET_SLACK_SECONDS = 0.05
PAST_THE_END_SLACK_SECONDS = 1.0
LAST_FRAME_SECONDS = 0.01
HEAD_WINDOW_SECONDS = 180.0
SPANNABLE_SOURCES = 2

ALIGNED = "aligned"
UNALIGNABLE = "cannot be aligned"
DISCONTINUOUS = "not a contiguous excerpt"

EASY = "easy"
MODERATE = "moderate"
HARD = "hard"
EASY_QUIET_MILLISECONDS = 2_000
MODERATE_QUIET_MILLISECONDS = 250


@dataclass(frozen=True, kw_only=True)
class Probe:
    at_seconds: float
    offset_seconds: float
    ncc: float
    peak_ratio: float | None


@dataclass(frozen=True, kw_only=True)
class Alignment:
    verdict: str
    refusals: tuple[str, ...] = ()
    probes: tuple[Probe, ...] = ()
    punch_in_seconds: float | None = None
    coarse_offset_seconds: float | None = None
    coarse_ncc: float | None = None
    coarse_peak_ratio: float | None = None
    drift_ppm: float | None = None
    fit_residual_seconds: float | None = None
    probe_ncc_min: float | None = None

    @property
    def trustworthy(self) -> bool:
        return self.verdict == ALIGNED


@dataclass(frozen=True, kw_only=True)
class CutDifficulty:
    label: str
    quiet_milliseconds: int


@dataclass(frozen=True)
class ReadsEnvelopes:
    """Coarse and fine envelopes of one file, decoding it once."""

    work: Path
    coarse_hz: int = COARSE_HZ
    fine_hz: int = FINE_HZ

    def __call__(self, source: Path, tag: str) -> tuple[np.ndarray, np.ndarray]:
        coarse = audio.cached_envelope(source, self.work, self.coarse_hz, tag)
        fine = audio.cached_envelope(source, self.work, self.fine_hz, tag)
        (self.work / "raw" / f"{tag}.raw").unlink(missing_ok=True)
        return coarse, fine


@dataclass(frozen=True)
class GradesCutDifficulty:
    hz: int = COARSE_HZ

    def __call__(self, source_coarse, at_seconds) -> CutDifficulty:
        quiet, _ = audio.quiet_mask(source_coarse)
        frame = max(0, min(int(round(at_seconds * self.hz)), len(quiet) - 1))
        if not quiet[frame]:
            return CutDifficulty(label=HARD, quiet_milliseconds=0)
        first = frame
        while first > 0 and quiet[first - 1]:
            first -= 1
        last = frame
        while last < len(quiet) - 1 and quiet[last + 1]:
            last += 1
        milliseconds = (last - first + 1) * (1_000 // self.hz)
        return CutDifficulty(
            label=self.grade(milliseconds), quiet_milliseconds=int(milliseconds)
        )

    def grade(self, milliseconds):
        if milliseconds >= EASY_QUIET_MILLISECONDS:
            return EASY
        return MODERATE if milliseconds >= MODERATE_QUIET_MILLISECONDS else HARD


@dataclass(frozen=True)
class LocatesEditInSource:
    """Fits a line through independently aligned probes.

    The intercept is the punch-in and the slope is the clock difference; the
    residual separates correctable drift from material cut out of the middle.
    """

    coarse_hz: int = COARSE_HZ
    fine_hz: int = FINE_HZ
    probe_seconds: float = PROBE_SECONDS
    probe_at: tuple[float, ...] = PROBE_AT
    search_seconds: float = FINE_SEARCH_SECONDS

    def __call__(self, *, source_coarse, source_fine, edit_coarse, edit_fine) -> Alignment:
        if len(edit_coarse) > len(source_coarse):
            return Alignment(
                verdict=UNALIGNABLE, refusals=("the edit is longer than the source",)
            )

        refusals = []
        coarse = self.roughly(source_coarse, edit_coarse)
        if coarse.coarse_ncc < MIN_COARSE_NCC:
            refusals.append(f"coarse NCC {coarse.coarse_ncc:.3f} below {MIN_COARSE_NCC}")
        if coarse.coarse_peak_ratio is not None and coarse.coarse_peak_ratio < MIN_COARSE_PEAK_RATIO:
            refusals.append(
                f"coarse peak ratio {coarse.coarse_peak_ratio:.2f} below {MIN_COARSE_PEAK_RATIO}"
            )

        probes = self.probed(source_fine, edit_fine, coarse.coarse_offset_seconds)
        usable = tuple(probe for probe in probes if probe.ncc >= MIN_PROBE_NCC)
        if len(usable) < USABLE_PROBES:
            return Alignment(
                verdict=UNALIGNABLE,
                probes=probes,
                refusals=tuple(refusals + [f"only {len(usable)} usable probes"]),
                **coarse.measured,
            )

        fitted = self.fitted(usable)
        discontinuous = fitted.fit_residual_seconds > MAX_FIT_RESIDUAL_SECONDS
        if discontinuous:
            refusals.append(
                f"probes deviate {fitted.fit_residual_seconds:.3f} s from a straight line"
            )
        if abs(fitted.drift_ppm) > MAX_DRIFT_PPM:
            refusals.append(f"clock drift {fitted.drift_ppm:.0f} ppm is implausible")
        offset = fitted.punch_in_seconds
        if -NEGATIVE_OFFSET_SLACK_SECONDS <= offset < 0:
            offset = 0.0
        elif offset < 0:
            refusals.append(f"offset {offset:.3f} s is before the start of the source")

        aligned = not refusals
        return Alignment(
            verdict=self.verdict(refusals, discontinuous),
            refusals=tuple(refusals),
            probes=probes,
            punch_in_seconds=round(offset, 4) if aligned else None,
            drift_ppm=fitted.drift_ppm if aligned else None,
            fit_residual_seconds=fitted.fit_residual_seconds,
            probe_ncc_min=min(probe.ncc for probe in usable),
            **coarse.measured,
        )

    def verdict(self, refusals, discontinuous):
        if not refusals:
            return ALIGNED
        return DISCONTINUOUS if discontinuous else UNALIGNABLE

    def roughly(self, source_coarse, edit_coarse):
        correlation = audio.ncc(source_coarse, edit_coarse)
        index, best, ratio = audio.peak_and_ratio(correlation, guard=self.coarse_hz * 5)
        return RoughOffset(
            coarse_offset_seconds=round(index / self.coarse_hz, 3),
            coarse_ncc=round(best, 4),
            coarse_peak_ratio=round(ratio, 2) if np.isfinite(ratio) else None,
        )

    def probed(self, source_fine, edit_fine, coarse_offset):
        edit_seconds = len(edit_fine) / self.fine_hz
        search = int(self.search_seconds * self.fine_hz)
        window = int(self.probe_seconds * self.fine_hz)
        found = []
        for fraction in self.probe_at:
            at = max(0.0, min(fraction * edit_seconds, edit_seconds - self.probe_seconds))
            first = int(at * self.fine_hz)
            if first + window > len(edit_fine):
                continue
            short = edit_fine[first : first + window]
            centre = int((coarse_offset + at) * self.fine_hz)
            low = max(0, centre - search)
            high = min(len(source_fine), centre + search + window)
            if high - low < window:
                continue
            index, best, ratio = audio.peak_and_ratio(
                audio.ncc(source_fine[low:high], short), guard=self.fine_hz // 2
            )
            found.append(
                Probe(
                    at_seconds=round(at, 1),
                    offset_seconds=round((low + index) / self.fine_hz - at, 4),
                    ncc=round(best, 4),
                    peak_ratio=round(ratio, 2) if np.isfinite(ratio) else None,
                )
            )
        return tuple(found)

    def fitted(self, usable):
        at = np.array([probe.at_seconds for probe in usable], dtype=float)
        offsets = np.array([probe.offset_seconds for probe in usable], dtype=float)
        if len(usable) >= FITTABLE_PROBES:
            slope, intercept = np.polyfit(at, offsets, 1)
            residual = float(np.max(np.abs(offsets - (intercept + slope * at))))
        else:
            slope, intercept, residual = 0.0, float(np.median(offsets)), 0.0
        return StraightLine(
            punch_in_seconds=float(intercept),
            drift_ppm=round(float(slope) * 1e6, 1),
            fit_residual_seconds=round(residual, 4),
        )


@dataclass(frozen=True, kw_only=True)
class RoughOffset:
    coarse_offset_seconds: float
    coarse_ncc: float
    coarse_peak_ratio: float | None

    @property
    def measured(self):
        return {
            "coarse_offset_seconds": self.coarse_offset_seconds,
            "coarse_ncc": self.coarse_ncc,
            "coarse_peak_ratio": self.coarse_peak_ratio,
        }


@dataclass(frozen=True, kw_only=True)
class StraightLine:
    punch_in_seconds: float
    drift_ppm: float
    fit_residual_seconds: float


@dataclass(frozen=True, kw_only=True)
class DerivedPair:
    recording_id: str
    alignment: Alignment
    source_duration_seconds: float
    edit_duration_seconds: float
    punch_in_seconds: float | None = None
    punch_out_seconds: float | None = None
    punch_in_difficulty: CutDifficulty | None = None
    punch_out_difficulty: CutDifficulty | None = None

    @property
    def trustworthy(self) -> bool:
        return self.alignment.trustworthy and self.punch_in_seconds is not None

    @property
    def refusals(self) -> tuple[str, ...]:
        return self.alignment.refusals


def reads_duration(path):
    return probe_format(Path(path))["duration"]


@dataclass(frozen=True)
class AlignsPublishedEdit:
    """One published edit against one source, gated and graded."""

    work: Path
    reads: object | None = None
    locates: object = LocatesEditInSource()
    grades: object = GradesCutDifficulty()
    measures: object = reads_duration

    def __call__(self, recording_id, source: Path, edit: Path, window=None) -> DerivedPair:
        reads = self.reads or ReadsEnvelopes(work=self.work)
        source_coarse, source_fine = reads(Path(source), f"{recording_id}.source")
        edit_coarse, edit_fine = reads(Path(edit), f"{recording_id}.{Path(edit).stem}")
        first, last = self.framed(window, len(edit_coarse), len(edit_fine))
        found = self.locates(
            source_coarse=source_coarse,
            source_fine=source_fine,
            edit_coarse=edit_coarse[first[0]:last[0]],
            edit_fine=edit_fine[first[1]:last[1]],
        )
        source_seconds = self.measures(source)
        edit_seconds = self.measures(edit) if window is None else window[1] - window[0]
        return self.paired(recording_id, found, source_coarse, source_seconds, edit_seconds)

    def framed(self, window, coarse_frames, fine_frames):
        if window is None:
            return (0, 0), (coarse_frames, fine_frames)
        start, end = window
        return (
            (int(start * COARSE_HZ), int(start * FINE_HZ)),
            (min(coarse_frames, int(end * COARSE_HZ)), min(fine_frames, int(end * FINE_HZ))),
        )

    def paired(self, recording_id, found, source_coarse, source_seconds, edit_seconds):
        measured = dict(
            recording_id=recording_id,
            source_duration_seconds=source_seconds,
            edit_duration_seconds=edit_seconds,
        )
        if not found.trustworthy:
            return DerivedPair(alignment=found, **measured)
        punch_in = found.punch_in_seconds
        punch_out = round(punch_in + edit_seconds * (1 + found.drift_ppm / 1e6), 4)
        if punch_out > source_seconds + PAST_THE_END_SLACK_SECONDS:
            return DerivedPair(alignment=self.past_the_end(found), **measured)
        return DerivedPair(
            alignment=found,
            punch_in_seconds=punch_in,
            punch_out_seconds=punch_out,
            punch_in_difficulty=self.grades(source_coarse, punch_in),
            punch_out_difficulty=self.grades(
                source_coarse, min(punch_out, source_seconds - LAST_FRAME_SECONDS)
            ),
            **measured,
        )

    def past_the_end(self, found):
        return replace(
            found,
            verdict=UNALIGNABLE,
            refusals=found.refusals + ("the edit runs past the end of the source",),
        )


def refuses(recording_id, reason, source_seconds=0.0, edit_seconds=0.0) -> DerivedPair:
    return DerivedPair(
        recording_id=recording_id,
        alignment=Alignment(verdict=UNALIGNABLE, refusals=(reason,)),
        source_duration_seconds=source_seconds,
        edit_duration_seconds=edit_seconds,
    )


@dataclass(frozen=True)
class DerivesPairsForEdit:
    """One pair per source: an edit spanning two recordings is two rows, never one."""

    aligns: object
    measures: object = reads_duration
    head_seconds: float = HEAD_WINDOW_SECONDS

    def __call__(self, named, edit) -> tuple[DerivedPair, ...]:
        if len(named) == 1:
            recording_id, source = named[0]
            return (self.aligns(recording_id, source, edit),)
        if len(named) > SPANNABLE_SOURCES:
            return tuple(
                refuses(recording_id, f"an edit spanning {len(named)} sources is not derived")
                for recording_id, _ in named
            )
        return self.spanned(named, edit)

    def spanned(self, named, edit):
        (first_id, first_source), (second_id, second_source) = named
        edit_seconds = self.measures(edit)
        head = self.aligns(
            first_id, first_source, edit, window=(0.0, min(self.head_seconds, edit_seconds))
        )
        if not head.trustworthy:
            return (head, refuses(second_id, f"the head of the edit did not place in {first_id}"))
        split = round(head.source_duration_seconds - head.punch_in_seconds, 4)
        if not 0.0 < split < edit_seconds:
            return (
                refuses(
                    first_id,
                    f"the edit does not run to the end of {first_id}, "
                    f"so it does not continue into another source",
                    head.source_duration_seconds,
                    edit_seconds,
                ),
                refuses(second_id, f"nothing of the edit is left for {second_id}"),
            )
        return (
            self.aligns(first_id, first_source, edit, window=(0.0, split)),
            self.aligns(second_id, second_source, edit, window=(split, edit_seconds)),
        )
