from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sermon.analysis.io import reads_json
from sermon.analysis.proposes_from_transcript import (
    ASR_CONFIG,
    BindsCorpusRoots,
    ReasonsOverTranscript,
    TranscriptNotStored,
)
from sermon.pipeline import segments
from sermon.store import Recording, Store

DEFAULT_TAG = "stored.whole.v2"
CORPUS_DIRECTORIES = ("blocks", "transcripts", "diarization")


class BlockFileAlreadyWritten(FileExistsError):
    pass


class NothingToBlock(ValueError):
    pass


@dataclass(frozen=True)
class CorpusEntry:
    transcript: Path
    blocks: Path
    chosen: tuple[dict, ...]


@dataclass(frozen=True)
class DerivesCorpusEntry:
    """Derive one gradeable corpus entry from a Recording's stored transcript.

    The classifier answers differently for byte-identical input, and the store
    keeps no part of its answer but the Blocks it was turned into — not the
    model's own segment boundaries, which `choose` prefers at the punch-in. So a
    graded population has to be the frozen answer, written beside the transcript.
    """

    store: Store
    corpus_root: Path
    prompts_root: Path
    asr_config: str = ASR_CONFIG
    tag: str = DEFAULT_TAG
    reasons: object = None

    def __call__(self, recording_id):
        recording, doc = self._stored_transcript(recording_id)
        recorded = self._destination(recording_id)
        if recorded.is_file():
            raise BlockFileAlreadyWritten(f"{recorded} already records a classifier answer")
        transcript = self._writes_transcript(recording_id, doc)
        self._writes_diarization(recording)
        BindsCorpusRoots(corpus_root=self.corpus_root, prompts_root=self.prompts_root)()
        answer = (self.reasons or ReasonsOverTranscript())(doc)
        blocks = list(answer.get("blocks") or ())
        if not blocks:
            raise NothingToBlock(f"the classifier found no blocks in {recording_id}")
        model_segments = list(answer.get("model_segments") or ())
        chosen = self._chooses(blocks, model_segments, doc)
        recorded.write_text(
            json.dumps(
                {
                    "recording_id": recording_id,
                    "asr_config": self.asr_config,
                    "config_id": self.tag,
                    "blocks": blocks,
                    "model_segments": model_segments,
                    "segments": chosen,
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        return CorpusEntry(transcript=transcript, blocks=recorded, chosen=tuple(chosen))

    def _chooses(self, blocks, model_segments, doc):
        segments._EDGE_CACHE.clear()
        return segments.choose(model_segments, segments.derive(blocks, doc), doc)

    def _stored_transcript(self, recording_id):
        recording = self.store.loads(Recording, recording_id)
        doc = None if recording is None else reads_json(self.store, recording, "transcript")
        if doc is None:
            raise TranscriptNotStored(f"no transcript is stored for {recording_id}")
        return recording, doc

    def _destination(self, recording_id):
        for name in CORPUS_DIRECTORIES:
            (Path(self.corpus_root) / name).mkdir(parents=True, exist_ok=True)
        return Path(self.corpus_root) / "blocks" / f"{recording_id}.{self.tag}.json"

    def _writes_transcript(self, recording_id, doc):
        path = (
            Path(self.corpus_root) / "transcripts" / f"{recording_id}.{self.asr_config}.json"
        )
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def _writes_diarization(self, recording):
        turns = reads_json(self.store, recording, "diarization")
        if turns is None:
            return None
        path = Path(self.corpus_root) / "diarization" / f"{recording.recording_id}.json"
        path.write_text(json.dumps(turns), encoding="utf-8")
        return path
