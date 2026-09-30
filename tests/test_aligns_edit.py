from pathlib import Path

import numpy as np
import pytest

from sermon.analysis.aligns_edit import (
    ALIGNED,
    COARSE_HZ,
    DISCONTINUOUS,
    FINE_HZ,
    UNALIGNABLE,
    AlignsPublishedEdit,
    DerivesPairsForEdit,
    GradesCutDifficulty,
    LocatesEditInSource,
    ReadsEnvelopes,
)

PER_COARSE_FRAME = FINE_HZ // COARSE_HZ


SYLLABLE_MS = 25


def speech(seconds, seed=7):
    """Smooth on a syllable, as a real envelope is; white noise decorrelates under drift."""
    generator = np.random.default_rng(seed)
    loud = generator.gamma(2.0, 0.3, size=int(seconds * FINE_HZ) + SYLLABLE_MS)
    smoothed = np.convolve(loud, np.ones(SYLLABLE_MS) / SYLLABLE_MS, mode="valid")
    return smoothed[: int(seconds * FINE_HZ)].astype(np.float32) + 0.01


def coarsened(fine):
    frames = len(fine) // PER_COARSE_FRAME
    return fine[: frames * PER_COARSE_FRAME].reshape(frames, PER_COARSE_FRAME).mean(axis=1)


def excerpt(source, start_seconds, length_seconds, stretch_ppm=0.0):
    wanted = np.arange(int(length_seconds * FINE_HZ)) * (1 + stretch_ppm / 1e6)
    return np.interp(
        start_seconds * FINE_HZ + wanted, np.arange(len(source)), source
    ).astype(np.float32)


def locates(source_fine, edit_fine):
    return LocatesEditInSource()(
        source_coarse=coarsened(source_fine),
        source_fine=source_fine,
        edit_coarse=coarsened(edit_fine),
        edit_fine=edit_fine,
    )


def test_a_contiguous_excerpt_is_located_within_its_source():
    source = speech(900)
    found = locates(source, excerpt(source, 301.5, 300))
    assert found.verdict == ALIGNED
    assert found.punch_in_seconds == pytest.approx(301.5, abs=0.01)


def test_the_offset_of_the_edit_within_the_source_is_backed_by_several_probes():
    source = speech(900)
    found = locates(source, excerpt(source, 301.5, 300))
    assert len(found.probes) >= 3
    assert min(probe.ncc for probe in found.probes) > 0.9


def test_the_punch_in_is_the_intercept_of_the_fit_not_the_middle_of_it():
    source = speech(900)
    found = locates(source, excerpt(source, 301.5, 300, stretch_ppm=-130.0))
    middle = float(np.median([probe.offset_seconds for probe in found.probes]))
    assert found.punch_in_seconds == pytest.approx(301.5, abs=0.01)
    assert abs(middle - 301.5) > 0.01


def test_the_drift_is_measured_rather_than_averaged_away():
    source = speech(900)
    found = locates(source, excerpt(source, 301.5, 300, stretch_ppm=-130.0))
    assert found.verdict == ALIGNED
    assert found.drift_ppm == pytest.approx(-130.0, abs=15.0)
    assert found.fit_residual_seconds < 0.01


def test_an_edit_longer_than_its_source_cannot_be_aligned():
    source = speech(200)
    found = locates(source, speech(400, seed=8))
    assert found.verdict == UNALIGNABLE
    assert any("longer than" in refusal for refusal in found.refusals)
    assert found.punch_in_seconds is None


def test_an_edit_that_matches_nothing_in_its_source_cannot_be_aligned():
    found = locates(speech(900), speech(300, seed=99))
    assert found.verdict == UNALIGNABLE
    assert found.refusals
    assert found.punch_in_seconds is None


def test_probes_that_do_not_fall_on_a_straight_line_are_not_a_contiguous_excerpt():
    source = speech(900)
    spliced = np.concatenate(
        [excerpt(source, 100.0, 150.0), excerpt(source, 253.0, 150.0)]
    )
    found = locates(source, spliced)
    assert found.verdict == DISCONTINUOUS
    assert any("straight line" in refusal for refusal in found.refusals)
    assert found.punch_in_seconds is None


def test_an_edit_that_starts_before_the_source_does_cannot_be_aligned():
    source = speech(900)
    edit = np.concatenate([speech(120, seed=42), excerpt(source, 0.0, 200.0)])
    found = locates(source, edit)
    assert found.verdict == UNALIGNABLE
    assert found.punch_in_seconds is None


SPEECH_LEVEL = 0.3
ROOM_LEVEL = 0.001
LEAD_SECONDS = 30.0
TALK_SECONDS = 60.0
GAP_AT = LEAD_SECONDS + TALK_SECONDS


