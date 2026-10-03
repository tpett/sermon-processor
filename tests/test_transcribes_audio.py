import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from steps._asr import (
    AnswersOnTheTailnet,
    RecognizesSteadily,
    RefusesEveryTime,
    StatesTheAudio,
    silences_every,
)

from sermon.analysis.transcribes_audio import (
    ASR_ENDPOINT,
    CHUNK_TARGET_S,
    MODEL,
    POOR_CONFIDENCE,
    AudioNotDecodable,
    DecodesChannelOne,
    PostsToTranscriber,
    RetriesTranscription,
    TranscribesAudio,
    TranscriberRefused,
    TranscriberUnreachable,
    chunks_at_silence,
    confidence_of,
    marks_likely_music,
    refuses_a_public_transcriber,
    transcribes_with,
)
from sermon.store import Recording

SERVICE_S = 5412.0
LONG_SERVICE_S = 11400.0
SPIKE_DATA = os.environ.get("SERMON_SPIKE_DATA")
SPIKE_TRANSCRIPT = "recording_20260712_103000.whisper-large-v3-turbo+words.json"
SINGING_MINUTES = (6, 10)
SERMON_SPAN = (1167.88, 4243.68)


@dataclass
class OneLocalFile:
    path: object

    def resolves(self, entity):
        return self.path


def a_recording(duration=SERVICE_S):
    return Recording(
        recording_id="recording_20260712_103000",
        object_key="recordings/recording_20260712_103000.flac",
        state="downloaded",
        started_at=datetime(2026, 7, 12, 10, 30, tzinfo=UTC),
        started_at_source="key",
        size_bytes=1,
        duration_seconds=duration,
    )


def transcribes(engine, duration=SERVICE_S, silences=None):
    return TranscribesAudio(
        store=OneLocalFile(path=Path("/nowhere.flac")),
        engine=engine,
        decodes=StatesTheAudio(
            duration=duration,
            silences=silences if silences is not None else silences_every(duration),
        ),
    )(a_recording(duration))


def test_confidence_reads_the_average_log_probability_as_a_probability():
    assert confidence_of(-0.122) == 0.8851
    assert confidence_of(-2.5) == 0.0821
    assert confidence_of(None) == 0.0


def test_one_chunk_when_the_recording_is_shorter_than_the_target():
    assert chunks_at_silence(1200.0, []) == ((0.0, 1200.0),)


def test_chunk_boundaries_land_in_the_middle_of_a_silence_run():
    quiet = [{"start": 1700.0, "end": 1712.0}]
    assert chunks_at_silence(3000.0, quiet) == ((0.0, 1706.0), (1706.0, 3000.0))


def test_a_silence_too_short_to_cut_in_is_not_used():
    assert chunks_at_silence(3000.0, [{"start": 1700.0, "end": 1701.0}]) == (
        (0.0, CHUNK_TARGET_S),
        (CHUNK_TARGET_S, 3000.0),
    )


def test_chunks_cover_the_recording_without_a_gap_or_an_overlap():
    spans = chunks_at_silence(LONG_SERVICE_S, silences_every(LONG_SERVICE_S))
    assert spans[0][0] == 0.0
    assert spans[-1][1] == LONG_SERVICE_S
    assert [end for _, end in spans[:-1]] == [start for start, _ in spans[1:]]


def test_a_three_hour_service_is_cut_into_pieces():
    assert len(chunks_at_silence(LONG_SERVICE_S, silences_every(LONG_SERVICE_S))) > 1


def test_times_are_absolute_against_the_source_across_every_chunk():
    doc = transcribes(RecognizesSteadily(), duration=LONG_SERVICE_S)
    starts = [item["start"] for item in doc["utterances"]]
    assert starts == sorted(starts)
    assert doc["utterances"][-1]["end"] == pytest.approx(LONG_SERVICE_S, abs=12.0)
    assert all(
        word["start"] >= item["start"] - 0.001
        for item in doc["utterances"]
        for word in item["words"]
    )


def test_no_utterance_straddles_a_chunk_boundary():
    doc = transcribes(RecognizesSteadily(), duration=LONG_SERVICE_S)
    assert len(doc["chunks"]) > 1
    for chunk in doc["chunks"][:-1]:
        assert not [
            item
            for item in doc["utterances"]
            if item["start"] < chunk["end"] < item["end"]
        ]


