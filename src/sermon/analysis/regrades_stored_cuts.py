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
class StoredProposal:
    name: str
    recording_id: str
    tag: str
    stored: tuple[tuple[float, float], ...]
    transcript: dict | None
    live: tuple[tuple[float, float], ...] | None

    @property
    def regraded(self):
        return self.live is not None


@dataclass(frozen=True)
class DerivesStoredProposals:
    corpus_root: Path
    derives: object | None = None
    tag: str | None = None

    def __call__(self):
        derives = self.derives or DerivesStoredSegments(data_root=self.corpus_root)
        for path in sorted((Path(self.corpus_root) / "blocks").glob("*.json")):
            found = self._reads(path, derives)
            if found is not None:
                yield found

    def _reads(self, path, derives):
        stored = json.loads(path.read_text())
        recording_id = stored["recording_id"]
        tag = path.name[len(recording_id) + 1 : -len(".json")]
        if self.tag is not None and self.tag not in tag:
            return None
        transcript = (
            Path(self.corpus_root) / "transcripts" / f"{recording_id}.{stored['asr_config']}.json"
        )
        kept = _boundaries(stored.get("segments") or ())
        if not transcript.is_file():
            return StoredProposal(path.name, recording_id, tag, kept, None, None)
        doc = json.loads(transcript.read_text())
        return StoredProposal(
            path.name, recording_id, tag, kept, doc, _boundaries(derives(stored, doc))
        )


def _boundaries(segments):
    return tuple((segment["punch_in"], segment["punch_out"]) for segment in segments)


@dataclass(frozen=True)
class RegradesStoredCuts:
    corpus_root: Path
    derives: object | None = None
    scores: object = ScoresCut
    tag: str | None = None

    def __call__(self):
        return tuple(
            self._regrades(found)
            for found in DerivesStoredProposals(
                corpus_root=self.corpus_root, derives=self.derives, tag=self.tag
            )()
        )

    def _regrades(self, found):
        if not found.regraded:
            return RegradedProposal(
                recording_id=found.recording_id,
                tag=found.tag,
                stored_count=len(found.stored),
                live_count=None,
            )
        scoring = self.scores(transcript=found.transcript)
        return RegradedProposal(
            recording_id=found.recording_id,
            tag=found.tag,
            stored_count=len(found.stored),
            live_count=len(found.live),
            cuts=tuple(
                RegradedCut(
                    recording_id=found.recording_id,
                    tag=found.tag,
                    boundary=boundary,
                    score=scoring(after, before),
                )
                for was, now in zip(found.stored, found.live)
                for boundary, before, after in zip(BOUNDARIES, was, now)
            ),
        )
