from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from test_aligns_edit import coarsened, excerpt, speech

from sermon.cli import ENVIRONMENT_FILE, aligns
from sermon.store import Artifact, CorpusPair, Recording, Segment, opens_store

RECORDING_ID = "recording_20260927_095721"
SECOND_ID = "recording_20260718_100700"
EDIT_NAME = "2026-09-27 - Hebrews 13.7-8.mp3"
MACHINE_CUT_NAME = "2026-09-06 - Hebrews 12.18-24.mp3"


def settings_file(root):
    (root / ENVIRONMENT_FILE).write_text(
        "\n".join(
            (
                f"SERMON_DATA_ROOT={root / 'data'}",
                "SERMON_OBJECT_STORE_ENDPOINT=https://s3.home.tpett.me",
                "SERMON_OBJECT_STORE_BUCKET=reformation-recordings",
                "SERMON_OBJECT_STORE_ACCESS_KEY_ID=not-a-real-key",
                "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY=not-a-real-secret",
                "SERMON_MODEL_ENDPOINT=http://mac-m1:11434",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "SERMON_DATA_ROOT": str(root / "data"),
        "SERMON_OBJECT_STORE_ENDPOINT": "https://s3.home.tpett.me",
        "SERMON_OBJECT_STORE_BUCKET": "reformation-recordings",
        "SERMON_OBJECT_STORE_ACCESS_KEY_ID": "not-a-real-key",
        "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY": "not-a-real-secret",
        "SERMON_MODEL_ENDPOINT": "http://mac-m1:11434",
    }


class RecordsLines:
    def __init__(self):
        self.lines = []

    def __call__(self, line=""):
        self.lines.append(str(line))

    def __str__(self):
        return "\n".join(self.lines)


class ReadsSynthetic:
    def __init__(self, envelopes, durations):
        self.envelopes = envelopes
        self.durations = durations

    def reads(self, source, tag):
        fine = self.envelopes[source.name]
        return coarsened(fine), fine

    def measures(self, path):
        return self.durations[Path(path).name]


def touched(root, *names):
    made = []
    for name in names:
        path = root / name
        path.write_bytes(b"")
        made.append(path)
    return made


def registered(root, recording_id, duration):
    store = opens_store(str(root / "data"))
    try:
        return store.saves(
            Recording(
                recording_id=recording_id,
                object_key=f"recordings/{recording_id}.flac",
                state="downloaded",
                started_at=datetime(2026, 9, 27, 9, 57, 21, tzinfo=UTC),
                started_at_source="key",
                size_bytes=1,
                duration_seconds=duration,
            )
        )
    finally:
        store.close()


def pairs_in(root):
    store = opens_store(str(root / "data"))
    try:
        return store.lists(CorpusPair)
    finally:
        store.close()


@pytest.fixture
def one_pair(tmp_path):
    settings = settings_file(tmp_path)
    source, edit = touched(tmp_path, "source.flac", EDIT_NAME)
    registered(tmp_path, RECORDING_ID, 900.0)
    envelope = speech(900)
    synthetic = ReadsSynthetic(
        {source.name: envelope, edit.name: excerpt(envelope, 301.5, 300)},
        {source.name: 900.0, edit.name: 300.0},
    )
    return settings, source, edit, synthetic


def run(settings, synthetic, prints, *arguments):
    return aligns(
        settings=settings,
        arguments=list(arguments),
        reads=synthetic.reads,
        measures=synthetic.measures,
        prints=prints,
    )


def test_aligning_writes_one_labelled_pair_with_the_derived_boundaries(tmp_path, one_pair):
    settings, source, edit, synthetic = one_pair
    outcome = run(
        settings, synthetic, RecordsLines(), RECORDING_ID, str(edit), "--source", str(source)
    )
    stored = pairs_in(tmp_path)
    assert outcome == 0
    assert len(stored) == 1
    assert stored[0].recording_id == RECORDING_ID
    assert stored[0].punch_in_seconds == pytest.approx(301.5, abs=0.01)
    assert stored[0].punch_out_seconds == pytest.approx(601.5, abs=0.01)
    assert (stored[0].provenance, stored[0].alignment) == ("human", "aligned")
    assert stored[0].drift_ppm is not None
    assert stored[0].punch_in_difficulty in ("easy", "moderate", "hard")


def test_the_report_names_the_boundaries_the_drift_and_the_difficulty(tmp_path, one_pair):
    settings, source, edit, synthetic = one_pair
    prints = RecordsLines()
    run(settings, synthetic, prints, RECORDING_ID, str(edit), "--source", str(source))
    spoken = str(prints)
    assert "301.5" in spoken
    assert "601.5" in spoken
    assert "ppm" in spoken
    assert "easy" in spoken or "moderate" in spoken or "hard" in spoken


def test_an_untrustworthy_alignment_records_the_exclusion_and_fails(tmp_path):
    settings = settings_file(tmp_path)
    source, edit = touched(tmp_path, "source.flac", EDIT_NAME)
    registered(tmp_path, RECORDING_ID, 900.0)
    synthetic = ReadsSynthetic(
        {source.name: speech(900), edit.name: speech(300, seed=99)},
        {source.name: 900.0, edit.name: 300.0},
    )
    prints = RecordsLines()
    outcome = run(
        settings, synthetic, prints, RECORDING_ID, str(edit), "--source", str(source)
    )
    stored = pairs_in(tmp_path)
    assert outcome == 1
    assert [(pair.recording_id, pair.alignment) for pair in stored] == [
        (RECORDING_ID, "cannot be aligned")
    ]
    assert "cannot be aligned" in str(prints)


def test_a_recorded_refusal_carries_no_boundaries_and_is_not_a_labelled_example(tmp_path):
    settings = settings_file(tmp_path)
    source, edit = touched(tmp_path, "source.flac", EDIT_NAME)
    registered(tmp_path, RECORDING_ID, 900.0)
    synthetic = ReadsSynthetic(
        {source.name: speech(900), edit.name: speech(300, seed=99)},
        {source.name: 900.0, edit.name: 300.0},
    )
    run(settings, synthetic, RecordsLines(), RECORDING_ID, str(edit), "--source", str(source))
    stored = pairs_in(tmp_path)
    assert [pair.provenance for pair in stored] == ["human"]
    assert (stored[0].punch_in_seconds, stored[0].punch_out_seconds) == (None, None)
    assert (stored[0].drift_ppm, stored[0].punch_in_difficulty) == (None, None)
    assert stored[0].covers_more_than_95_percent is False
    assert [pair for pair in stored if pair.labelled] == []


def test_a_refused_pair_is_remembered_so_it_is_not_attempted_forever(tmp_path):
    settings = settings_file(tmp_path)
    source, edit = touched(tmp_path, "source.flac", EDIT_NAME)
    registered(tmp_path, RECORDING_ID, 900.0)
    synthetic = ReadsSynthetic(
        {source.name: speech(900), edit.name: speech(300, seed=99)},
        {source.name: 900.0, edit.name: 300.0},
    )
    run(settings, synthetic, RecordsLines(), RECORDING_ID, str(edit), "--source", str(source))
    run(settings, synthetic, RecordsLines(), RECORDING_ID, str(edit), "--source", str(source))
    assert [pair.alignment for pair in pairs_in(tmp_path)] == ["cannot be aligned"]


def test_an_edit_that_is_not_a_contiguous_excerpt_records_that_verdict_and_fails(tmp_path):
    settings = settings_file(tmp_path)
    source, edit = touched(tmp_path, "source.flac", EDIT_NAME)
    registered(tmp_path, RECORDING_ID, 900.0)
    envelope = speech(900)
    spliced = np.concatenate(
        [excerpt(envelope, 100.0, 150.0), excerpt(envelope, 253.0, 150.0)]
    )
    synthetic = ReadsSynthetic(
        {source.name: envelope, edit.name: spliced},
        {source.name: 900.0, edit.name: 300.0},
    )
    prints = RecordsLines()
    outcome = run(
        settings, synthetic, prints, RECORDING_ID, str(edit), "--source", str(source)
    )
    stored = pairs_in(tmp_path)
    assert outcome == 1
    assert [(pair.recording_id, pair.alignment) for pair in stored] == [
        (RECORDING_ID, "not a contiguous excerpt")
    ]
    assert [pair for pair in stored if pair.labelled] == []
    assert "not a contiguous excerpt" in str(prints)


def test_a_machine_cut_is_recorded_as_published_and_never_aligned(tmp_path):
    settings = settings_file(tmp_path)
    source, edit = touched(tmp_path, "source.flac", MACHINE_CUT_NAME)
    registered(tmp_path, RECORDING_ID, 900.0)
    synthetic = ReadsSynthetic({}, {})
    prints = RecordsLines()
    outcome = run(
        settings, synthetic, prints, RECORDING_ID, str(edit), "--source", str(source)
    )
    stored = pairs_in(tmp_path)
    assert outcome == 0
    assert [pair.provenance for pair in stored] == ["machine"]
    assert (stored[0].alignment, stored[0].punch_in_seconds) == (None, None)
    assert "machine" in str(prints)


def test_an_output_the_system_rendered_from_its_own_proposal_is_a_machine_cut(tmp_path):
    settings = settings_file(tmp_path)
    source, edit = touched(tmp_path, "source.flac", EDIT_NAME)
    recording = registered(tmp_path, RECORDING_ID, 900.0)
    store = opens_store(str(tmp_path / "data"))
    try:
        segment = store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification="sermon",
                state="complete",
                boundary_source="model",
                span_start_seconds=300.0,
                span_end_seconds=600.0,
                punch_in_seconds=301.5,
                punch_out_seconds=601.5,
            )
        )
        store.saves(
            Artifact(
                recording_id=recording.recording_id,
                segment_id=segment.segment_id,
                kind="rendered_mp3",
                path=f"published/{EDIT_NAME}",
                size_bytes=1,
                checksum="0" * 64,
            )
        )
    finally:
        store.close()
    outcome = run(
        settings,
        ReadsSynthetic({}, {}),
        RecordsLines(),
        RECORDING_ID,
        str(edit),
        "--source",
        str(source),
    )
    assert outcome == 0
    assert [pair.provenance for pair in pairs_in(tmp_path)] == ["machine"]


