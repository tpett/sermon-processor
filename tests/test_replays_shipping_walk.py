import json

import pytest

from sermon.analysis.proposes_from_transcript import ChoosesBoundaries, DerivesSpans
from sermon.analysis.replays_shipping_walk import (
    ReplayFailed,
    ReplaysShippingWalk,
    SKIPPED_IN_REPLAY,
)
from sermon.jobs import analyzes_recording
from sermon.pipeline import classify, segments

RECORDING = "recording_20260823_103015"
TAG = "fw-qwen3.6.whole.v2"
ASR = "fw-test+words"
SPOKEN = {
    "announcements": "good morning and welcome there is coffee after the service",
    "scripture_reading": "please stand for the reading of gods word from romans chapter eight",
    "sermon": "this morning we will look at what the apostle means by grace and what it asks",
    "prayer": "let us pray father we thank you for this day in jesus name amen",
}
BLOCKS = (
    (0.0, 300.0, "announcements"),
    (300.0, 1200.0, "music"),
    (1200.0, 1500.0, "scripture_reading"),
    (1500.0, 4000.0, "sermon"),
    (4000.0, 4200.0, "prayer"),
    (4200.0, 4800.0, "music"),
)
MODEL_PUNCH_IN = 1350.0


def words_over(start, end, text):
    words, at = [], start + 2.0
    while at + 0.3 < end - 4.0:
        for word in text.split():
            if at + 0.3 >= end - 4.0:
                break
            words.append({"w": word, "start": round(at, 3), "end": round(at + 0.25, 3)})
            at += 0.3
        at += 1.5
    return words


def transcript():
    utterances = []
    for start, end, kind in BLOCKS:
        if kind in SPOKEN:
            spoken = words_over(start, end, SPOKEN[kind])
            for index in range(0, len(spoken), 12):
                chunk = spoken[index:index + 12]
                utterances.append({
                    "start": chunk[0]["start"],
                    "end": chunk[-1]["end"],
                    "text": " ".join(word["w"] for word in chunk),
                    "words": chunk,
                })
    return {
        "recording_id": RECORDING,
        "started_at": "2026-08-23T10:30:15",
        "duration": 4800.0,
        "language": "en",
        "utterances": utterances,
        "silences": [],
    }


def block_file(model_punch_in=MODEL_PUNCH_IN):
    return {
        "recording_id": RECORDING,
        "asr_config": ASR,
        "blocks": [
            {"start": start, "end": end, "type": kind, "confidence": 0.9, "evidence": "e"}
            for start, end, kind in BLOCKS
        ],
        "model_segments": [
            {"punch_in": model_punch_in, "punch_out": 4000.0, "classification": "sermon"}
        ],
        "segments": [{"punch_in": 1.0, "punch_out": 2.0}],
    }


@pytest.fixture
def corpus(tmp_path):
    (tmp_path / "blocks").mkdir()
    (tmp_path / "transcripts").mkdir()
    (tmp_path / "diarization").mkdir()
    (tmp_path / "blocks" / f"{RECORDING}.{TAG}.json").write_text(json.dumps(block_file()))
    (tmp_path / "transcripts" / f"{RECORDING}.{ASR}.json").write_text(json.dumps(transcript()))
    return tmp_path


def replayed(corpus):
    return ReplaysShippingWalk(corpus_root=corpus)(corpus / "blocks" / f"{RECORDING}.{TAG}.json")


def expected_with(model_segments):
    doc = transcript()
    segments.DATA_ROOT = None
    return [
        (round(chosen["punch_in"], 3), round(chosen["punch_out"], 3))
        for chosen in _choosing(ChoosesBoundaries(model_segments=model_segments), doc)
    ]


def _choosing(chooses, doc):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as root:
        (Path(root) / "diarization").mkdir()
        segments.DATA_ROOT = Path(root)
        segments._EDGE_CACHE.clear()
        spans = [
            {"start": start, "end": end, "type": kind, "confidence": 0.9}
            for start, end, kind in BLOCKS
        ]
        found = chooses(spans, doc)
        segments._EDGE_CACHE.clear()
        segments.DATA_ROOT = None
        return found


def test_the_replay_names_the_recording_and_the_configuration(corpus):
    found = replayed(corpus)
    assert found.recording_id == RECORDING
    assert found.tag == TAG
    assert found.name == f"{RECORDING}.{TAG}.json"


def test_the_replay_proposes_what_the_walk_chooses_with_no_model_segments(corpus):
    found = replayed(corpus)
    proposed = [(cut.punch_in, cut.punch_out) for cut in found.proposals]
    assert proposed == expected_with(())
    assert proposed != expected_with(block_file()["model_segments"])


def test_the_replay_ignores_the_boundaries_the_block_file_stored(corpus):
    assert [(cut.punch_in, cut.punch_out) for cut in replayed(corpus).proposals] != [(1.0, 2.0)]


def test_the_replay_runs_the_walk_so_a_stage_dropped_from_it_shows(corpus, monkeypatch):
    whole = replayed(corpus)
    monkeypatch.setattr(
        analyzes_recording,
        "WALK",
        tuple(name for name in analyzes_recording.WALK if name != "boundary_refinement"),
    )
    unrefined = replayed(corpus)
    doc = transcript()
    assert [(cut.punch_in, cut.punch_out) for cut in unrefined.proposals] == [
        (span["punch_in"], span["punch_out"]) for span in _choosing(DerivesSpans(), doc)
    ]
    assert unrefined.proposals != whole.proposals


def test_the_replay_skips_only_stages_the_walk_already_survives_losing(corpus):
    assert SKIPPED_IN_REPLAY <= analyzes_recording.OPTIONAL_STAGES
    assert {"summarization", "diarization", "waveform", "preview"} == SKIPPED_IN_REPLAY


def test_a_skipped_stage_the_walk_cannot_survive_losing_fails_the_replay(corpus, monkeypatch):
    monkeypatch.setattr(
        analyzes_recording, "OPTIONAL_STAGES", frozenset({"waveform", "preview", "diarization"})
    )
    with pytest.raises(ReplayFailed, match="summarization"):
        replayed(corpus)


def test_the_replay_leaves_the_pipeline_roots_and_model_endpoint_as_it_found_them(corpus):
    segments.DATA_ROOT, classify.DATA, classify.PROMPTS = "a", "b", "c"
    classify.ENDPOINT = "http://somewhere"
    try:
        replayed(corpus)
        assert (segments.DATA_ROOT, classify.DATA, classify.PROMPTS) == ("a", "b", "c")
        assert classify.ENDPOINT == "http://somewhere"
    finally:
        segments.DATA_ROOT = classify.DATA = classify.PROMPTS = classify.ENDPOINT = None


def test_the_replay_never_reaches_a_model_endpoint(corpus, monkeypatch):
    seen = []
    monkeypatch.setattr(classify, "ollama", lambda *a, **k: seen.append(a) or "{}")
    replayed(corpus)
    assert seen == []


def test_a_block_file_with_no_transcript_is_not_replayed(corpus):
    (corpus / "transcripts" / f"{RECORDING}.{ASR}.json").unlink()
    assert replayed(corpus) is None
