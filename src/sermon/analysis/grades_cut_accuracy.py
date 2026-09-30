from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sermon.analysis.measures_boundary_error import (
    ArchivesRatherThanCuts,
    MeasuresBoundaryError,
)
from sermon.analysis.regrades_stored_cuts import DerivesStoredProposals
from sermon.scores_cut import DEGRADED, EQUAL, IMPROVED, SAME_CUT, CutScore, ScoresCut

BOUNDARIES = ("punch_in", "punch_out")


@dataclass(frozen=True)
class AccuracyOfCut:
    recording_id: str
    label: str
    boundary: str
    human: float
    difficulty: str
    proposed: float | None
    score: CutScore | None

    @property
    def found(self):
        return self.score is not None


@dataclass(frozen=True)
class GradesCutAccuracy:
    """Grade every labelled cut point of one recording, unless it was archived whole.

    A recording the human kept whole carries no cut decision, so it is graded as
    nothing at all rather than as a boundary that happens to sit at zero — the
    same way a recording with no labelled segment is.
    """

    ground_truth: Path
    measures: object | None = None
    archives: object | None = None
    scores: object = ScoresCut

    def __call__(self, recording_id, transcript, proposed):
        archives = self.archives or ArchivesRatherThanCuts(ground_truth=self.ground_truth)
        if archives(recording_id):
            return ()
        measures = self.measures or MeasuresBoundaryError(ground_truth=self.ground_truth)
        scoring = self.scores(transcript=transcript)
        return tuple(
            self._grades(measured, boundary, scoring)
            for measured in measures(recording_id, proposed)
            for boundary in BOUNDARIES
        )

    def _grades(self, measured, boundary, scoring):
        human = getattr(measured, f"true_{boundary}")
        at = getattr(measured, boundary)
        return AccuracyOfCut(
            recording_id=measured.recording_id,
            label=measured.label,
            boundary=boundary,
            human=human,
            difficulty=getattr(measured, f"{boundary}_difficulty"),
            proposed=at,
            score=scoring(at, human) if at is not None else None,
        )


def ranks(cut):
    if cut.score is None:
        return (1, float("inf"))
    return (0 if cut.score.same_run else 1, cut.score.speech_seconds)


def compares(before, after):
    if before.proposed == after.proposed:
        return EQUAL
    if ranks(after) < ranks(before):
        return IMPROVED
    if ranks(after) > ranks(before):
        return DEGRADED
    return SAME_CUT


@dataclass(frozen=True)
class GradedProposal:
    recording_id: str
    tag: str
    cuts: tuple[AccuracyOfCut, ...]
    was: tuple[AccuracyOfCut, ...] = ()

    @property
    def changes(self):
        return tuple(
            (before, after, compares(before, after)) for before, after in zip(self.was, self.cuts)
        )


@dataclass(frozen=True)
class GradesCorpusAccuracy:
    corpus_root: Path
    ground_truth: Path | None = None
    derives: object | None = None
    grades: object | None = None
    before: dict | None = None
    tag: str | None = None

    def __call__(self):
        grades = self.grades or GradesCutAccuracy(
            ground_truth=self.ground_truth or Path(self.corpus_root) / "groundtruth.json"
        )
        graded = []
        for found in DerivesStoredProposals(
            corpus_root=self.corpus_root, derives=self.derives, tag=self.tag
        )():
            if not found.regraded:
                continue
            cuts = grades(found.recording_id, found.transcript, found.live)
            if not cuts:
                continue
            graded.append(
                GradedProposal(
                    recording_id=found.recording_id,
                    tag=found.tag,
                    cuts=cuts,
                    was=self._baseline(grades, found),
                )
            )
        return tuple(graded)

    def _baseline(self, grades, found):
        if self.before is None or found.name not in self.before:
            return ()
        return grades(found.recording_id, found.transcript, self.before[found.name])
