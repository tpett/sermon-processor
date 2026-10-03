"""A diarizer the spec can run: the real stage and engine wrapper, no model and no audio.

Only the two things that need real audio are substituted -- decoding, and the
engine's own clustering -- so labelling, ordering, storage and the failure
path are the shipped code.
"""

from __future__ import annotations

from dataclasses import dataclass

from steps._asr import StatesTheAudio

from sermon.analysis.diarizes_audio import DiarizesAudio, RunsSherpaDiarizer

SERVICE_VOICES = ((0.0, 0.05, 0), (0.05, 0.35, 1), (0.35, 0.8, 0), (0.8, 1.0, 2))


@dataclass(frozen=True)
class HeardTurn:
    start: float
    end: float
    speaker: int


class HeardInOrderOfVoice(list):
    def sort_by_start_time(self):
        return sorted(self, key=lambda turn: turn.start)


@dataclass(frozen=True)
class HearsAService:
    """Three voices, the first returning after the second: the engine's raw answer."""

    duration: float

    def process(self, samples):
        return HeardInOrderOfVoice(
            sorted(
                (
                    HeardTurn(start * self.duration, end * self.duration, voice)
                    for start, end, voice in SERVICE_VOICES
                ),
                key=lambda turn: turn.speaker,
            )
        )


def diarizes_a_service(store, recording):
    duration = recording.duration_seconds or 5412.0
    return DiarizesAudio(
        store=store,
        engine=RunsSherpaDiarizer(builds=lambda _models: HearsAService(duration)),
        decodes=StatesTheAudio(duration=duration),
    )