def test_every_word_carries_a_start_and_an_end():
    doc = transcribes(RecognizesSteadily())
    words = [word for item in doc["utterances"] for word in item["words"]]
    assert words
    assert all(word["start"] <= word["end"] for word in words)
    assert all(set(word) == {"w", "start", "end"} for word in words)


def test_the_document_carries_what_the_pipeline_reads():
    doc = transcribes(RecognizesSteadily())
    assert set(doc) >= {
        "asr_config",
        "duration",
        "model",
        "recording_id",
        "silences",
        "started_at",
        "transcribe_seconds",
        "utterances",
        "word_timestamps",
    }
    assert set(doc["utterances"][0]) >= {
        "start",
        "end",
        "text",
        "speaker",
        "words",
        "avg_logprob",
        "compression_ratio",
        "no_speech_prob",
        "confidence",
    }


def test_the_silence_runs_the_decoder_found_are_carried_through():
    quiet = ({"start": 100.0, "end": 190.0},)
    doc = transcribes(RecognizesSteadily(), silences=quiet)
    assert doc["silences"] == [{"start": 100.0, "end": 190.0}]


def test_a_poor_recognition_is_recorded_as_a_poor_confidence():
    doc = transcribes(RecognizesSteadily(logprob=-1.5))
    assert doc["speech_confidence"] < POOR_CONFIDENCE


def test_a_clear_recording_is_not_flagged_poor():
    doc = transcribes(RecognizesSteadily())
    assert doc["speech_confidence"] > POOR_CONFIDENCE


def test_the_spoken_language_is_detected_and_recorded():
    doc = transcribes(RecognizesSteadily(language="es"))
    assert doc["language"] == "es"


def test_audio_that_cannot_be_decoded_is_not_retried_forever():
    engine = RecognizesSteadily()
    delays = []
    attempt = RetriesTranscription(
        transcribes=TranscribesAudio(
            store=OneLocalFile(path=Path("/nowhere.flac")),
            engine=engine,
            decodes=DecodesChannelOne(),
        ),
        sleeps=delays.append,
    )
    with pytest.raises(AudioNotDecodable):
        attempt(a_recording())
    assert delays == []
    assert engine.windows == []


def test_a_missing_source_is_not_decodable():
    with pytest.raises(AudioNotDecodable):
        DecodesChannelOne()(None, Path("/tmp"))


def test_an_unreachable_transcriber_is_retried_with_growing_delays():
    engine = RefusesEveryTime()
    delays = []
    attempt = RetriesTranscription(
        transcribes=TranscribesAudio(
            store=OneLocalFile(path=Path("/nowhere.flac")),
            engine=engine,
            decodes=StatesTheAudio(duration=SERVICE_S),
        ),
        sleeps=delays.append,
    )
    with pytest.raises(TranscriberUnreachable):
        attempt(a_recording())
    assert len(engine.attempts) == 3
    assert delays == [2.0, 4.0]


def test_the_model_may_be_reached_over_http_on_the_tailnet():
    answers = AnswersOnTheTailnet()
    doc = transcribes(PostsToTranscriber(endpoint="http://100.88.211.71:9000", opens=answers))
    assert answers.destinations
    assert all(
        item.startswith("http://100.88.211.71:9000/transcribe")
        for item in answers.destinations
    )
    assert doc["utterances"][0]["words"]


class Resolves:
    """A resolver the test states; nothing here reaches a real DNS server."""

    def __init__(self, answers):
        self.answers = dict(answers)
        self.asked = []

    def __call__(self, host):
        self.asked.append(host)
        if host not in self.answers:
            raise OSError(f"no such host {host}")
        return list(self.answers[host])


NAMES = {
    "localhost": ["127.0.0.1", "::1"],
    "mac-m1.ts.net": ["100.88.211.71"],
    "asr.home.internal": ["192.168.1.9"],
    "evil.example.com.local": ["93.184.216.34"],
    "split.home.internal": ["192.168.1.9", "93.184.216.34"],
    "funnel.ts.net": ["100.88.211.71", "203.0.113.7"],
    "lan.ts.net": ["192.168.1.9"],
    "api.example.com": ["93.184.216.34"],
}


def resolving():
    return Resolves(NAMES)


def test_a_transcriber_that_is_not_on_this_network_is_refused():
    for endpoint in ("https://api.example.com/v1", "http://8.8.8.8:9000", "http://"):
        with pytest.raises(TranscriberRefused):
            PostsToTranscriber(endpoint=endpoint, resolves=resolving())