def a_service_with_a_gap_of(seconds):
    """Quiet at both ends, because the quiet threshold is a percentile of the whole."""
    spans = (
        (ROOM_LEVEL, LEAD_SECONDS),
        (SPEECH_LEVEL, TALK_SECONDS),
        (ROOM_LEVEL, seconds),
        (SPEECH_LEVEL, TALK_SECONDS),
        (ROOM_LEVEL, LEAD_SECONDS),
    )
    return np.concatenate(
        [np.full(int(length * COARSE_HZ), level, dtype=np.float32) for level, length in spans]
    )


def test_ten_seconds_of_clean_silence_before_the_first_word_grades_the_cut_easy():
    graded = GradesCutDifficulty()(a_service_with_a_gap_of(10.0), GAP_AT + 5.0)
    assert graded.label == "easy"
    assert graded.quiet_milliseconds == 10_000


def test_two_seconds_of_clean_silence_grades_the_cut_easy():
    graded = GradesCutDifficulty()(a_service_with_a_gap_of(2.0), GAP_AT + 1.0)
    assert (graded.label, graded.quiet_milliseconds) == ("easy", 2_000)


def test_a_fifth_of_a_second_of_quiet_between_words_grades_the_cut_hard():
    graded = GradesCutDifficulty()(a_service_with_a_gap_of(0.2), GAP_AT + 0.1)
    assert (graded.label, graded.quiet_milliseconds) == ("hard", 200)


def test_half_a_second_of_quiet_between_words_grades_the_cut_moderate():
    graded = GradesCutDifficulty()(a_service_with_a_gap_of(0.5), GAP_AT + 0.25)
    assert (graded.label, graded.quiet_milliseconds) == ("moderate", 500)


def test_audio_at_the_cut_point_grades_it_hard():
    graded = GradesCutDifficulty()(a_service_with_a_gap_of(10.0), GAP_AT - 30.0)
    assert (graded.label, graded.quiet_milliseconds) == ("hard", 0)


