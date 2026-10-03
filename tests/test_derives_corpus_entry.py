import json
from datetime import UTC, datetime

import pytest

from sermon.analysis.derives_corpus_entry import (
    BlockFileAlreadyWritten,
    DerivesCorpusEntry,
    NothingToBlock,
)
from sermon.analysis.io import writes_json
from sermon.analysis.proposes_from_transcript import TranscriptNotStored
from sermon.analysis.regrades_stored_cuts import DerivesStoredProposals
from sermon.pipeline import classify, segments
from sermon.store import Artifact, Recording, opens_store

RECORDING = "recording_20260920_094416"
ASR = "whisper-large-v3-turbo+words"
TAG = "stored.whole.v2"
DURATION = 9000.0

MODEL_PUNCH_IN = 4139.0
REFINED_PUNCH_IN = 4199.95
CHOSEN_PUNCH_OUT = 7566.4

BLOCKS = [
    {"start": 0.0, "end": 4150.0, "type": "music", "confidence": 0.9},
    {"start": 4150.0, "end": 7600.0, "type": "sermon", "confidence": 0.95},
    {"start": 7600.0, "end": 9000.0, "type": "other", "confidence": 0.8},
]
MODEL_SEGMENTS = [
    {"punch_in": MODEL_PUNCH_IN, "punch_out": 7599.0, "classification": "sermon",
     "confidence": 0.95}
]


@pytest.fixture
def injected_roots():
    held = (classify.DATA, classify.PROMPTS, segments.DATA_ROOT)
    yield
    classify.DATA, classify.PROMPTS, segments.DATA_ROOT = held


def utterance(start, text):
    words = [
        {"w": word.strip(".,"), "start": start + offset * 0.5, "end": start + offset * 0.5 + 0.4}
        for offset, word in enumerate(text.split())
    ]
    return {"start": start, "end": words[-1]["end"], "text": text, "words": words}


def spoken_service():
    return {
        "recording_id": RECORDING,
        "duration": DURATION,
        "started_at": "2026-09-20T09:44:16",
        "utterances": [
            utterance(float(start), "Good morning church we are glad you are here today")
            for start in range(0, int(DURATION), 60)
        ],
        "silences": [],
    }


def reasons_over(doc=None):
    return {"blocks": BLOCKS, "model_segments": MODEL_SEGMENTS}


def recording_row():
    return Recording(
        recording_id=RECORDING,
        object_key=f"{RECORDING}.flac",
        state="discovered",
        started_at=datetime(2026, 9, 20, 9, 44, 16, tzinfo=UTC),
        started_at_source="key",
        size_bytes=1,
        duration_seconds=DURATION,
    )


def data_root_holding_the_transcript(tmp_path, doc=None, transcript=True, diarization=None):
    data_root = tmp_path / "data"
    store = opens_store(data_root)
    recording = store.saves(recording_row())
    if transcript:
        writes_json(store, recording, "transcript", doc or spoken_service())
    if diarization is not None:
        writes_json(store, recording, "diarization", diarization)
    store.close()
    return data_root


def derives(tmp_path, data_root=None, **overrides):
    root = data_root or data_root_holding_the_transcript(tmp_path)
    store = opens_store(root)
    try:
        return DerivesCorpusEntry(
            store=store,
            corpus_root=overrides.pop("corpus_root", root / "corpus"),
            prompts_root=overrides.pop("prompts_root", tmp_path / "prompts"),
            asr_config=ASR,
            reasons=overrides.pop("reasons", reasons_over),
            **overrides,
        )(RECORDING)
    finally:
        store.close()


def block_file(tmp_path, tag=TAG):
    return json.loads(
        (tmp_path / "data" / "corpus" / "blocks" / f"{RECORDING}.{tag}.json").read_text()
    )


def test_the_stored_transcript_is_written_where_the_grader_reads_it(tmp_path, injected_roots):
    entry = derives(tmp_path)
    expected = tmp_path / "data" / "corpus" / "transcripts" / f"{RECORDING}.{ASR}.json"
    assert entry.transcript == expected
    assert json.loads(expected.read_text()) == spoken_service()


def test_the_classifier_answer_is_recorded_as_a_block_file(tmp_path, injected_roots):
    entry = derives(tmp_path)
    assert entry.blocks == (
        tmp_path / "data" / "corpus" / "blocks" / f"{RECORDING}.{TAG}.json"
    )
    recorded = block_file(tmp_path)
    assert recorded["recording_id"] == RECORDING
    assert recorded["asr_config"] == ASR
    assert recorded["config_id"] == TAG
    assert recorded["blocks"] == BLOCKS