def test_a_recording_nothing_names_is_refused(tmp_path, one_pair):
    settings, source, edit, synthetic = one_pair
    prints = RecordsLines()
    outcome = run(
        settings, synthetic, prints, "recording_19990101_000000", str(edit),
        "--source", str(source),
    )
    assert outcome == 1
    assert pairs_in(tmp_path) == []
    assert "recording_19990101_000000" in str(prints)


def test_an_edit_that_is_not_on_disk_is_refused(tmp_path, one_pair):
    settings, source, edit, synthetic = one_pair
    prints = RecordsLines()
    outcome = run(
        settings, synthetic, prints, RECORDING_ID, str(tmp_path / "gone.mp3"),
        "--source", str(source),
    )
    assert outcome == 1
    assert pairs_in(tmp_path) == []
    assert "gone.mp3" in str(prints)


def test_a_source_that_is_not_on_disk_is_refused(tmp_path, one_pair):
    settings, source, edit, synthetic = one_pair
    prints = RecordsLines()
    outcome = run(settings, synthetic, prints, RECORDING_ID, str(edit))
    assert outcome == 1
    assert pairs_in(tmp_path) == []
    assert "source" in str(prints)


def test_the_classification_the_pair_is_recorded_under_is_the_one_given(tmp_path, one_pair):
    settings, source, edit, synthetic = one_pair
    outcome = run(
        settings, synthetic, RecordsLines(), RECORDING_ID, str(edit),
        "--source", str(source), "--classification", "lesson",
    )
    assert outcome == 0
    assert [pair.classification for pair in pairs_in(tmp_path)] == ["lesson"]


