"""Who was speaking during each utterance, read off the stored speaker turns."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass


@dataclass(frozen=True)
class AttributesSpeakers:
    """The turn overlapping an utterance most names its speaker, else the transcript's own label."""

    def __call__(self, utterances, turns):
        ordered = sorted(turns, key=lambda turn: turn["start"])
        starts = [turn["start"] for turn in ordered]
        longest = max((turn["end"] - turn["start"] for turn in ordered), default=0.0)
        return tuple(
            self._speaker(utterance, ordered, starts, longest) or utterance.get("speaker")
            for utterance in utterances
        )

    def _speaker(self, utterance, ordered, starts, longest):
        start, end = utterance["start"], utterance["end"]
        best, most = None, 0.0
        for turn in ordered[bisect_left(starts, start - longest) : bisect_left(starts, end)]:
            shared = min(end, turn["end"]) - max(start, turn["start"])
            if shared > most:
                best, most = turn["speaker"], shared
        return best
