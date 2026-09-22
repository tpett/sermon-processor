from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ASR_CONFIG = "whisper-large-v3-turbo+words"


@dataclass(frozen=True)
class ChoosesBoundaries:
    model_segments: object = ()

    def __call__(self, blocks, doc):
        raise NotImplementedError


@dataclass(frozen=True)
class ProposesFromStoredTranscript:
    store: object
    corpus_root: Path
    prompts_root: Path
    model: str = ""
    summarizer: str | None = None
    asr_config: str = ASR_CONFIG
    reasons: object = None

    def __call__(self, recording):
        raise NotImplementedError