def test_a_published_output_covering_almost_all_of_its_source_is_flagged(tmp_path):
    settings = settings_file(tmp_path)
    source, edit = touched(tmp_path, "source.flac", EDIT_NAME)
    registered(tmp_path, RECORDING_ID, 310.0)
    envelope = speech(310)
    synthetic = ReadsSynthetic(
        {source.name: envelope, edit.name: excerpt(envelope, 1.0, 305.0)},
        {source.name: 310.0, edit.name: 305.0},
    )
    outcome = run(
        settings, synthetic, RecordsLines(), RECORDING_ID, str(edit), "--source", str(source)
    )
    stored = pairs_in(tmp_path)
    assert outcome == 0
    assert [pair.covers_more_than_95_percent for pair in stored] == [True]


PART_ONE = "recording_20260718_081932"
PART_TWO = "recording_20260718_100850"
SPANNING_EDIT = "2026-07-18 - CT-Islam.mp3"


def two_part_recording(tmp_path, second_from):
    settings = settings_file(tmp_path)
    first, second, edit = touched(
        tmp_path, "part1.flac", "part2.flac", SPANNING_EDIT
    )
    registered(tmp_path, PART_ONE, 600.0)
    registered(tmp_path, PART_TWO, 600.0)
    one = speech(600, seed=11)
    two = speech(600, seed=12)
    spliced = np.concatenate([excerpt(one, 300.0, 300.0), excerpt(two, second_from, 300.0)])
    synthetic = ReadsSynthetic(
        {first.name: one, second.name: two, edit.name: spliced},
        {first.name: 600.0, second.name: 600.0, edit.name: 600.0},
    )
    return settings, synthetic, first, second, edit


