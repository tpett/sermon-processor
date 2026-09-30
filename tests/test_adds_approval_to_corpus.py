from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.analysis import DerivesGroundTruth
from sermon.analysis.adds_approval_to_corpus import AddsApprovalToCorpus
from sermon.store import CorpusPair, Recording, Segment, opens_store

RECORDING_ID = "recording_20260927_095721"


@pytest.fixture
def store(tmp_path):
    opened = opens_store(data_root=tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def adjusted(store):
    store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=f"recordings/{RECORDING_ID}.flac",
            state="reviewed",
            started_at=datetime(2026, 9, 27, 9, 57, 21, tzinfo=UTC),
            started_at_source="key",
            size_bytes=885996288,
            duration_seconds=6791.608,
        )
    )
    return store.saves(
        Segment(
            recording_id=RECORDING_ID,
            classification="sermon",
            state="complete",
            boundary_source="human",
            span_start_seconds=3000.0,
            span_end_seconds=5600.0,
            punch_in_seconds=3055.026,
            punch_out_seconds=5597.35,
        )
    )


def test_an_adjusted_approval_becomes_a_labelled_pair(store, adjusted):
    added = AddsApprovalToCorpus(store=store)(adjusted)
    assert (added.punch_in_seconds, added.punch_out_seconds) == (3055.026, 5597.35)
    assert (added.provenance, added.alignment) == ("human", "aligned")
    assert added.classification == "sermon"


def test_an_untouched_approval_does_not_become_a_labelled_example(store, adjusted):
    untouched = store.saves(replace(adjusted, boundary_source="model"))
    assert AddsApprovalToCorpus(store=store)(untouched) is None
    assert store.lists(CorpusPair) == []


def test_a_refined_boundary_is_the_machines_work_not_the_reviewers(store, adjusted):
    refined = store.saves(replace(adjusted, boundary_source="model-in/refined-out"))
    assert AddsApprovalToCorpus(store=store)(refined) is None
    assert store.lists(CorpusPair) == []


def test_a_segment_nobody_has_approved_yet_is_not_ground_truth(store, adjusted):
    proposed = store.saves(replace(adjusted, state="proposed"))
    assert AddsApprovalToCorpus(store=store)(proposed) is None
    assert store.lists(CorpusPair) == []


def test_adding_the_same_approval_twice_corrects_the_record_rather_than_doubling_it(
    store, adjusted
):
    AddsApprovalToCorpus(store=store)(adjusted)
    moved = store.saves(replace(adjusted, punch_out_seconds=5600.0))
    AddsApprovalToCorpus(store=store)(moved)
    assert [pair.punch_out_seconds for pair in store.lists(CorpusPair)] == [5600.0]


def test_the_difficulty_of_a_cut_is_not_invented_where_no_audio_was_read(store, adjusted):
    added = AddsApprovalToCorpus(store=store)(adjusted)
    assert (added.punch_in_difficulty, added.punch_out_difficulty) == (None, None)


def aligned_by_measurement(store, **fields):
    return DerivesGroundTruth(store=store)(
        RECORDING_ID,
        punch_in=3055.026,
        punch_out=5597.35,
        classification="sermon",
        drift_ppm=-0.2,
        punch_in_difficulty="easy",
        punch_out_difficulty="moderate",
        **fields,
    )


def test_a_reapproval_keeps_the_drift_and_difficulties_the_alignment_measured(store, adjusted):
    aligned_by_measurement(store)
    added = AddsApprovalToCorpus(store=store)(adjusted)
    assert added.drift_ppm == -0.2
    assert (added.punch_in_difficulty, added.punch_out_difficulty) == ("easy", "moderate")
    assert added.labelled is True


def test_a_boundary_the_reviewer_moved_loses_only_its_own_difficulty(store, adjusted):
    aligned_by_measurement(store)
    moved = store.saves(replace(adjusted, punch_out_seconds=5600.0))
    added = AddsApprovalToCorpus(store=store)(moved)
    assert (added.punch_in_seconds, added.punch_out_seconds) == (3055.026, 5600.0)
    assert (added.punch_in_difficulty, added.punch_out_difficulty) == ("easy", None)
    assert added.drift_ppm == -0.2


def test_a_refusal_replaces_the_record_because_a_verdict_is_not_an_absence(store, adjusted):
    AddsApprovalToCorpus(store=store)(adjusted)
    refused = DerivesGroundTruth(store=store)(
        RECORDING_ID,
        punch_in=None,
        punch_out=None,
        classification="sermon",
        alignment="not a contiguous excerpt",
    )
    assert (refused.punch_in_seconds, refused.punch_out_seconds) == (None, None)
    assert (refused.drift_ppm, refused.punch_in_difficulty) == (None, None)
    assert refused.alignment == "not a contiguous excerpt"
    assert refused.labelled is False
    assert len(store.lists(CorpusPair)) == 1
