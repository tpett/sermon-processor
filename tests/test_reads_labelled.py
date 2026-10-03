import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.analysis.measures_boundary_error import (
    ArchivesRatherThanCuts,
    MeasuresBoundaryError,
    ReadsLabelledFromFile,
    ReadsLabelledFromStore,
    SourceDurationUnknown,
)
from sermon.store import CorpusPair, Recording, Segment, opens_store

RECORDING_ID = "recording_20260927_095721"
SOURCE_SECONDS = 6791.608
PUNCH_IN = 3055.0258
PUNCH_OUT = 5597.3505
LABEL = "Hebrews 13.7-8"


@pytest.fixture
def store(tmp_path):
    opened = opens_store(data_root=tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def recorded(store):
    return store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=f"recordings/{RECORDING_ID}.flac",
            state="reviewed",
            started_at=datetime(2026, 9, 27, 9, 57, 21, tzinfo=UTC),
            started_at_source="key",
            size_bytes=885996288,
            duration_seconds=SOURCE_SECONDS,
        )
    )


def aligned(**overrides):
    return replace(
        CorpusPair(
            recording_id=RECORDING_ID,
            classification="sermon",
            provenance="human",
            alignment="aligned",
            punch_in_seconds=PUNCH_IN,
            punch_out_seconds=PUNCH_OUT,
            drift_ppm=-0.2,
            punch_in_difficulty="easy",
            punch_out_difficulty="moderate",
        ),
        **overrides,
    )


def reads(store, recording_id=RECORDING_ID):
    return ReadsLabelledFromStore(store=store)(recording_id)


def test_an_aligned_human_pair_is_read_as_one_labelled_segment(store, recorded):
    store.saves(aligned())
    labelled = reads(store)
    assert labelled["recording_id"] == RECORDING_ID
    assert labelled["segments"] == [
        {
            "punch_in": PUNCH_IN,
            "punch_out": PUNCH_OUT,
            "difficulty_in": {"label": "easy"},
            "difficulty_out": {"label": "moderate"},
        }
    ]


def test_the_source_duration_is_joined_from_the_recording(store, recorded):
    store.saves(aligned())
    assert reads(store)["source_duration"] == SOURCE_SECONDS


def test_the_publication_label_is_what_the_measurement_displays(store, recorded):
    store.saves(aligned())
    store.saves(
        Segment(
            recording_id=RECORDING_ID,
            classification="sermon",
            state="complete",
            span_start_seconds=3000.0,
            span_end_seconds=5600.0,
            punch_in_seconds=PUNCH_IN,
            punch_out_seconds=PUNCH_OUT,
            label=LABEL,
        )
    )
    assert reads(store)["desktop_label"] == LABEL


def test_a_pair_with_no_published_label_is_displayed_by_its_recording_id(store, recorded):
    store.saves(aligned())
    assert reads(store)["desktop_label"] == RECORDING_ID


def test_two_classifications_of_one_recording_are_two_labelled_segments(store, recorded):
    store.saves(aligned())
    store.saves(
        aligned(
            classification="lesson",
            punch_in_seconds=600.0,
            punch_out_seconds=2400.0,
        )
    )
    assert [held["punch_in"] for held in reads(store)["segments"]] == [600.0, PUNCH_IN]


def test_a_recording_with_no_pair_at_all_reads_nothing(store, recorded):
    assert reads(store) is None


def test_a_recording_the_store_has_never_heard_of_reads_nothing(store, recorded):
    store.saves(aligned())
    assert reads(store, "recording_20260101_000000") is None


def test_a_pair_that_could_not_be_aligned_is_never_ground_truth(store, recorded):
    store.saves(
        CorpusPair(
            recording_id=RECORDING_ID,
            classification="sermon",
            provenance="human",
            alignment="cannot be aligned",
        )
    )
    assert reads(store) is None


def test_a_pair_that_is_not_a_contiguous_excerpt_is_never_ground_truth(store, recorded):
    store.saves(
        CorpusPair(
            recording_id=RECORDING_ID,
            classification="sermon",
            provenance="human",
            alignment="not a contiguous excerpt",
        )
    )
    assert reads(store) is None


def test_a_machine_cut_is_never_ground_truth(store, recorded):
    store.saves(
        CorpusPair(
            recording_id=RECORDING_ID,
            classification="sermon",
            provenance="machine",
        )
    )
    assert reads(store) is None


def test_an_untouched_approval_is_never_ground_truth(store, recorded):
    store.saves(
        CorpusPair(
            recording_id=RECORDING_ID,
            classification="sermon",
            provenance="machine",
        )
    )
    store.saves(
        Segment(
            recording_id=RECORDING_ID,
            classification="sermon",
            state="complete",
            boundary_source="model",
            span_start_seconds=3000.0,
            span_end_seconds=5600.0,
            punch_in_seconds=3060.83,
            punch_out_seconds=5594.575,
            label=LABEL,
        )
    )
    assert reads(store) is None


def test_a_pair_covering_more_than_95_percent_of_its_source_is_never_ground_truth(
    store, recorded
):
    store.saves(aligned(covers_more_than_95_percent=True))
    assert reads(store) is None


