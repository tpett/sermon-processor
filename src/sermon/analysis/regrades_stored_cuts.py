from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sermon.pipeline import segments
from sermon.scores_cut import DEGRADED, CutScore, ScoresCut

BOUNDARIES = ("punch_in", "punch_out")


@dataclass(frozen=True)
class RegradedCut:
    recording_id: str
    tag: str
    boundary: str
    score: CutScore


@dataclass(frozen=True)
class RegradedProposal:
    recording_id: str
    tag: str
    stored_count: int
    live_count: int | None
    cuts: tuple[RegradedCut, ...] = ()

    @property
    def regraded(self):
        return self.live_count is not None

    @property
    def drifted(self):
        return any(cut.score.delta_seconds != 0.0 for cut in self.cuts)

    @property
    def degraded(self):
        return self.regraded and (
            self.stored_count != self.live_count
            or any(cut.score.verdict == DEGRADED for cut in self.cuts)
        )


@dataclass(frozen=True)
class DerivesStoredSegments:
    data_root: Path

    def __call__(self, stored, doc):
        segments.DATA_ROOT = Path(self.data_root)
        segments._EDGE_CACHE.clear()
        derived = segments.derive(stored["blocks"], doc)
        return segments.choose(stored.get("model_segments") or [], derived, doc)


@dataclass(frozen=True)
class RegradesStoredCuts:
    corpus_root: Path
    derives: object | None = None
    scores: object = ScoresCut

    def __call__(self):
        derives = self.derives or DerivesStoredSegments(data_root=self.corpus_root)
        return tuple(self._regrades(path, derives) for path in sorted(self._stored_blocks()))

    def _stored_blocks(self):
        return (Path(self.corpus_root) / "blocks").glob("*.json")

    def _regrades(self, path, derives):
        stored = json.loads(path.read_text())
        recording_id = stored["recording_id"]
        tag = path.name[len(recording_id) + 1 : -len(".json")]
        transcript = (
            Path(self.corpus_root) / "transcripts" / f"{recording_id}.{stored['asr_config']}.json"
        )
        kept = stored.get("segments") or []
        if not transcript.is_file():
            return RegradedProposal(
                recording_id=recording_id, tag=tag, stored_count=len(kept), live_count=None
            )
        doc = json.loads(transcript.read_text())
        live = derives(stored, doc)
        scoring = self.scores(transcript=doc)
        return RegradedProposal(
            recording_id=recording_id,
            tag=tag,
            stored_count=len(kept),
            live_count=len(live),
            cuts=tuple(
                RegradedCut(
                    recording_id=recording_id,
                    tag=tag,
                    boundary=boundary,
                    score=scoring(proposed[boundary], expected[boundary]),
                )
                for expected, proposed in zip(kept, live)
                for boundary in BOUNDARIES
            ),
        )