def test_a_private_transcriber_is_allowed():
    for endpoint in (
        "http://100.88.211.71:9000",
        "http://192.168.1.9:9000",
        "http://10.0.0.4:9000",
        "http://172.16.0.4:9000",
        "http://169.254.1.1:9000",
        "http://127.0.0.1:9000",
        "http://[::1]:9000",
        "http://localhost:9000",
        "http://mac-m1.ts.net:9000",
        "http://asr.home.internal:9000",
    ):
        assert refuses_a_public_transcriber(endpoint, resolves=resolving()) == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://evil.example.com.local:9000",
        "http://split.home.internal:9000",
        "http://funnel.ts.net:9000",
        "http://lan.ts.net:9000",
        "http://unresolvable.internal:9000",
        "http://[::ffff:8.8.8.8]:9000",
        "http://0.0.0.0:9000",
        "http://192.0.2.1:9000",
        "http://[2001:db8::1]:9000",
    ],
)
def test_a_name_is_judged_by_every_address_it_resolves_to(endpoint):
    with pytest.raises(TranscriberRefused):
        refuses_a_public_transcriber(endpoint, resolves=resolving())


def test_a_literal_address_is_never_resolved():
    resolver = resolving()
    refuses_a_public_transcriber("http://100.88.211.71:9000", resolves=resolver)
    assert resolver.asked == []


def test_the_name_is_checked_again_before_audio_is_posted():
    resolver = resolving()
    answers = AnswersOnTheTailnet(destinations=[])
    engine = PostsToTranscriber(endpoint="http://mac-m1.ts.net:9000", opens=answers, resolves=resolver)
    resolver.answers["mac-m1.ts.net"] = ["93.184.216.34"]
    with pytest.raises(TranscriberRefused):
        engine([0.0] * 16)
    assert answers.destinations == []


def test_the_local_engine_is_chosen_when_no_endpoint_is_named():
    local = transcribes_with(store=OneLocalFile(path=None), environment={})
    assert local.transcribes.engine.model == MODEL


def test_the_environment_may_name_the_machine_holding_the_model():
    named = transcribes_with(
        store=OneLocalFile(path=None),
        environment={ASR_ENDPOINT: "http://100.88.211.71:9000"},
    )
    assert named.transcribes.engine.endpoint == "http://100.88.211.71:9000"


def test_a_named_private_endpoint_is_chosen_over_the_local_engine():
    remote = transcribes_with(store=OneLocalFile(path=None), endpoint="http://100.88.211.71:9000")
    assert remote.transcribes.engine.endpoint == "http://100.88.211.71:9000"


def test_music_is_marked_where_the_audio_sounds_but_says_little():
    utterances = [
        {"start": at, "end": at + 8.0, "confidence": 0.8, "words": [{"w": "la"}] * 4}
        for at in range(0, 300, 12)
    ]
    marked = marks_likely_music(utterances, [], 300.0)
    assert marked
    assert marked[0]["start"] == 0.0
    assert marked[0]["end"] == pytest.approx(300.0)


def test_speech_is_not_marked_as_music():
    utterances = [
        {"start": at, "end": at + 8.0, "confidence": 0.85, "words": [{"w": "word"}] * 24}
        for at in range(0, 300, 12)
    ]
    assert marks_likely_music(utterances, [], 300.0) == []


def test_silence_is_not_marked_as_music():
    assert marks_likely_music([], [{"start": 0.0, "end": 300.0}], 300.0) == []


@pytest.mark.skipif(not SPIKE_DATA, reason="SERMON_SPIKE_DATA names the spike corpus")
def test_the_singing_in_a_real_service_is_marked_and_the_sermon_is_not():
    doc = json.loads((Path(SPIKE_DATA) / "transcripts" / SPIKE_TRANSCRIPT).read_text())
    for item in doc["utterances"]:
        item["confidence"] = confidence_of(item.get("avg_logprob"))
    marked = marks_likely_music(doc["utterances"], doc["silences"], doc["duration"])
    singing = [
        span
        for span in marked
        if span["start"] <= SINGING_MINUTES[0] * 60 and span["end"] >= SINGING_MINUTES[1] * 60
    ]
    assert singing
    overlap = sum(
        max(0.0, min(span["end"], SERMON_SPAN[1]) - max(span["start"], SERMON_SPAN[0]))
        for span in marked
    )
    assert overlap / (SERMON_SPAN[1] - SERMON_SPAN[0]) < 0.05
