"""A transcriber the spec can run: the real stage, no model and no audio.

Transcribing a service costs half an hour of compute, so nothing here loads a
model or opens a file. What it does substitute is narrow — the two things that
need real audio, decoding and recognition — so chunking, timestamp arithmetic,
silence handling, music marking, flagging, retry and the locality rule are the
shipped code in every scenario that exercises them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

from sermon.analysis.transcribes_audio import (
    SAMPLE_RATE,
    DecodedAudio,
    PostsToTranscriber,
    Recognized,
    RetriesTranscription,
    TranscriberUnreachable,
    TranscribesAudio,
    utterance_from,
)

STAND_IN_RATE = SAMPLE_RATE // 1000
SPEECH_WORDS_PER_S = 2.5
CLEAR_LOGPROB = -0.12
POOR_LOGPROB = -1.5
UTTERANCE_S = 8.0
UTTERANCE_PERIOD_S = 12.0
PHRASE = ("and", "he", "said", "to", "them", "let", "us", "pray", "amen", "brothers")


def stand_in_seconds(window):
    return len(window) / STAND_IN_RATE


class StatedAudio(DecodedAudio):
    """The decoded audio, at a thousandth of its sample rate."""

    def between(self, start, end):
        return np.zeros(int(max(0.0, end - start) * STAND_IN_RATE), dtype=np.float32)


@dataclass(frozen=True)
class StatesTheAudio:
    """Stands in for ffmpeg: the duration and silence runs are given, not measured."""

    duration: float
    silences: tuple = ()

    def __call__(self, source, work):
        return StatedAudio(
            raw=None,
            duration=self.duration,
            silences=[dict(gap) for gap in self.silences],
            samples=np.zeros(0, dtype=np.int16),
        )


def utterances_across(seconds, words_per_second, logprob, empty=False):
    spoken = []
    at = 0.0
    while at < seconds - 0.001:
        end = min(at + UTTERANCE_S, seconds)
        count = max(1, int((end - at) * words_per_second))
        step = (end - at) / count
        spoken.append(
            utterance_from(
                at,
                end,
                "" if empty else " ".join(PHRASE[index % len(PHRASE)] for index in range(count)),
                logprob,
                0.0,
                1.4,
                [
                    {
                        "w": PHRASE[index % len(PHRASE)],
                        "start": round(at + index * step, 3),
                        "end": round(at + (index + 1) * step, 3),
                    }
                    for index in range(count)
                ],
            )
        )
        at += UTTERANCE_PERIOD_S
    return spoken


@dataclass
class RecognizesSteadily:
    """Emits plausible speech for whatever window it is handed."""

    words_per_second: float = SPEECH_WORDS_PER_S
    logprob: float = CLEAR_LOGPROB
    language: str = "en"
    windows: list = field(default_factory=list)

    def where(self):
        return "a stand-in recogniser"

    def __call__(self, window, language="en"):
        seconds = stand_in_seconds(window)
        self.windows.append(seconds)
        return Recognized(
            utterances=utterances_across(seconds, self.words_per_second, self.logprob),
            language=self.language,
            language_probability=0.98,
        )

    def detects(self, window):
        return self.language, 0.98


@dataclass
class RefusesEveryTime:
    attempts: list = field(default_factory=list)

    def where(self):
        return "a stand-in recogniser"

    def __call__(self, window, language="en"):
        self.attempts.append(language)
        raise TranscriberUnreachable(self.where())

    def detects(self, window):
        self.attempts.append(None)
        raise TranscriberUnreachable(self.where())


@dataclass
class Answered:
    body: bytes

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *failure):
        return False


@dataclass
class AnswersOnTheTailnet:
    """One request in, one transcript out, and every destination written down."""

    destinations: list = field(default_factory=list)
    words_per_second: float = SPEECH_WORDS_PER_S

    def __call__(self, request, timeout=None):
        self.destinations.append(request.full_url)
        seconds = len(request.data) / 4 / STAND_IN_RATE
        return Answered(
            json.dumps(
                {
                    "utterances": utterances_across(
                        seconds, self.words_per_second, CLEAR_LOGPROB
                    ),
                    "language": "en",
                    "language_probability": 0.98,
                }
            ).encode()
        )


def silences_every(duration, period=600.0, length=6.0):
    return tuple(
        {"start": round(at, 2), "end": round(at + length, 2)}
        for at in _quiet_moments(duration, period)
    )


def _quiet_moments(duration, period):
    at = period
    while at + period < duration:
        yield at
        at += period


def transcribes_for(store, recording):
    """The transcriber the scenario's Givens asked for."""
    duration = recording.duration_seconds or 5412.0
    decodes = StatesTheAudio(duration=duration, silences=silences_every(duration))
    destinations = []
    store._asr_destinations = destinations
    host = getattr(store, "_transcription_host", None)
    if getattr(store, "_failing_stage", None) == "transcription":
        engine = RefusesEveryTime()
        store._asr_attempts = engine.attempts
    elif host:
        engine = PostsToTranscriber(
            endpoint=host, opens=AnswersOnTheTailnet(destinations=destinations)
        )
    else:
        engine = RecognizesSteadily(
            logprob=POOR_LOGPROB if getattr(store, "_poor_transcript", False) else CLEAR_LOGPROB,
            language=getattr(store, "_spoken_language", "en"),
        )
    store._asr_engine = engine
    delays = []
    store._asr_backoff = delays
    return RetriesTranscription(
        transcribes=TranscribesAudio(store=store, engine=engine, decodes=decodes),
        sleeps=delays.append,
    )
