"""The fixed yardstick the shipping gate measures a proposal against the human cut with.

Everything that decides whether a proposal is closer to or further from the human
lives here and nowhere else, and the gate prints this file's digest, so changing
how cuts are judged is a visible act rather than a side effect of a pipeline change.

A pause is a gap of at least a second between words, or the quiet before the first
word or after the last. A proposal in the human's pause is the human's cut. Any other
proposal is as far from it as the speech between them. Clearance from the nearest
word and landing inside a word are reported, and rank nothing.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

JUDGE_VERSION = 1
SILENCE_RUN_SECONDS = 1.0
TOLERANCE_SPEECH_SECONDS = 0.1
ARCHIVED_WHOLE_COVERAGE = 0.95

BETTER = "better"
WORSE = "worse"
UNCHANGED = "unchanged"

IN_THE_HUMANS_PAUSE = 0
ELSEWHERE = 1
MISSED = 2


def digest_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


JUDGE_DIGEST = digest_of(__file__)


@dataclass(frozen=True)
class Judgement:
    proposed: float | None
    human: float
    same_pause: bool
    speech_seconds: float
    inside_word: bool
    clearance_seconds: float | None

    @property
    def missed(self):
        return self.proposed is None

    @property
    def seconds_from_human(self):
        return None if self.missed else round(self.proposed - self.human, 3)

    @property
    def tier(self):
        if self.missed:
            return MISSED
        return IN_THE_HUMANS_PAUSE if self.same_pause else ELSEWHERE


@dataclass(frozen=True)
class JudgesCut:
    transcript: dict

    @cached_property
    def speech(self):
        merged = []
        for starts, ends in sorted(
            (float(word["start"]), float(word["end"]))
            for utterance in self.transcript.get("utterances") or ()
            for word in utterance.get("words") or ()
        ):
            if merged and starts <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], ends)
            else:
                merged.append([starts, ends])
        return tuple((starts, ends) for starts, ends in merged)

    @cached_property
    def pauses(self):
        if not self.speech:
            return ()
        found = [(-math.inf, self.speech[0][0])]
        found += [
            (ends, starts)
            for (_, ends), (starts, _) in zip(self.speech, self.speech[1:])
            if starts - ends >= SILENCE_RUN_SECONDS
        ]
        found.append((self.speech[-1][1], math.inf))
        return tuple(found)

    def pause_of(self, at):
        return next((pause for pause in self.pauses if pause[0] <= at <= pause[1]), None)

    def speech_between(self, one, other):
        since, until = min(one, other), max(one, other)
        return round(
            sum(max(0.0, min(until, ends) - max(since, starts)) for starts, ends in self.speech),
            3,
        )

    def speaks_at(self, at):
        return any(starts < at < ends for starts, ends in self.speech)

    def clearance(self, at):
        if self.speaks_at(at):
            return 0.0
        return round(
            min((min(abs(at - starts), abs(at - ends)) for starts, ends in self.speech),
                default=math.inf),
            3,
        )

    def __call__(self, proposed, human):
        if proposed is None:
            return Judgement(None, human, False, math.inf, False, None)
        landed = self.pause_of(proposed)
        return Judgement(
            proposed=proposed,
            human=human,
            same_pause=landed is not None and landed == self.pause_of(human),
            speech_seconds=self.speech_between(proposed, human),
            inside_word=self.speaks_at(proposed),
            clearance_seconds=self.clearance(proposed),
        )


def compares(before, after):
    if before.proposed == after.proposed:
        return UNCHANGED
    if before.tier != after.tier:
        return BETTER if after.tier < before.tier else WORSE
    if before.tier != ELSEWHERE:
        return UNCHANGED
    moved = after.speech_seconds - before.speech_seconds
    if abs(moved) <= TOLERANCE_SPEECH_SECONDS:
        return UNCHANGED
    return BETTER if moved < 0 else WORSE


def pairs(proposed, human):
    wanted = human["punch_out"] - human["punch_in"]
    best, widest = None, 0.0
    for punch_in, punch_out in proposed:
        shared = min(human["punch_out"], punch_out) - max(human["punch_in"], punch_in)
        if shared > widest:
            best, widest = (punch_in, punch_out), shared
    return best if widest > wanted / 2 else None


def archived_whole(labelled):
    source = float(labelled.get("source_duration") or 0.0)
    kept = sum(held["punch_out"] - held["punch_in"] for held in labelled.get("segments") or ())
    return source > 0.0 and kept / source > ARCHIVED_WHOLE_COVERAGE
