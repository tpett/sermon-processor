import pytest

from sermon.scores_cut import (
    DEGRADED,
    EQUAL,
    IMPROVED,
    LONG_RUN_SECONDS,
    SAME_CUT,
    SILENCE_RUN_SECONDS,
    FindsSilenceRuns,
    ScoresCut,
)


def transcript(*utterances, silences=()):
    return {
        "utterances": [
            {"words": [{"w": word, "start": start, "end": end} for word, start, end in spoken]}
            for spoken in utterances
        ],
        "silences": [{"start": start, "end": end} for start, end in silences],
    }


def three_runs(silences=()):
    return transcript(
        [("one", 0.0, 1.0), ("two", 1.0, 2.0)],
        [("three", 7.0, 8.0), ("four", 8.0, 9.0)],
        [("five", 11.0, 12.0)],
        [("six", 50.0, 51.0)],
        silences=silences,
    )


IN_FIRST_RUN = 3.0
LATER_IN_FIRST_RUN = 6.0
IN_SECOND_RUN = 10.0
IN_LONG_RUN = 20.0
LATER_IN_LONG_RUN = 30.0
MID_WORD = 7.5
AFTER_EVERY_WORD = 100.0


def test_a_gap_between_words_of_at_least_a_second_is_a_run():
    found = FindsSilenceRuns()(three_runs())
    assert [(run.start, run.end) for run in found] == [(2.0, 7.0), (9.0, 11.0), (12.0, 50.0)]
    assert [run.index for run in found] == [0, 1, 2]


def test_the_run_threshold_is_the_named_constant():
    assert SILENCE_RUN_SECONDS == 1.0
    exactly = transcript([("one", 0.0, 1.0), ("two", 2.0, 3.0)])
    just_under = transcript([("one", 0.0, 1.0), ("two", 1.99, 3.0)])
    assert len(FindsSilenceRuns()(exactly)) == 1
    assert FindsSilenceRuns()(just_under) == ()


def test_the_first_and_the_last_gap_are_both_runs():
    edges = transcript(
        [("one", 0.0, 1.0)],
        [("two", 5.0, 6.0)],
        [("three", 9.0, 10.0)],
    )
    assert [(run.start, run.end) for run in FindsSilenceRuns()(edges)] == [(1.0, 5.0), (6.0, 9.0)]


def test_two_cuts_in_one_run_are_the_same_cut_however_far_apart_they_are():
    scored = ScoresCut(transcript=three_runs())(IN_FIRST_RUN, LATER_IN_FIRST_RUN)
    assert scored.same_run is True
    assert scored.speech_seconds == 0.0
    assert scored.verdict == SAME_CUT
    assert scored.delta_seconds == -3.0


def test_cuts_in_adjacent_runs_are_separated_by_the_speech_between_them():
    scored = ScoresCut(transcript=three_runs())(IN_SECOND_RUN, LATER_IN_FIRST_RUN)
    assert scored.same_run is False
    assert scored.speech_seconds == 2.0
    assert scored.verdict == DEGRADED


def test_a_cut_inside_a_word_is_in_no_run_and_reads_as_speech():
    scored = ScoresCut(transcript=three_runs())(MID_WORD, LATER_IN_FIRST_RUN)
    assert scored.proposed_run is None
    assert scored.in_speech is True
    assert scored.speech_seconds == 0.5
    assert scored.verdict == DEGRADED


def test_leaving_a_word_for_a_run_is_an_improvement():
    scored = ScoresCut(transcript=three_runs())(LATER_IN_FIRST_RUN, MID_WORD)
    assert scored.truth_in_speech is True
    assert scored.in_speech is False
    assert scored.verdict == IMPROVED


def test_a_cut_in_a_long_run_is_flagged_rather_than_refused():
    scored = ScoresCut(transcript=three_runs())(IN_LONG_RUN, LATER_IN_LONG_RUN)
    assert scored.long_run is True
    assert scored.same_run is True
    assert scored.verdict == SAME_CUT


def test_the_long_run_threshold_is_the_named_constant():
    assert LONG_RUN_SECONDS == 30.0
    exactly = transcript([("one", 0.0, 1.0)], [("two", 31.0, 32.0)])
    over = transcript([("one", 0.0, 1.0)], [("two", 31.01, 32.0)])
    assert ScoresCut(transcript=exactly)(15.0, 16.0).long_run is False
    assert ScoresCut(transcript=over)(15.0, 16.0).long_run is True