def test_a_refusal_beside_a_labelled_pair_leaves_only_the_labelled_one(store, recorded):
    store.saves(aligned())
    store.saves(
        CorpusPair(
            recording_id=RECORDING_ID,
            classification="lesson",
            provenance="human",
            alignment="cannot be aligned",
        )
    )
    assert [held["punch_in"] for held in reads(store)["segments"]] == [PUNCH_IN]


def test_every_admitted_pair_satisfies_the_labelled_rule(store, recorded):
    store.saves(aligned())
    store.saves(
        CorpusPair(
            recording_id=RECORDING_ID, classification="meeting", provenance="machine"
        )
    )
    store.saves(
        CorpusPair(
            recording_id=RECORDING_ID,
            classification="lesson",
            provenance="human",
            alignment="cannot be aligned",
        )
    )
    store.saves(
        aligned(
            classification="seminar",
            punch_in_seconds=100.0,
            punch_out_seconds=SOURCE_SECONDS,
            covers_more_than_95_percent=True,
        )
    )
    assert len(store.lists(CorpusPair, recording_id=RECORDING_ID)) == 4
    admitted = [held["punch_in"] for held in reads(store)["segments"]]
    assert admitted == [
        pair.punch_in_seconds for pair in store.lists(CorpusPair) if pair.labelled
    ]
    assert admitted == [PUNCH_IN]


def ground_truth(tmp_path):
    path = tmp_path / "groundtruth.json"
    path.write_text(
        json.dumps(
            {
                "recordings": [
                    {
                        "recording_id": RECORDING_ID,
                        "desktop_label": LABEL,
                        "source_duration": SOURCE_SECONDS,
                        "segments": [
                            {
                                "punch_in": PUNCH_IN,
                                "punch_out": PUNCH_OUT,
                                "difficulty_in": {"label": "easy"},
                                "difficulty_out": {"label": "moderate"},
                            }
                        ],
                    }
                ]
            }
        )
    )
    return path


def test_the_frozen_file_stays_readable_as_a_second_source(tmp_path):
    labelled = ReadsLabelledFromFile(ground_truth=ground_truth(tmp_path))(RECORDING_ID)
    assert labelled["desktop_label"] == LABEL
    assert labelled["segments"][0]["punch_in"] == PUNCH_IN


def test_the_frozen_file_says_nothing_about_a_recording_it_does_not_hold(tmp_path):
    assert ReadsLabelledFromFile(ground_truth=ground_truth(tmp_path))("nothing") is None


def test_the_stored_corpus_answers_the_archive_check(store, recorded):
    store.saves(aligned(punch_in_seconds=10.0, punch_out_seconds=SOURCE_SECONDS))
    archives = ArchivesRatherThanCuts(reads=ReadsLabelledFromStore(store=store))
    assert archives(RECORDING_ID) is True
    assert ArchivesRatherThanCuts(reads=lambda recording_id: None)(RECORDING_ID) is False


def test_a_stored_pair_whose_recording_was_never_measured_is_refused(store, recorded):
    store.saves(replace(recorded, duration_seconds=None))
    store.saves(aligned(punch_in_seconds=0.0, punch_out_seconds=SOURCE_SECONDS))
    archives = ArchivesRatherThanCuts(reads=ReadsLabelledFromStore(store=store))
    with pytest.raises(SourceDurationUnknown, match=RECORDING_ID):
        archives(RECORDING_ID)


def test_the_stored_corpus_answers_the_boundary_measurement(store, recorded):
    store.saves(aligned())
    measures = MeasuresBoundaryError(reads=ReadsLabelledFromStore(store=store))
    measured = measures(RECORDING_ID, [(3060.83, 5594.575)])
    assert [held.true_punch_in for held in measured] == [PUNCH_IN]
    assert measured[0].label == RECORDING_ID
    assert measured[0].punch_in_error == round(3060.83 - PUNCH_IN, 3)


def test_a_boundary_measurement_against_the_frozen_file_is_unchanged(tmp_path):
    measures = MeasuresBoundaryError(ground_truth=ground_truth(tmp_path))
    measured = measures(RECORDING_ID, [(3060.83, 5594.575)])
    assert [held.label for held in measured] == [LABEL]
    assert measured[0].punch_out_error == round(5594.575 - PUNCH_OUT, 3)


def test_a_segment_belonging_to_another_recording_does_not_name_this_one(store, recorded):
    store.saves(aligned())
    store.saves(
        replace(
            Recording(
                recording_id="recording_20260920_095721",
                object_key="recordings/recording_20260920_095721.flac",
                state="reviewed",
                started_at=datetime(2026, 9, 20, 9, 57, 21, tzinfo=UTC),
                started_at_source="key",
                size_bytes=1,
            ),
            duration_seconds=100.0,
        )
    )
    store.saves(
        Segment(
            recording_id="recording_20260920_095721",
            classification="sermon",
            state="complete",
            span_start_seconds=0.0,
            span_end_seconds=50.0,
            punch_in_seconds=1.0,
            punch_out_seconds=49.0,
            label="Another week",
        )
    )
    assert reads(store)["desktop_label"] == RECORDING_ID