def test_the_block_file_keeps_the_model_segments_the_store_does_not_hold(tmp_path, injected_roots):
    derives(tmp_path)
    recorded = block_file(tmp_path)
    assert recorded["model_segments"] == MODEL_SEGMENTS
    assert [held["punch_in"] for held in recorded["segments"]] == [MODEL_PUNCH_IN]
    assert [held["boundary_source"] for held in recorded["segments"]] == [
        "model-in/refined-out"
    ]


def test_a_block_file_without_the_model_segments_would_grade_a_different_cut(
    tmp_path, injected_roots
):
    """The gap design (a) could not close: Block rows alone lose the model's punch-in."""
    segments.DATA_ROOT = tmp_path
    (tmp_path / "diarization").mkdir()
    doc = spoken_service()
    segments._EDGE_CACHE.clear()
    led = segments.choose(MODEL_SEGMENTS, segments.derive(BLOCKS, doc), doc)
    segments._EDGE_CACHE.clear()
    refined = segments.choose([], segments.derive(BLOCKS, doc), doc)
    assert [held["punch_in"] for held in led] == [MODEL_PUNCH_IN]
    assert [held["punch_in"] for held in refined] == [REFINED_PUNCH_IN]


def test_the_recorded_entry_is_a_population_the_grader_walks(tmp_path, injected_roots):
    derives(tmp_path)
    walked = tuple(DerivesStoredProposals(corpus_root=tmp_path / "data" / "corpus")())
    assert [(found.recording_id, found.tag) for found in walked] == [(RECORDING, TAG)]
    assert [found.live for found in walked] == [((MODEL_PUNCH_IN, CHOSEN_PUNCH_OUT),)]
    assert [found.stored for found in walked] == [((MODEL_PUNCH_IN, CHOSEN_PUNCH_OUT),)]


def test_a_recording_with_no_stored_transcript_is_refused(tmp_path, injected_roots):
    root = data_root_holding_the_transcript(tmp_path, transcript=False)
    with pytest.raises(TranscriptNotStored):
        derives(tmp_path, data_root=root)
    assert not (root / "corpus" / "blocks").exists()


def test_a_block_file_already_written_is_never_redrawn(tmp_path, injected_roots):
    derives(tmp_path)
    first = block_file(tmp_path)
    with pytest.raises(BlockFileAlreadyWritten):
        derives(
            tmp_path,
            data_root=tmp_path / "data",
            reasons=lambda doc=None: {"blocks": [], "model_segments": []},
        )
    assert block_file(tmp_path) == first


def test_a_classifier_answer_holding_no_blocks_writes_no_block_file(tmp_path, injected_roots):
    with pytest.raises(NothingToBlock):
        derives(tmp_path, reasons=lambda doc=None: {"blocks": [], "model_segments": []})
    assert list((tmp_path / "data" / "corpus" / "blocks").glob("*.json")) == []


def test_the_diarization_artifact_is_placed_where_the_pipeline_looks(tmp_path, injected_roots):
    turns = {"turns": [{"start": 4151.5, "end": 7598.0, "speaker": "A"}]}
    root = data_root_holding_the_transcript(tmp_path, diarization=turns)
    derives(tmp_path, data_root=root)
    assert json.loads(
        (root / "corpus" / "diarization" / f"{RECORDING}.json").read_text()
    ) == turns


def test_a_corpus_without_a_diarization_directory_still_derives(tmp_path, injected_roots):
    derives(tmp_path)
    assert (tmp_path / "data" / "corpus" / "diarization").is_dir()


def test_the_tag_names_the_configuration_the_draw_came_from(tmp_path, injected_roots):
    derives(tmp_path, tag="t3-qwen3.6.whole.v2")
    recorded = block_file(tmp_path, tag="t3-qwen3.6.whole.v2")
    assert recorded["config_id"] == "t3-qwen3.6.whole.v2"


def test_the_store_rows_are_left_untouched(tmp_path, injected_roots):
    root = data_root_holding_the_transcript(tmp_path)
    derives(tmp_path, data_root=root)
    store = opens_store(root)
    try:
        assert [held.kind for held in store.lists(Artifact, recording_id=RECORDING)] == [
            "transcript"
        ]
        assert store.loads(Recording, RECORDING) == recording_row()
    finally:
        store.close()