def test_an_edit_spanning_two_recordings_is_written_as_two_pairs(tmp_path):
    settings, synthetic, first, second, edit = two_part_recording(tmp_path, 0.0)
    outcome = run(
        settings, synthetic, RecordsLines(), PART_ONE, PART_TWO, str(edit),
        "--source", str(first), "--source", str(second), "--classification", "seminar",
    )
    stored = sorted(pairs_in(tmp_path), key=lambda pair: pair.recording_id)
    assert outcome == 0
    assert [pair.recording_id for pair in stored] == [PART_ONE, PART_TWO]
    assert stored[0].punch_in_seconds == pytest.approx(300.0, abs=0.05)
    assert stored[1].punch_in_seconds == pytest.approx(0.0, abs=0.05)
    assert {pair.classification for pair in stored} == {"seminar"}


def test_a_spanning_edit_derives_no_boundaries_when_either_half_is_not_trustworthy(tmp_path):
    settings, synthetic, first, second, edit = two_part_recording(tmp_path, 0.0)
    synthetic.envelopes[second.name] = speech(600, seed=99)
    prints = RecordsLines()
    outcome = run(
        settings, synthetic, prints, PART_ONE, PART_TWO, str(edit),
        "--source", str(first), "--source", str(second),
    )
    spoken = str(prints)
    stored = sorted(pairs_in(tmp_path), key=lambda pair: pair.recording_id)
    assert outcome == 1
    assert [(pair.recording_id, pair.alignment) for pair in stored] == [
        (PART_ONE, "cannot be aligned"),
        (PART_TWO, "cannot be aligned"),
    ]
    assert [pair for pair in stored if pair.labelled] == []
    assert f"{PART_ONE}  punch-in" in spoken
    assert f"{PART_TWO}: cannot be aligned" in spoken


def test_one_source_per_named_recording_is_required(tmp_path):
    settings, synthetic, first, second, edit = two_part_recording(tmp_path, 0.0)
    prints = RecordsLines()
    outcome = run(
        settings, synthetic, prints, PART_ONE, PART_TWO, str(edit), "--source", str(first)
    )
    assert outcome == 1
    assert pairs_in(tmp_path) == []