class RecordsDecodes:
    def __init__(self, root):
        self.root = root
        self.decoded = []

    def __call__(self, source, destination, sr=16_000):
        if destination.exists() and destination.stat().st_size:
            return destination
        self.decoded.append(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        samples = (speech(12) * 6000).astype(np.int16)
        destination.write_bytes(samples.tobytes())
        return destination


def test_an_edit_is_decoded_once_for_both_envelopes(tmp_path, monkeypatch):
    from sermon.pipeline import audio

    decodes = RecordsDecodes(tmp_path)
    monkeypatch.setattr(audio, "decode", decodes)
    coarse, fine = ReadsEnvelopes(work=tmp_path)(tmp_path / "an-edit.mp3", "tag")
    assert len(decodes.decoded) == 1
    assert len(fine) == len(coarse) * PER_COARSE_FRAME


def test_the_decoded_audio_is_not_left_behind(tmp_path, monkeypatch):
    from sermon.pipeline import audio

    monkeypatch.setattr(audio, "decode", RecordsDecodes(tmp_path))
    ReadsEnvelopes(work=tmp_path)(tmp_path / "an-edit.mp3", "tag")
    assert list((tmp_path / "raw").glob("*.raw")) == []


class ReadsSyntheticEnvelopes:
    def __init__(self, **named):
        self.named = named

    def __call__(self, source, tag):
        fine = self.named[source.name]
        return coarsened(fine), fine


class ReadsSyntheticDurations:
    def __init__(self, **named):
        self.named = named

    def __call__(self, path):
        return self.named[path.name]


SOURCE = Path("a-source.flac")
EDIT = Path("an-edit.mp3")


def derives(source_fine, edit_fine, source_seconds, edit_seconds, **named):
    return AlignsPublishedEdit(
        work=Path("/nowhere"),
        reads=ReadsSyntheticEnvelopes(**{SOURCE.name: source_fine, EDIT.name: edit_fine}),
        measures=ReadsSyntheticDurations(
            **{SOURCE.name: source_seconds, EDIT.name: edit_seconds}
        ),
        **named,
    )("recording_20260927_095721", SOURCE, EDIT)


def test_the_punch_out_is_the_punch_in_plus_the_edit_duration():
    source = speech(900)
    derived = derives(source, excerpt(source, 301.5, 300), 900.0, 300.0)
    assert derived.trustworthy
    assert derived.punch_out_seconds == pytest.approx(601.5, abs=0.01)


def test_the_punch_out_accounts_for_the_drift_across_the_segment():
    source = speech(900)
    drifting = derives(source, excerpt(source, 301.5, 300, stretch_ppm=-130.0), 900.0, 300.0)
    straight = derives(source, excerpt(source, 301.5, 300), 900.0, 300.0)
    assert drifting.punch_out_seconds < straight.punch_out_seconds
    assert straight.punch_out_seconds - drifting.punch_out_seconds == pytest.approx(
        300.0 * 130e-6, abs=0.005
    )


def test_an_edit_that_runs_past_the_end_of_the_source_is_refused():
    source = speech(900)
    derived = derives(source, excerpt(source, 700.0, 190), 750.0, 190.0)
    assert not derived.trustworthy
    assert any("past the end" in refusal for refusal in derived.refusals)
    assert derived.punch_in_seconds is None


def test_each_boundary_is_graded_from_the_audio_around_it():
    source = speech(900)
    derived = derives(source, excerpt(source, 301.5, 300), 900.0, 300.0)
    assert derived.punch_in_difficulty.label in ("easy", "moderate", "hard")
    assert derived.punch_out_difficulty.label in ("easy", "moderate", "hard")


def test_an_alignment_that_is_not_trustworthy_carries_no_boundaries():
    derived = derives(speech(900), speech(300, seed=99), 900.0, 300.0)
    assert not derived.trustworthy
    assert (derived.punch_in_seconds, derived.punch_out_seconds) == (None, None)
    assert (derived.punch_in_difficulty, derived.punch_out_difficulty) == (None, None)


FIRST = Path("first.flac")
SECOND = Path("second.flac")
FIRST_ID = "recording_20260718_081932"
SECOND_ID = "recording_20260718_100850"


def spans(envelopes, durations):
    aligner = AlignsPublishedEdit(
        work=Path("/nowhere"),
        reads=ReadsSyntheticEnvelopes(**envelopes),
        measures=ReadsSyntheticDurations(**durations),
    )
    return DerivesPairsForEdit(
        aligns=aligner, measures=ReadsSyntheticDurations(**durations)
    )(((FIRST_ID, FIRST), (SECOND_ID, SECOND)), EDIT)


def two_sources(first_from, first_seconds, second_from, second_seconds):
    first = speech(600, seed=11)
    second = speech(600, seed=12)
    edit = np.concatenate(
        [
            excerpt(first, first_from, first_seconds),
            excerpt(second, second_from, second_seconds),
        ]
    )
    return (
        {FIRST.name: first, SECOND.name: second, EDIT.name: edit},
        {FIRST.name: 600.0, SECOND.name: 600.0, EDIT.name: first_seconds + second_seconds},
    )


def test_an_edit_spanning_two_sources_is_derived_as_one_pair_for_each():
    head, tail = spans(*two_sources(300.0, 300.0, 0.0, 300.0))
    assert (head.trustworthy, tail.trustworthy) == (True, True)
    assert head.punch_in_seconds == pytest.approx(300.0, abs=0.01)
    assert head.punch_out_seconds == pytest.approx(600.0, abs=0.05)
    assert tail.punch_in_seconds == pytest.approx(0.0, abs=0.05)
    assert tail.punch_out_seconds == pytest.approx(300.0, abs=0.05)


def test_the_second_source_keeps_whatever_the_human_dropped_from_its_head():
    head, tail = spans(*two_sources(300.0, 300.0, 120.0, 300.0))
    assert (head.trustworthy, tail.trustworthy) == (True, True)
    assert tail.punch_in_seconds == pytest.approx(120.0, abs=0.05)
    assert tail.punch_out_seconds == pytest.approx(420.0, abs=0.05)


def test_an_edit_that_stops_short_of_the_first_sources_end_is_refused_rather_than_guessed():
    head, tail = spans(*two_sources(100.0, 200.0, 0.0, 100.0))
    assert (head.trustworthy, tail.trustworthy) == (False, False)
    assert any("does not run to the end" in refusal for refusal in head.refusals)


def test_neither_source_is_written_when_the_head_of_the_edit_does_not_place():
    envelopes, durations = two_sources(300.0, 300.0, 0.0, 300.0)
    envelopes[EDIT.name] = speech(600, seed=99)
    head, tail = spans(envelopes, durations)
    assert (head.trustworthy, tail.trustworthy) == (False, False)
    assert tail.refusals


def test_an_edit_named_against_three_sources_is_refused():
    envelopes, durations = two_sources(300.0, 300.0, 0.0, 300.0)
    aligner = AlignsPublishedEdit(
        work=Path("/nowhere"),
        reads=ReadsSyntheticEnvelopes(**envelopes),
        measures=ReadsSyntheticDurations(**durations),
    )
    named = ((FIRST_ID, FIRST), (SECOND_ID, SECOND), ("recording_20260718_120000", SECOND))
    derived = DerivesPairsForEdit(
        aligns=aligner, measures=ReadsSyntheticDurations(**durations)
    )(named, EDIT)
    assert len(derived) == 3
    assert not any(pair.trustworthy for pair in derived)
