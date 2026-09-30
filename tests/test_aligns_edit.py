import numpy as np
import pytest

from sermon.analysis.aligns_edit import (
    ALIGNED,
    COARSE_HZ,
    DISCONTINUOUS,
    FINE_HZ,
    UNALIGNABLE,
    GradesCutDifficulty,
    LocatesEditInSource,
    ReadsEnvelopes,
)

PER_COARSE_FRAME = FINE_HZ // COARSE_HZ


def speech(seconds, seed=7):
    generator = np.random.default_rng(seed)
    return generator.gamma(2.0, 0.3, size=int(seconds * FINE_HZ)).astype(np.float32) + 0.01


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
        [excerpt(source, 100.0, 150.0), excerpt(source, 400.0, 150.0)]
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


def levels(*spans):
    return np.concatenate([np.full(int(seconds * COARSE_HZ), level) for level, seconds in spans])


LOUD = 0.3
QUIET = 0.0005


def test_ten_seconds_of_clean_silence_before_the_first_word_grades_the_cut_easy():
    graded = GradesCutDifficulty()(levels((LOUD, 60), (QUIET, 10), (LOUD, 60)), 65.0)
    assert graded.label == "easy"
    assert graded.quiet_milliseconds == 10_000


def test_two_seconds_of_clean_silence_grades_the_cut_easy():
    graded = GradesCutDifficulty()(levels((LOUD, 60), (QUIET, 2), (LOUD, 60)), 61.0)
    assert graded.label == "easy"


def test_a_quarter_of_a_second_of_quiet_between_words_grades_the_cut_hard():
    graded = GradesCutDifficulty()(levels((LOUD, 60), (QUIET, 0.2), (LOUD, 60)), 60.1)
    assert graded.label == "hard"


def test_half_a_second_of_quiet_between_words_grades_the_cut_moderate():
    graded = GradesCutDifficulty()(levels((LOUD, 60), (QUIET, 0.5), (LOUD, 60)), 60.25)
    assert graded.label == "moderate"


def test_audio_at_the_cut_point_grades_it_hard():
    graded = GradesCutDifficulty()(levels((LOUD, 60), (QUIET, 10), (LOUD, 60)), 30.0)
    assert (graded.label, graded.quiet_milliseconds) == ("hard", 0)


class RecordsDecodes:
    def __init__(self, root):
        self.root = root
        self.decoded = []

    def __call__(self, source, destination, sr=16_000):
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
