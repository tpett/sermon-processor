"""Who speaks when, computed on this machine from the Recording's own audio.

features/analysis/speaker_diarization.feature. The turns are evidence of who is
speaking, not a source of boundaries. The engine and its settings are the spike's
`experiments/src/diarize.py`, unchanged.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from sermon.analysis.provisions_diarization_models import EMBEDDING, SEGMENTATION
from sermon.analysis.transcribes_audio import DecodesChannelOne, TranscriptionUnavailable

MODELS_SETTING = "SERMON_DIARIZATION_MODELS"
MERGE_THRESHOLD = 0.9
MIN_TURN_S = 1.0
MIN_GAP_S = 0.5
THREADS = 8


class DiarizationUnavailable(RuntimeError):
    """No speaker turns could be produced. Analysis carries on without them."""


def builds_sherpa_diarizer(models, threshold=MERGE_THRESHOLD, threads=THREADS):
    import sherpa_onnx

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(models / SEGMENTATION)
            ),
            num_threads=threads,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(models / EMBEDDING), num_threads=threads
        ),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=threshold),
        min_duration_on=MIN_TURN_S,
        min_duration_off=MIN_GAP_S,
    )
    if not config.validate():
        raise DiarizationUnavailable("the diarization engine refused its configuration")
    return sherpa_onnx.OfflineSpeakerDiarization(config)


@dataclass(frozen=True)
class RunsSherpaDiarizer:
    """The engine in this process. No network, no third party, ever."""

    models: Path | None = None
    threshold: float = MERGE_THRESHOLD
    threads: int = THREADS
    builds: object = None
    _built: list = field(default_factory=list, repr=False, compare=False)

    def where(self):
        return f"sherpa-onnx pyannote-segmentation-3.0 + titanet-small at {self.models}"

    def _engine(self):
        if self.models is None:
            raise DiarizationUnavailable(f"no diarization models are configured ({MODELS_SETTING})")
        for name in (SEGMENTATION, EMBEDDING):
            if not (Path(self.models) / name).is_file():
                raise DiarizationUnavailable(f"diarization model {name} is not in {self.models}")
        if not self._built:
            if self.builds is not None:
                self._built.append(self.builds(Path(self.models)))
            else:
                self._built.append(
                    builds_sherpa_diarizer(Path(self.models), self.threshold, self.threads)
                )
        return self._built[0]

    def __call__(self, samples):
        engine = self._engine()
        try:
            heard = engine.process(samples).sort_by_start_time()
        except (OSError, RuntimeError, ValueError, MemoryError) as broke:
            raise DiarizationUnavailable(f"{self.where()}: {broke}") from broke
        return [
            {
                "start": round(float(turn.start), 3),
                "end": round(float(turn.end), 3),
                "speaker": f"S{turn.speaker}",
            }
            for turn in heard
        ]


@dataclass(frozen=True)
class DiarizesAudio:
    """The callable `DiarizesRecording.diarizes` expects: a Recording in, turns out."""

    store: object
    engine: object = field(default_factory=RunsSherpaDiarizer)
    decodes: object = field(default_factory=DecodesChannelOne)

    def __call__(self, recording):
        source = self.store.resolves(recording)
        with tempfile.TemporaryDirectory(prefix="sermon-diarize-") as work:
            try:
                decoded = self.decodes(source, Path(work))
            except TranscriptionUnavailable as undecodable:
                raise DiarizationUnavailable(str(undecodable)) from undecodable
            return self.engine(decoded.between(0.0, decoded.duration))


def diarizes_with(store, environment=None):
    """Local models when the setting names them; otherwise a diarizer that is unavailable."""
    named = (os.environ if environment is None else environment).get(MODELS_SETTING)
    return DiarizesAudio(store=store, engine=RunsSherpaDiarizer(models=Path(named) if named else None))
