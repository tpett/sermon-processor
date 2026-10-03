"""Production's analyze job, run over a stored transcript and a stored model answer.

The job is built the way `sermon-work` builds it with no corpus named: the same
`RunsAnalyzeJob`, the same stage walk, the pipeline roots bound to an empty
`corpus/` the way `works` lays one out. Only the model's block table is given
rather than asked for, at the walk's own `divides` seam. Stages that need audio
or a model are refused before they start, and only stages the walk already
carries on without.
"""

from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sermon.analysis.io import writes_json
from sermon.analysis.proposes_from_transcript import BindsCorpusRoots
from sermon.jobs import analyzes_recording
from sermon.pipeline import classify, segments
from sermon.sends_notification import SendsNotification
from sermon.store import Job, Recording, Segment, layout, opens_store

SKIPPED_IN_REPLAY = frozenset({"waveform", "preview", "diarization", "summarization"})


class ReplayFailed(RuntimeError):
    pass


class NotReplayed(RuntimeError):
    pass


@dataclass(frozen=True)
class ProposedCut:
    classification: str
    punch_in: float
    punch_out: float


@dataclass(frozen=True)
class ReplayedProposals:
    name: str
    recording_id: str
    tag: str
    proposals: tuple[ProposedCut, ...]


def refuses_what_needs_audio_or_a_model(name):
    if name in SKIPPED_IN_REPLAY:
        raise NotReplayed(f"{name} needs audio or a model and is not replayed")


@contextmanager
def bound_like_production(data_root):
    held = (segments.DATA_ROOT, classify.DATA, classify.PROMPTS, classify.ENDPOINT)
    layout.diarization_root(data_root).mkdir(parents=True, exist_ok=True)
    BindsCorpusRoots(
        corpus_root=layout.corpus_root(data_root), prompts_root=data_root / "prompts"
    )()
    classify.ENDPOINT = None
    segments._EDGE_CACHE.clear()
    try:
        yield
    finally:
        segments._EDGE_CACHE.clear()
        segments.DATA_ROOT, classify.DATA, classify.PROMPTS, classify.ENDPOINT = held


@dataclass(frozen=True)
class ReplaysShippingWalk:
    corpus_root: Path

    def __call__(self, block_path):
        block_path = Path(block_path)
        stored = json.loads(block_path.read_text())
        recording_id = stored["recording_id"]
        tag = block_path.name[len(recording_id) + 1 : -len(".json")]
        transcript = (
            Path(self.corpus_root) / "transcripts" / f"{recording_id}.{stored['asr_config']}.json"
        )
        if not transcript.is_file():
            return None
        doc = json.loads(transcript.read_text())
        answer = {"blocks": stored["blocks"], "model_segments": stored.get("model_segments") or []}
        with tempfile.TemporaryDirectory() as scratch:
            proposals = self._walks(Path(scratch), recording_id, doc, answer)
        return ReplayedProposals(block_path.name, recording_id, tag, proposals)

    def _walks(self, data_root, recording_id, doc, answer):
        store = opens_store(data_root)
        try:
            with bound_like_production(data_root):
                recording = store.saves(
                    Recording(
                        recording_id=recording_id,
                        object_key=f"{recording_id}.flac",
                        state="downloaded",
                        started_at=datetime.fromisoformat(doc["started_at"]).replace(tzinfo=UTC),
                        started_at_source="key",
                        size_bytes=1,
                        duration_seconds=float(doc["duration"]),
                    )
                )
                writes_json(store, recording, "transcript", doc)
                store.saves(
                    Job(
                        recording_id=recording_id,
                        kind="analyze",
                        state="queued",
                        max_attempts=1,
                        dedupe_key=f"analyze:{recording_id}",
                        queued_at=datetime.now(UTC),
                    )
                )
                analyzes_recording.RunsAnalyzeJob(
                    store=store,
                    stages=refuses_what_needs_audio_or_a_model,
                    notifies=SendsNotification(store=store, sends=lambda _message: None),
                    divides=lambda _doc: answer,
                    recording_id=recording_id,
                )()
            job = store.lists(Job, recording_id=recording_id)[-1]
            if job.state != "succeeded":
                raise ReplayFailed(f"{recording_id}: the analyze job {job.state}: {job.last_error}")
            return tuple(
                ProposedCut(item.classification, item.punch_in_seconds, item.punch_out_seconds)
                for item in sorted(
                    store.lists(Segment, recording_id=recording_id),
                    key=lambda item: item.punch_in_seconds,
                )
            )
        finally:
            store.close()
