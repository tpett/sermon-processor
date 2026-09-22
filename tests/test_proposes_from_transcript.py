import ast
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sermon.analysis import (
    ClassifiesBlocks,
    DividesIntoBlocks,
    ProposesSegments,
    TranscribesRecording,
)
from sermon.analysis.measures_boundary_error import MeasuresBoundaryError
from sermon.analysis.proposes_from_transcript import (
    ASR_CONFIG,
    ChoosesBoundaries,
    ProposesFromStoredTranscript,
)
from sermon.jobs.analyzes_recording import (
    RecordingContents,
    RunsAnalyzeJob,
    StageFailed,
)
from sermon.pipeline import segments
from sermon.sends_notification import SendsNotification
from sermon.store import (
    Block,
    Job,
    Notification,
    Proposal,
    Recording,
    Reviewer,
    Segment,
    opens_store,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = PROJECT_ROOT / "src" / "sermon" / "analysis"
ANALYSIS_PATH = sorted(ANALYSIS_ROOT.glob("*.py")) + [
    PROJECT_ROOT / "src" / "sermon" / "jobs" / "analyzes_recording.py"
]
CORPUS = Path(os.environ.get("SERMON_SPIKE_DATA") or PROJECT_ROOT / "experiments" / "data")
GROUND_TRUTH = CORPUS / "groundtruth.json"
SPIKE_CONFIG = "u3-qwen3.6.whole.v2"
DEV_RECORDINGS = (
    "recording_20260412_102318",
    "recording_20260503_090012",
    "recording_20260510_102947",
    "recording_20260531_102925",
    "recording_20260614_094126",
    "recording_20260628_130014",
    "recording_20260712_103000",
    "recording_20260809_102935",
)

spike_data_required = pytest.mark.skipif(
    not (CORPUS / "transcripts").is_dir() or not (CORPUS / "blocks").is_dir(),
    reason=(
        f"{CORPUS}/transcripts and /blocks are gitignored and exist only in the primary "
        f"working tree; point SERMON_SPIKE_DATA at one that has them"
    ),
)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def reads_corpus_json(path):
    return json.loads(path.read_text())


def stored_transcript(recording_id):
    return reads_corpus_json(CORPUS / "transcripts" / f"{recording_id}.{ASR_CONFIG}.json")


def stored_reasoning(recording_id):
    return reads_corpus_json(CORPUS / "blocks" / f"{recording_id}.{SPIKE_CONFIG}.json")


def registers(store, recording_id, doc):
    return store.saves(
        Recording(
            recording_id=recording_id,
            object_key=f"{recording_id}.flac",
            state="downloaded",
            started_at=datetime.fromisoformat(doc["started_at"]).replace(tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=doc["duration"],
        )
    )


def proposes(store, recording_id, *, summarizer=None):
    doc = stored_transcript(recording_id)
    answer = stored_reasoning(recording_id)
    recording = registers(store, recording_id, doc)
    ProposesFromStoredTranscript(
        store=store,
        corpus_root=CORPUS,
        prompts_root=CORPUS.parent / "prompts",
        summarizer=summarizer,
        reasons=lambda _doc: answer,
    )(recording)
    return answer, store.lists(Segment, recording_id=recording_id)


def names_a_private_store_attribute(node):
    if isinstance(node, ast.Attribute):
        held = node.value
        named = getattr(held, "attr", None) or getattr(held, "id", None)
        return named == "store" and node.attr.startswith("_")
    if isinstance(node, ast.Call):
        called = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        return (
            called == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and str(node.args[1].value).startswith("_")
        )
    return False


def finds_private_store_attributes(source):
    return sorted(
        {
            node.attr if isinstance(node, ast.Attribute) else str(node.args[1].value)
            for node in ast.walk(ast.parse(source))
            if names_a_private_store_attribute(node)
        }
    )


def test_the_guard_sees_an_attribute_read_off_the_store():
    assert finds_private_store_attributes("x = self.store._first_word") == ["_first_word"]


def test_the_guard_sees_an_attribute_smuggled_through_getattr():
    assert finds_private_store_attributes(
        "x = getattr(self.store, '_last_word', None)"
    ) == ["_last_word"]


def test_the_guard_leaves_a_private_method_of_the_stage_alone():
    assert finds_private_store_attributes("self._records_punch_in_evidence(item, word)") == []


@pytest.mark.parametrize("module", ANALYSIS_PATH, ids=[path.name for path in ANALYSIS_PATH])
def test_no_analysis_stage_branches_on_an_attribute_injected_onto_the_store(module):
    assert finds_private_store_attributes(module.read_text(encoding="utf-8")) == []


def test_transcription_refuses_a_recording_whose_transcript_was_never_stored(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260412_102318",
            object_key="recording_20260412_102318.flac",
            state="downloaded",
            started_at=datetime(2026, 4, 12, 10, 23, 18, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=6352.913,
        )
    )
    with pytest.raises(StageFailed) as refused:
        TranscribesRecording(store=store)(recording)
    assert refused.value.stage == "transcription"


def test_blocking_refuses_a_recording_whose_transcript_was_never_stored(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260412_102318",
            object_key="recording_20260412_102318.flac",
            state="downloaded",
            started_at=datetime(2026, 4, 12, 10, 23, 18, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=6352.913,
        )
    )
    with pytest.raises(StageFailed) as refused:
        DividesIntoBlocks(store=store)(recording)
    assert refused.value.stage == "blocking"


@spike_data_required
@pytest.mark.parametrize("recording_id", DEV_RECORDINGS)
def test_blocking_keeps_the_spans_the_reasoning_stage_reported(store, recording_id):
    answer, _ = proposes(store, recording_id)
    blocks = store.lists(Block, recording_id=recording_id)
    assert [(round(item.start_seconds, 3), round(item.end_seconds, 3)) for item in blocks] == [
        (round(item["start"], 3), round(item["end"], 3)) for item in answer["blocks"]
    ]


@spike_data_required
@pytest.mark.parametrize("recording_id", DEV_RECORDINGS)
def test_classification_keeps_the_types_the_reasoning_stage_reported(store, recording_id):
    answer, _ = proposes(store, recording_id)
    blocks = store.lists(Block, recording_id=recording_id)
    assert [item.type for item in blocks] == [item["type"] for item in answer["blocks"]]


@spike_data_required
@pytest.mark.parametrize("recording_id", DEV_RECORDINGS)
def test_the_proposed_boundaries_are_the_ones_the_pipeline_library_derives(store, recording_id):
    answer, proposed = proposes(store, recording_id)
    doc = stored_transcript(recording_id)
    segments.DATA_ROOT = CORPUS
    segments._EDGE_CACHE.clear()
    expected = segments.choose(
        answer.get("model_segments") or [], segments.derive(answer["blocks"], doc), doc
    )
    assert [
        (item.punch_in_seconds, item.punch_out_seconds, item.boundary_source)
        for item in proposed
    ] == [
        (item["punch_in"], item["punch_out"], item["boundary_source"]) for item in expected
    ]


@spike_data_required
@pytest.mark.parametrize("recording_id", DEV_RECORDINGS)
def test_every_proposed_segment_carries_a_graded_proposal(store, recording_id):
    _, proposed = proposes(store, recording_id)
    graded = [
        self_reported
        for item in proposed
        for self_reported in store.lists(Proposal, segment_id=item.segment_id)
    ]
    assert len(graded) == len(proposed)
    assert all(item.punch_in_grade and item.punch_out_grade for item in graded)


@spike_data_required
def test_choosing_falls_back_to_refinement_when_the_reasoning_proposed_nothing():
    recording_id = "recording_20260412_102318"
    doc = stored_transcript(recording_id)
    answer = stored_reasoning(recording_id)
    chosen = ChoosesBoundaries(model_segments=())(answer["blocks"], doc)
    assert [item["boundary_source"] for item in chosen] == ["refined"]


def test_the_error_against_the_human_boundaries_is_reported_in_seconds():
    measured = MeasuresBoundaryError(ground_truth=GROUND_TRUTH)(
        "recording_20260412_102318", [(2021.0, 4880.46)]
    )
    assert [item.punch_in_error for item in measured] == [-0.075]
    assert [item.punch_out_error for item in measured] == [-2.211]
    assert [item.punch_in_difficulty for item in measured] == ["easy"]
    assert [item.punch_out_difficulty for item in measured] == ["easy"]


def test_a_boundary_pair_that_misses_the_human_segment_is_reported_as_not_found():
    measured = MeasuresBoundaryError(ground_truth=GROUND_TRUTH)(
        "recording_20260412_102318", [(10.0, 20.0)]
    )
    assert [item.found for item in measured] == [False]
    assert [item.true_punch_in for item in measured] == [2021.075]


def test_measuring_a_recording_the_corpus_never_labelled_reports_nothing():
    assert MeasuresBoundaryError(ground_truth=GROUND_TRUTH)("recording_19700101_000000", []) == ()


@spike_data_required
def test_proposing_twice_updates_the_proposal_rather_than_adding_another(store):
    recording_id = "recording_20260412_102318"
    _, first = proposes(store, recording_id)
    doc = stored_transcript(recording_id)
    recording = registers(store, recording_id, doc)
    ProposesSegments(store=store)(recording)
    assert [item.segment_id for item in store.lists(Segment, recording_id=recording_id)] == [
        item.segment_id for item in first
    ]


NOTHING_FABRICATED = RecordingContents(segments=())


def drains_the_analyze_job(store, recording_id, doc):
    recording = registers(store, recording_id, doc)
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    store.saves(
        Job(
            recording_id=recording_id,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{recording_id}",
            queued_at=recording.started_at,
        )
    )
    RunsAnalyzeJob(
        store=store,
        stages=lambda _name: None,
        notifies=SendsNotification(store=store),
        contents=NOTHING_FABRICATED,
        recording_id=recording_id,
        analyses=ProposesFromStoredTranscript(
            store=store,
            corpus_root=CORPUS,
            prompts_root=CORPUS.parent / "prompts",
            summarizer=None,
            reasons=lambda _doc: stored_reasoning(recording_id),
        ),
    )()


@spike_data_required
def test_draining_the_analyze_job_leaves_the_blocks_and_the_proposal_in_the_store(store):
    recording_id = "recording_20260412_102318"
    drains_the_analyze_job(store, recording_id, stored_transcript(recording_id))
    proposed = store.lists(Segment, recording_id=recording_id)
    assert len(store.lists(Block, recording_id=recording_id)) > 1
    assert [item.state for item in proposed] == ["proposed"]
    assert [item.boundary_source for item in proposed] == ["model-in/refined-out"]
    graded = store.lists(Proposal, segment_id=proposed[0].segment_id)
    assert [item.classification_confidence for item in graded] == ["high"]
    assert graded[0].evidence


@spike_data_required
def test_draining_the_analyze_job_leaves_the_recording_awaiting_review(store):
    recording_id = "recording_20260412_102318"
    drains_the_analyze_job(store, recording_id, stored_transcript(recording_id))
    assert store.loads(Recording, recording_id).state == "awaiting_review"
    assert [item.state for item in store.lists(Job, kind="analyze")] == ["succeeded"]
    assert [item.kind for item in store.lists(Notification, recording_id=recording_id)] == [
        "segment_proposed"
    ]


@spike_data_required
def test_draining_the_analyze_job_takes_the_job_for_the_recording_it_was_asked_about(store):
    recording_id = "recording_20260412_102318"
    other = "recording_20260503_090012"
    registers(store, other, stored_transcript(other))
    store.saves(
        Job(
            recording_id=other,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{other}",
            queued_at=datetime(2026, 5, 3, 9, 0, 12, tzinfo=UTC),
        )
    )
    drains_the_analyze_job(store, recording_id, stored_transcript(recording_id))
    assert {item.recording_id: item.state for item in store.lists(Job, kind="analyze")} == {
        other: "queued",
        recording_id: "succeeded",
    }
