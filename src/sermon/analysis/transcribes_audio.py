"""Turn a Recording's audio into the transcript every later stage reads.

features/analysis/transcription.feature. The document shape is the one the spike
produced and the pipeline already consumes.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlencode, urlparse

import numpy as np

from sermon.analysis.progress import ReportsTranscriptionProgress
from sermon.pipeline import audio

SAMPLE_RATE = audio.SR
ENVELOPE_HZ = 100
SILENCE_MIN_S = 2.0

MODEL = "deepdml/faster-whisper-large-v3-turbo-ct2"
COMPUTE_TYPE = "int8"
THREADS = 8
BEAM_SIZE = 5
EXPECTED_LANGUAGE = "en"
ASR_ENDPOINT = "SERMON_ASR_ENDPOINT"

CHUNK_TARGET_S = 1800.0
CHUNK_SEARCH_S = 300.0

# Singing is not low-confidence; it is slow. Silence is slow too, hence voiced.
MUSIC_WINDOW_S = 60.0
MUSIC_WORDS_PER_S = 1.4
MUSIC_VOICED_FRACTION = 0.5
MUSIC_MIN_S = 60.0

# Below the whole corpus, which runs 0.617 to 0.864: a floor, not a quality bar.
POOR_CONFIDENCE = 0.55

TAILNET = ipaddress.ip_network("100.64.0.0/10")
TAILNET_SUFFIX = ".ts.net"
THIS_NETWORK = tuple(
    ipaddress.ip_network(network)
    for network in (
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "fe80::/10",
        TAILNET,
    )
)
RETRY_ATTEMPTS = 3
RETRY_FIRST_DELAY_S = 2.0


class TranscriptionUnavailable(RuntimeError):
    """The transcript could not be produced. Retrying may or may not help."""


class AudioNotDecodable(TranscriptionUnavailable):
    def __init__(self, source):
        super().__init__(f"{source} could not be decoded to mono 16 kHz audio")


class TranscriberUnreachable(TranscriptionUnavailable):
    def __init__(self, where):
        super().__init__(f"the transcriber at {where} did not answer")
        self.where = where


class TranscriberRefused(ValueError):
    pass


def resolves_host(host):
    return [info[4][0] for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)]


def addresses_of(host, resolves):
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        return [ipaddress.ip_address(str(found).split("%")[0]) for found in resolves(host)]
    except (OSError, ValueError, UnicodeError):
        return []


def refuses_a_public_transcriber(endpoint, resolves=resolves_host):
    """Audio may only be sent to a machine on this network. Nothing else."""
    host = urlparse(endpoint).hostname
    if not host:
        raise TranscriberRefused(f"{endpoint!r} names no host to send audio to")
    addresses = addresses_of(host, resolves)
    if not addresses:
        raise TranscriberRefused(f"{host!r} could not be resolved; audio may only go to a private address")
    allowed = (TAILNET,) if host.rstrip(".").endswith(TAILNET_SUFFIX) else THIS_NETWORK
    elsewhere = [address for address in addresses if not any(address in network for network in allowed)]
    if elsewhere:
        raise TranscriberRefused(f"{host} reaches {elsewhere[0]}, which is not on this network; audio may not go there")
    return endpoint


def confidence_of(avg_logprob):
    """Whisper's per-segment average log probability, read as a probability."""
    if avg_logprob is None:
        return 0.0
    return round(min(1.0, math.exp(float(avg_logprob))), 4)


def average_confidence(utterances, start=None, end=None):
    within = [
        item
        for item in utterances
        if (start is None or item["end"] > start) and (end is None or item["start"] < end)
    ]
    if not within:
        return None
    return round(sum(item["confidence"] for item in within) / len(within), 4)


def quiet_seconds(silences, start, end):
    return sum(
        max(0.0, min(gap["end"], end) - max(gap["start"], start)) for gap in silences
    )


def marks_likely_music(utterances, silences, duration, window=MUSIC_WINDOW_S):
    """Windows that are sounding but barely producing words: singing, not speech."""
    if duration <= 0:
        return []
    marked = []
    for index in range(max(1, math.ceil(duration / window))):
        start = index * window
        end = min(start + window, duration)
        if end - start <= 0:
            continue
        words = sum(
            len(item.get("words", ()))
            for item in utterances
            if item["start"] < end and item["end"] > start
        )
        voiced = 1.0 - quiet_seconds(silences, start, end) / (end - start)
        if words / (end - start) < MUSIC_WORDS_PER_S and voiced > MUSIC_VOICED_FRACTION:
            marked.append((start, end))
    return [
        {
            "start": round(start, 3),
            "end": round(end, 3),
            "average_confidence": average_confidence(utterances, start, end),
        }
        for start, end in _merged(marked)
        if end - start >= MUSIC_MIN_S
    ]


