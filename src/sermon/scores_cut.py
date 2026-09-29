from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

SILENCE_RUN_SECONDS = 1.0
EDGE_RUN_SECONDS = 1.0
LONG_RUN_SECONDS = 30.0

EQUAL = "equal"
SAME_CUT = "same cut"
IMPROVED = "improved"
DEGRADED = "degraded"

INSIDE_A_RUN = 2
BETWEEN_WORDS = 1
INSIDE_A_WORD = 0


@dataclass(frozen=True)
class SilenceRun:
    index: int
    start: float
    end: float
    overlaps_audio_silence: bool

    @property
    def seconds(self):
        return round(self.end - self.start, 3)

    def holds(self, at):
        return self.start <= at <= self.end


@dataclass(frozen=True)
class CutScore:
    proposed: float
    truth: float
    delta_seconds: float
    proposed_run: SilenceRun | None
    truth_run: SilenceRun | None
    same_run: bool
    speech_seconds: float
    in_speech: bool
    truth_in_speech: bool
    long_run: bool
    overlaps_audio_silence: bool
    verdict: str


@dataclass(frozen=True)
class FindsSilenceRuns:
    gap_seconds: float = SILENCE_RUN_SECONDS
    edge_seconds: float = EDGE_RUN_SECONDS

    def __call__(self, transcript):
        quiet = tuple(
            (float(entry["start"]), float(entry["end"]))
            for entry in transcript.get("silences") or ()
        )
        spoken = _word_intervals(transcript)
        found = []
        for start, end, least in self._quiet_spans(spoken, transcript.get("duration")):
            if end - start < least:
                continue
            found.append(
                SilenceRun(
                    index=len(found),
                    start=start,
                    end=end,
                    overlaps_audio_silence=any(
                        min(end, until) > max(start, since) for since, until in quiet
                    ),
                )
            )
        return tuple(found)

    def _quiet_spans(self, spoken, duration):
        if not spoken:
            return
        yield 0.0, spoken[0][0], self.edge_seconds
        for (_, ends), (starts, _) in zip(spoken, spoken[1:]):
            yield ends, starts, self.gap_seconds
        if duration is not None:
            yield spoken[-1][1], float(duration), self.edge_seconds


@dataclass(frozen=True)
class ScoresCut:
    transcript: dict
    finds_runs: FindsSilenceRuns = FindsSilenceRuns()
    long_run_seconds: float = LONG_RUN_SECONDS

    @cached_property
    def runs(self):
        return self.finds_runs(self.transcript)

    @cached_property
    def speech(self):
        merged = []
        for starts, ends in _word_intervals(self.transcript):
            if merged and starts <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], ends)
            else:
                merged.append([starts, ends])
        return tuple((starts, ends) for starts, ends in merged)

    def run_of(self, at):
        for run in self.runs:
            if run.holds(at):
                return run
        return None

    def speaks_at(self, at):
        return any(starts < at < ends for starts, ends in self.speech)

    def speech_between(self, one, other):
        since, until = min(one, other), max(one, other)
        return round(
            sum(max(0.0, min(until, ends) - max(since, starts)) for starts, ends in self.speech), 3
        )

    def __call__(self, proposed, truth):
        proposed_run, truth_run = self.run_of(proposed), self.run_of(truth)
        in_speech, truth_in_speech = self.speaks_at(proposed), self.speaks_at(truth)
        speech_seconds = self.speech_between(proposed, truth)
        same_run = proposed_run is not None and proposed_run == truth_run
        landed = (proposed_run, truth_run)
        return CutScore(
            proposed=proposed,
            truth=truth,
            delta_seconds=round(proposed - truth, 3),
            proposed_run=proposed_run,
            truth_run=truth_run,
            same_run=same_run,
            speech_seconds=speech_seconds,
            in_speech=in_speech,
            truth_in_speech=truth_in_speech,
            long_run=any(run.seconds > self.long_run_seconds for run in landed if run),
            overlaps_audio_silence=any(run.overlaps_audio_silence for run in landed if run),
            verdict=_decides(
                proposed=proposed,
                truth=truth,
                same_run=same_run,
                speech_seconds=speech_seconds,
                within=self.finds_runs.gap_seconds,
                proposed_placing=_places(proposed_run, in_speech),
                truth_placing=_places(truth_run, truth_in_speech),
            ),
        )


def _word_intervals(transcript):
    spoken = sorted(
        (float(word["start"]), float(word["end"]))
        for utterance in transcript.get("utterances") or ()
        for word in utterance.get("words") or ()
    )
    return tuple(spoken)


def _places(run, in_speech):
    if run is not None:
        return INSIDE_A_RUN
    return INSIDE_A_WORD if in_speech else BETWEEN_WORDS


def _decides(proposed, truth, same_run, speech_seconds, within, proposed_placing, truth_placing):
    if proposed == truth:
        return EQUAL
    shares_a_gap = (
        proposed_placing == truth_placing == BETWEEN_WORDS
        and speech_seconds == 0.0
        and abs(proposed - truth) < within
    )
    if same_run or shares_a_gap:
        return SAME_CUT
    return IMPROVED if proposed_placing > truth_placing else DEGRADED
