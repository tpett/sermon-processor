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


class CorpusFileAlreadyWritten(FileExistsError):
    pass


class BlockFileAlreadyWritten(CorpusFileAlreadyWritten):
    pass


class FrozenCorpus(PermissionError):
    pass


class NothingToBlock(ValueError):
    pass


HELD_OUT_LOG = "test_access.log"


def records_held_out_runs(directory):
    return (directory / HELD_OUT_LOG).is_file() or (directory / "data" / HELD_OUT_LOG).is_file()


def refuses_a_frozen_corpus(corpus_root):
    resolved = Path(corpus_root).resolve()
    if any(records_held_out_runs(directory) for directory in (resolved, *resolved.parents)):
        raise FrozenCorpus(
            f"{corpus_root} is inside the tree that records held-out runs in {HELD_OUT_LOG}; "
            "it is frozen and never written"
        )


def creates(path, text, created):
    with path.open("x", encoding="utf-8") as written:
        created.append(path)
        written.write(text)


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
        refuses_a_frozen_corpus(self.corpus_root)
        recording, doc = self._stored_transcript(recording_id)
        turns = reads_json(self.store, recording, "diarization")
        transcript = self._root / "transcripts" / f"{recording_id}.{self.asr_config}.json"
        diarization = self._root / "diarization" / f"{recording_id}.json"
        recorded = self._root / "blocks" / f"{recording_id}.{self.tag}.json"
        if recorded.exists():
            raise BlockFileAlreadyWritten(f"{recorded} already records a classifier answer")
        writes = [transcript, recorded] + ([diarization] if turns is not None else [])
        held = [path for path in writes if path.exists()]
        if held:
            raise CorpusFileAlreadyWritten(
                f"{', '.join(str(path) for path in held)} already exists and is never overwritten"
            )
        for name in CORPUS_DIRECTORIES:
            (self._root / name).mkdir(parents=True, exist_ok=True)
        created = []
        try:
            creates(transcript, json.dumps(doc), created)
            if turns is not None:
                creates(diarization, json.dumps(turns), created)
            chosen = self._records(recording_id, doc, recorded, created)
        except BaseException:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        return CorpusEntry(transcript=transcript, blocks=recorded, chosen=tuple(chosen))

    @property
    def _root(self):
        return Path(self.corpus_root)

    def _records(self, recording_id, doc, recorded, created):
        BindsCorpusRoots(corpus_root=self.corpus_root, prompts_root=self.prompts_root)()
        answer = (self.reasons or ReasonsOverTranscript())(doc)
        blocks = list(answer.get("blocks") or ())
        if not blocks:
            raise NothingToBlock(f"the classifier found no blocks in {recording_id}")
        model_segments = list(answer.get("model_segments") or ())
        chosen = self._chooses(blocks, model_segments, doc)
        creates(
            recorded,
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
            created,
        )
        return chosen

    def _chooses(self, blocks, model_segments, doc):
        segments.DATA_ROOT = Path(self.corpus_root)
        segments._EDGE_CACHE.clear()
        return segments.choose(model_segments, segments.derive(blocks, doc), doc)

    def _stored_transcript(self, recording_id):
        recording = self.store.loads(Recording, recording_id)
        doc = None if recording is None else reads_json(self.store, recording, "transcript")
        if doc is None:
            raise TranscriptNotStored(f"no transcript is stored for {recording_id}")
        return recording, doc