def _merged(spans):
    joined = []
    for start, end in spans:
        if joined and start - joined[-1][1] < 1e-6:
            joined[-1] = (joined[-1][0], end)
            continue
        joined.append((start, end))
    return joined


def chunks_at_silence(duration, silences, target=CHUNK_TARGET_S, search=CHUNK_SEARCH_S):
    """Cut points for the work, placed in the middle of a long enough silence.

    A boundary inside a silence run cannot split a word. With no silence to
    reach, the cut lands on the target and is reported in the document.
    """
    if duration <= target:
        return ((0.0, duration), )
    quiet = [
        (gap["start"] + gap["end"]) / 2.0
        for gap in silences
        if gap["end"] - gap["start"] >= SILENCE_MIN_S
    ]
    cuts = []
    at = 0.0
    while duration - at > target:
        wanted = at + target
        nearby = [
            moment
            for moment in quiet
            if abs(moment - wanted) <= search and moment > at + search
        ]
        chosen = min(nearby, key=lambda moment: abs(moment - wanted), default=wanted)
        cuts.append(chosen)
        at = chosen
    edges = (0.0, *cuts, duration)
    return tuple(zip(edges, edges[1:]))


@dataclass(frozen=True)
class DecodedAudio:
    """Channel 1 of the source, mono 16 kHz, on disk and memory-mapped."""

    raw: Path
    duration: float
    silences: list
    samples: np.ndarray

    def between(self, start, end):
        window = self.samples[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)]
        return np.asarray(window, dtype=np.float32) / 32768.0


@dataclass(frozen=True)
class DecodesChannelOne:
    """ffmpeg once, then everything else reads the same decoded copy."""

    envelope_hz: int = ENVELOPE_HZ
    silence_min_s: float = SILENCE_MIN_S

    def __call__(self, source, work):
        if source is None or not Path(source).is_file():
            raise AudioNotDecodable(source)
        try:
            raw = audio.decode(Path(source), Path(work) / "channel1.raw")
        except (OSError, RuntimeError, subprocess.SubprocessError) as failed:
            raise AudioNotDecodable(source) from failed
        samples = np.memmap(raw, dtype=np.int16, mode="r")
        if samples.size == 0:
            raise AudioNotDecodable(source)
        envelope = audio.envelope(raw, self.envelope_hz)
        return DecodedAudio(
            raw=raw,
            duration=samples.size / SAMPLE_RATE,
            silences=audio.quiet_runs(envelope, self.envelope_hz, self.silence_min_s),
            samples=samples,
        )


@dataclass(frozen=True)
class Recognized:
    utterances: list
    language: str
    language_probability: float


def utterance_from(start, end, text, avg_logprob, no_speech_prob, compression_ratio, words):
    return {
        "start": round(float(start), 3),
        "end": round(float(end), 3),
        "speaker": None,
        "text": text.strip(),
        "confidence": confidence_of(avg_logprob),
        "avg_logprob": round(float(avg_logprob or 0.0), 4),
        "no_speech_prob": round(float(no_speech_prob or 0.0), 4),
        "compression_ratio": round(float(compression_ratio or 0.0), 3),
        "words": list(words),
    }