def test_an_empty_transcript_finds_no_run_and_measures_no_speech():
    scored = ScoresCut(transcript=transcript())(IN_FIRST_RUN, AFTER_EVERY_WORD)
    assert ScoresCut(transcript=transcript()).runs == ()
    assert scored.proposed_run is None
    assert scored.truth_run is None
    assert scored.in_speech is False
    assert scored.speech_seconds == 0.0


def test_a_cut_past_the_last_word_is_in_no_run_and_is_not_speech():
    scoring = ScoresCut(transcript=three_runs())
    assert scoring.run_of(AFTER_EVERY_WORD) is None
    scored = scoring(AFTER_EVERY_WORD, LATER_IN_FIRST_RUN)
    assert scored.in_speech is False
    assert scored.speech_seconds == 4.0


def test_a_cut_before_the_first_word_is_in_no_run():
    before_any_word = transcript([("one", 4.0, 5.0)], [("two", 9.0, 10.0)])
    assert ScoresCut(transcript=before_any_word).run_of(1.0) is None


def test_a_run_holds_its_own_edges_and_a_word_edge_is_not_speech():
    scoring = ScoresCut(transcript=three_runs())
    assert scoring.run_of(2.0).index == 0
    assert scoring.run_of(7.0).index == 0
    assert scoring(7.0, 2.0).in_speech is False


@pytest.mark.parametrize(
    ("one", "other"),
    [
        (IN_FIRST_RUN, LATER_IN_FIRST_RUN),
        (IN_FIRST_RUN, IN_SECOND_RUN),
        (MID_WORD, IN_LONG_RUN),
        (AFTER_EVERY_WORD, IN_FIRST_RUN),
        (IN_LONG_RUN, IN_LONG_RUN),
    ],
)
def test_landing_in_the_same_run_is_symmetric(one, other):
    scoring = ScoresCut(transcript=three_runs())
    assert scoring(one, other).same_run == scoring(other, one).same_run
    assert scoring(one, other).speech_seconds == scoring(other, one).speech_seconds


def test_speech_between_two_cuts_counts_an_overlapping_word_once():
    overlapping = transcript(
        [("one", 0.0, 1.0), ("two", 0.5, 2.0)],
        [("three", 7.0, 8.0)],
    )
    assert ScoresCut(transcript=overlapping)(0.0, 7.0).speech_seconds == 2.0


def test_the_signed_delta_is_reported_and_decides_nothing():
    scoring = ScoresCut(transcript=three_runs())
    far_apart_one_run = scoring(IN_LONG_RUN, LATER_IN_LONG_RUN)
    close_across_a_word = scoring(MID_WORD, LATER_IN_FIRST_RUN)
    assert far_apart_one_run.delta_seconds == -10.0
    assert far_apart_one_run.verdict == SAME_CUT
    assert close_across_a_word.delta_seconds == 1.5
    assert close_across_a_word.verdict == DEGRADED


def test_a_cut_that_did_not_move_is_equal():
    assert ScoresCut(transcript=three_runs())(IN_FIRST_RUN, IN_FIRST_RUN).verdict == EQUAL


def test_a_run_reports_whether_it_overlaps_a_stored_audio_silence():
    scoring = ScoresCut(transcript=three_runs(silences=[(2.5, 4.5)]))
    assert scoring.run_of(IN_FIRST_RUN).overlaps_audio_silence is True
    assert scoring.run_of(IN_SECOND_RUN).overlaps_audio_silence is False
    assert scoring(IN_FIRST_RUN, LATER_IN_FIRST_RUN).overlaps_audio_silence is True


def test_a_stored_audio_silence_never_keeps_a_cut_out_of_a_run():
    gated = ScoresCut(transcript=three_runs())(IN_FIRST_RUN, LATER_IN_FIRST_RUN)
    ungated = ScoresCut(transcript=three_runs(silences=[(2.5, 4.5)]))(
        IN_FIRST_RUN, LATER_IN_FIRST_RUN
    )
    assert gated.same_run == ungated.same_run
    assert gated.verdict == ungated.verdict
