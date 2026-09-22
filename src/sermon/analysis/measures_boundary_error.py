from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class BoundaryError:
    recording_id: str
    label: str
    true_punch_in: float
    true_punch_out: float
    punch_in_difficulty: str
    punch_out_difficulty: str
    found: bool
    punch_in: float | None = None
    punch_out: float | None = None
    punch_in_error: float | None = None
    punch_out_error: float | None = None


@dataclass(frozen=True)
class MeasuresBoundaryError:
    ground_truth: Path

    def __call__(self, recording_id, proposed):
        labelled = self._labelled(recording_id)
        if labelled is None:
            return ()
        return tuple(
            self._against(labelled, human, proposed)
            for human in labelled.get("segments", ())
        )

    def _labelled(self, recording_id):
        corpus = json.loads(Path(self.ground_truth).read_text())
        for held in corpus["recordings"]:
            if held.get("recording_id") == recording_id:
                return held
        return None

    def _against(self, labelled, human, proposed):
        measured = BoundaryError(
            recording_id=labelled["recording_id"],
            label=labelled["desktop_label"],
            true_punch_in=human["punch_in"],
            true_punch_out=human["punch_out"],
            punch_in_difficulty=human["difficulty_in"]["label"],
            punch_out_difficulty=human["difficulty_out"]["label"],
            found=False,
        )
        overlapping = _overlapping(proposed, human)
        if overlapping is None:
            return measured
        punch_in, punch_out = overlapping
        return replace(
            measured,
            found=True,
            punch_in=punch_in,
            punch_out=punch_out,
            punch_in_error=round(punch_in - human["punch_in"], 3),
            punch_out_error=round(punch_out - human["punch_out"], 3),
        )


def _overlapping(proposed, human):
    wanted = human["punch_out"] - human["punch_in"]
    best, widest = None, 0.0
    for punch_in, punch_out in proposed:
        shared = min(human["punch_out"], punch_out) - max(human["punch_in"], punch_in)
        if shared > widest:
            best, widest = (punch_in, punch_out), shared
    return best if widest > wanted / 2 else None