@dataclass(frozen=True)
class RunsFasterWhisper:
    """The engine in this process. No network, no third party, ever."""

    reports_progress: ClassVar[bool] = True
    model: str = MODEL
    compute_type: str = COMPUTE_TYPE
    threads: int = THREADS
    beam_size: int = BEAM_SIZE
    loads: object = None
    _loaded: list = field(default_factory=list, repr=False, compare=False)

    def where(self):
        return f"faster-whisper {self.model} ({self.compute_type})"

    def _model(self):
        if not self._loaded:
            self._loaded.append(self.loads() if self.loads else self._imports())
        return self._loaded[0]

    def _imports(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError as missing:
            raise TranscriberUnreachable(self.where()) from missing
        return WhisperModel(
            self.model,
            device="cpu",
            compute_type=self.compute_type,
            cpu_threads=self.threads,
        )

    def __call__(self, samples, language=EXPECTED_LANGUAGE, reports=None):
        try:
            segments, spoken = self._model().transcribe(
                samples,
                language=language,
                beam_size=self.beam_size,
                word_timestamps=True,
                condition_on_previous_text=False,
                vad_filter=False,
            )
            recognized = []
            for segment in segments:
                recognized.append(self._utterance(segment))
                if reports is not None:
                    reports(float(segment.end))
        except TranscriptionUnavailable:
            raise
        except (OSError, RuntimeError, ValueError) as broke:
            raise TranscriberUnreachable(self.where()) from broke
        return Recognized(
            utterances=recognized,
            language=getattr(spoken, "language", language) or language,
            language_probability=float(getattr(spoken, "language_probability", 1.0) or 0.0),
        )

    def _utterance(self, segment):
        return utterance_from(
            segment.start,
            segment.end,
            segment.text,
            segment.avg_logprob,
            segment.no_speech_prob,
            segment.compression_ratio,
            (
                {
                    "w": word.word.strip(),
                    "start": round(float(word.start), 3),
                    "end": round(float(word.end), 3),
                }
                for word in (segment.words or ())
            ),
        )

    def detects(self, samples):
        heard = self(samples[: SAMPLE_RATE * 30] if len(samples) else samples, language=None)
        return heard.language, heard.language_probability


@dataclass(frozen=True)
class PostsToTranscriber:
    """The same engine on another machine on the tailnet, reached over HTTP.

    The app server holds no shell credentials for that box, so HTTP to a private
    address is the only way to reach it.
    """

    endpoint: str
    opens: object = urllib.request.urlopen
    timeout_s: float = 3600.0
    resolves: object = field(default=resolves_host, repr=False)

    def __post_init__(self):
        refuses_a_public_transcriber(self.endpoint, self.resolves)

    def where(self):
        return self.endpoint

    def __call__(self, samples, language=EXPECTED_LANGUAGE):
        refuses_a_public_transcriber(self.endpoint, self.resolves)
        asked = f"{self.endpoint.rstrip('/')}/transcribe"
        query = urlencode({"language": language} if language else {})
        request = urllib.request.Request(
            f"{asked}?{query}" if query else asked,
            data=np.asarray(samples, dtype=np.float32).tobytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Sample-Rate": str(SAMPLE_RATE),
            },
            method="POST",
        )
        try:
            with self.opens(request, timeout=self.timeout_s) as answering:
                answered = json.loads(answering.read())
        except (OSError, urllib.error.HTTPError, ValueError) as unanswered:
            raise TranscriberUnreachable(self.endpoint) from unanswered
        return Recognized(
            utterances=[
                utterance_from(
                    item["start"],
                    item["end"],
                    item.get("text", ""),
                    item.get("avg_logprob"),
                    item.get("no_speech_prob"),
                    item.get("compression_ratio"),
                    item.get("words", ()),
                )
                for item in answered.get("utterances", ())
            ],
            language=answered.get("language") or language or EXPECTED_LANGUAGE,
            language_probability=float(answered.get("language_probability") or 0.0),
        )

    def detects(self, samples):
        heard = self(samples[: SAMPLE_RATE * 30] if len(samples) else samples, language=None)
        return heard.language, heard.language_probability


