import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from sermon.analysis import DiarizesRecording
from sermon.analysis.diarizes_audio import (
    EMBEDDING,
    MODELS_SETTING,
    SEGMENTATION,
    DiarizationUnavailable,
    DiarizesAudio,
    RunsSherpaDiarizer,
    diarizes_with,
)
from sermon.analysis.io import reads_json
from sermon.jobs.analyzes_recording import StageFailed
from sermon.store import Recording, layout, opens_store

SAMPLE_RATE = 16_000


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def a_recording(store):
    recording = Recording(
        recording_id="recording_20260913_090014",
        object_key="2026/09/13/recording_20260913_090014.flac",
        state="downloaded",
        started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
        started_at_source="key",
        size_bytes=1,
        duration_seconds=12.0,
    )
    return store.saves(replace(recording, local_path=str(layout.source_path(recording))))


@dataclass
class Segment:
    start: float
    end: float
    speaker: int


class Heard(list):
    def sort_by_start_time(self):
        return sorted(self, key=lambda segment: segment.start)


@dataclass
class HearsTwoVoices:
    heard: list

    def process(self, samples):
        self.heard.append(len(samples))
        return Heard([Segment(6.00049, 12.0, 1), Segment(0.0, 5.99951, 0)])


@dataclass
class BreaksMidway:
    def process(self, samples):
        raise RuntimeError("onnxruntime ran out of memory")


@dataclass
class StatedSamples:
    duration: float

    def between(self, start, end):
        return np.zeros(int((end - start) * SAMPLE_RATE), dtype=np.float32)


@dataclass
class DecodesStated:
    duration: float = 12.0

    def __call__(self, source, work):
        return StatedSamples(duration=self.duration)


@dataclass
class RecordsSamples:
    turns: list
    heard: list

    def __call__(self, samples):
        self.heard.append(len(samples))
        return self.turns


def models_in(tmp_path):
    for name in (SEGMENTATION, EMBEDDING):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"onnx")
    return tmp_path


def test_no_models_configured_is_unavailable_and_names_the_setting():
    with pytest.raises(DiarizationUnavailable, match=MODELS_SETTING):
        RunsSherpaDiarizer(models=None)(np.zeros(SAMPLE_RATE, dtype=np.float32))


def test_a_missing_model_file_is_unavailable_and_names_the_file(tmp_path):
    (tmp_path / EMBEDDING).write_bytes(b"onnx")
    with pytest.raises(DiarizationUnavailable, match="model.onnx"):
        RunsSherpaDiarizer(models=tmp_path)(np.zeros(SAMPLE_RATE, dtype=np.float32))


def test_turns_come_back_in_order_in_the_shape_the_pipeline_reads(tmp_path):
    heard = []
    engine = RunsSherpaDiarizer(models=models_in(tmp_path), builds=lambda _: HearsTwoVoices(heard))
    turns = engine(np.zeros(12 * SAMPLE_RATE, dtype=np.float32))
    assert turns == [
        {"start": 0.0, "end": 6.0, "speaker": "S0"},
        {"start": 6.0, "end": 12.0, "speaker": "S1"},
    ]
    assert heard == [12 * SAMPLE_RATE]


def test_the_engine_is_built_once_and_reused(tmp_path):
    built = []

    def builds(models):
        built.append(models)
        return HearsTwoVoices([])

    engine = RunsSherpaDiarizer(models=models_in(tmp_path), builds=builds)
    engine(np.zeros(SAMPLE_RATE, dtype=np.float32))
    engine(np.zeros(SAMPLE_RATE, dtype=np.float32))
    assert built == [tmp_path]


def test_an_engine_that_breaks_is_unavailable(tmp_path):
    engine = RunsSherpaDiarizer(models=models_in(tmp_path), builds=lambda _: BreaksMidway())
    with pytest.raises(DiarizationUnavailable, match="out of memory"):
        engine(np.zeros(SAMPLE_RATE, dtype=np.float32))


def test_the_whole_recording_is_handed_to_the_engine(store):
    heard = []
    turns = [{"start": 0.0, "end": 12.0, "speaker": "S0"}]
    diarizes = DiarizesAudio(
        store=store, engine=RecordsSamples(turns=turns, heard=heard), decodes=DecodesStated()
    )
    assert diarizes(a_recording(store)) == turns
    assert heard == [12 * SAMPLE_RATE]


def test_an_undecodable_source_is_unavailable(store):
    diarizes = DiarizesAudio(store=store, engine=RecordsSamples(turns=[], heard=[]))
    with pytest.raises(DiarizationUnavailable, match="decoded"):
        diarizes(a_recording(store))


def test_the_stage_stores_what_the_engine_heard(store):
    recording = a_recording(store)
    turns = [{"start": 0.0, "end": 6.0, "speaker": "S0"}, {"start": 6.0, "end": 12.0, "speaker": "S1"}]
    DiarizesRecording(store=store, diarizes=lambda _: [dict(turn) for turn in turns])(recording)
    assert reads_json(store, recording, "diarization") == {"turns": turns}


def test_an_unavailable_diarizer_fails_the_stage_by_name(store):
    def unavailable(_recording):
        raise DiarizationUnavailable("no models")

    with pytest.raises(StageFailed) as failed:
        DiarizesRecording(store=store, diarizes=unavailable)(a_recording(store))
    assert failed.value.stage == "diarization"
    assert reads_json(store, a_recording(store), "diarization") is None


def test_the_models_come_from_the_setting(tmp_path):
    named = diarizes_with(store=None, environment={MODELS_SETTING: str(tmp_path)})
    assert named.engine.models == tmp_path
    assert diarizes_with(store=None, environment={}).engine.models is None


def models_on_this_machine():
    named = os.environ.get(MODELS_SETTING)
    spike = os.environ.get("SERMON_SPIKE_DATA")
    for candidate in (named, spike and Path(spike).parent / "work" / "models"):
        if candidate and all((Path(candidate) / name).is_file() for name in (SEGMENTATION, EMBEDDING)):
            return Path(candidate)
    return None


SPOKEN = "In the beginning was the Word, and the Word was with God, and the Word was God."


@pytest.mark.skipif(models_on_this_machine() is None, reason="diarization models are not on this machine")
@pytest.mark.skipif(shutil.which("say") is None, reason="no local speech synthesiser")
def test_the_real_engine_hears_synthetic_speech_and_nothing_in_a_tone(store, tmp_path):
    recording = a_recording(store)
    source = store.resolves(recording)
    source.parent.mkdir(parents=True, exist_ok=True)
    spoken = tmp_path / "spoken.aiff"
    subprocess.run(["say", "-o", str(spoken), SPOKEN], check=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=180:duration=6", "-i", str(spoken),
            "-filter_complex", "[0]aresample=44100[tone];[1]aresample=44100[speech];"
            "[tone][speech]concat=n=2:v=0:a=1", "-ac", "1", str(source),
        ],
        check=True,
    )
    turns = DiarizesAudio(
        store=store, engine=RunsSherpaDiarizer(models=models_on_this_machine(), threads=2)
    )(recording)
    assert turns, "the engine heard no speaker in synthetic speech"
    for turn in turns:
        assert set(turn) == {"start", "end", "speaker"}
        assert turn["speaker"].startswith("S")
        assert turn["start"] >= 5.5, f"a speaker was heard in the tone: {turn}"
    assert sum(turn["end"] - turn["start"] for turn in turns) >= 3.0