@dataclass(frozen=True)
class TranscribesAudio:
    """The callable `TranscribesRecording.transcribes` expects.

    Takes a Recording whose source is on local disk, gives back the transcript
    document, and records in it how the document was made.
    """

    store: object
    engine: object = field(default_factory=RunsFasterWhisper)
    decodes: object = field(default_factory=DecodesChannelOne)
    language: str = EXPECTED_LANGUAGE
    detects_language: bool = True
    clock: object = time.monotonic
    work: object = None
    reports: object = None

    def __call__(self, recording):
        source = self.store.resolves(recording)
        if self.work is not None:
            return self._transcribes(recording, source, Path(self.work))
        with tempfile.TemporaryDirectory(prefix="sermon-asr-") as work:
            return self._transcribes(recording, source, Path(work))

    def _transcribes(self, recording, source, work):
        decoded = self.decodes(source, work)
        spans = chunks_at_silence(decoded.duration, decoded.silences)
        started = self.clock()
        language, probability = self._language(decoded)
        utterances = []
        for index, (start, end) in enumerate(spans, start=1):
            heard = self._recognises(
                recording, decoded, language, index, len(spans), start, end
            )
            utterances.extend(_shifted(heard.utterances, start, utterances))
        elapsed = self.clock() - started
        music = marks_likely_music(utterances, decoded.silences, decoded.duration)
        return {
            "recording_id": recording.recording_id,
            "desktop_label": None,
            "asr_config": _asr_config(self.engine, self.language),
            "model": getattr(self.engine, "model", self.engine.where()),
            "compute_type": getattr(self.engine, "compute_type", None),
            "word_timestamps": True,
            "started_at": recording.started_at.replace(tzinfo=None).isoformat(),
            "duration": round(decoded.duration, 3),
            "split": None,
            "utterances": utterances,
            "silences": decoded.silences,
            "likely_music": music,
            "language": language,
            "language_probability": round(probability, 4),
            "average_confidence": average_confidence(utterances),
            "speech_confidence": _speech_confidence(utterances, music),
            "chunks": [
                {"start": round(start, 3), "end": round(end, 3)} for start, end in spans
            ],
            "transcribed_by": self.engine.where(),
            "transcribe_seconds": round(elapsed, 1),
        }

    def _recognises(self, recording, decoded, language, chunk, chunks, start, end):
        window = decoded.between(start, end)
        if self.reports is None:
            return self.engine(window, language=language)

        def reached(at):
            self.reports(
                recording,
                chunk=chunk,
                chunks=chunks,
                recognised_seconds=at,
                duration_seconds=decoded.duration,
            )

        reached(start)
        if getattr(self.engine, "reports_progress", False):
            return self.engine(
                window, language=language, reports=lambda at: reached(start + at)
            )
        heard = self.engine(window, language=language)
        reached(end)
        return heard

    def _language(self, decoded):
        if not self.detects_language or not hasattr(self.engine, "detects"):
            return self.language, 1.0
        try:
            heard, probability = self.engine.detects(decoded.between(0.0, 30.0))
        except TranscriptionUnavailable:
            raise
        except Exception:
            return self.language, 1.0
        return (heard or self.language), probability


def _asr_config(engine, language):
    model = str(getattr(engine, "model", engine.where())).split("/")[-1]
    compute = getattr(engine, "compute_type", None)
    return f"fw-{model}{'.' + compute if compute else ''}+words"


def _speech_confidence(utterances, music):
    speech = [
        item
        for item in utterances
        if not any(span["start"] < item["end"] and span["end"] > item["start"] for span in music)
    ]
    return average_confidence(speech or utterances)


def _shifted(utterances, offset, already):
    floor = already[-1]["end"] if already else 0.0
    moved = []
    for item in utterances:
        start = round(item["start"] + offset, 3)
        if start < floor - 1e-6:
            continue
        moved.append(
            item
            | {
                "start": start,
                "end": round(item["end"] + offset, 3),
                "words": [
                    {
                        "w": word["w"],
                        "start": round(word["start"] + offset, 3),
                        "end": round(word["end"] + offset, 3),
                    }
                    for word in item.get("words", ())
                ],
            }
        )
    return moved


@dataclass(frozen=True)
class RetriesTranscription:
    """A small budget: an attempt costs half an hour, so this survives a
    restart rather than grinding against something broken."""

    transcribes: object
    attempts: int = RETRY_ATTEMPTS
    first_delay_s: float = RETRY_FIRST_DELAY_S
    sleeps: object = time.sleep

    def __call__(self, recording):
        last = None
        for attempt in range(self.attempts):
            try:
                return self.transcribes(recording)
            except AudioNotDecodable:
                raise
            except TranscriptionUnavailable as failed:
                last = failed
                if attempt + 1 < self.attempts:
                    self.sleeps(self.first_delay_s * 2**attempt)
        raise last


def transcribes_with(store, endpoint=None, environment=None, **settings):
    """Local engine unless a private endpoint is named; never anything hosted."""
    named = endpoint or (os.environ if environment is None else environment).get(ASR_ENDPOINT)
    engine = PostsToTranscriber(endpoint=named) if named else RunsFasterWhisper(**settings)
    return RetriesTranscription(
        transcribes=TranscribesAudio(
            store=store,
            engine=engine,
            reports=ReportsTranscriptionProgress(store=store),
        )
    )
