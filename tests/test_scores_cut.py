import pytest

from sermon.scores_cut import (
    DEGRADED,
    DIFFERENT_CUT,
    EQUAL,
    IMPROVED,
    LONG_RUN_SECONDS,
    SAME_CUT,
    EDGE_RUN_SECONDS,
    SILENCE_RUN_SECONDS,
    WORD_BUFFER_SECONDS,
    FindsSilenceRuns,
    ScoresCut,
)


def transcript(*utterances, silences=(), duration=None):
    return {
        "duration": duration,
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


def with_edges():
    return transcript(
        [("one", 4.0, 5.0), ("two", 5.0, 6.0)],
        [("three", 9.0, 10.0)],
        duration=30.0,
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
    assert scored.verdict == DIFFERENT_CUT


def test_two_cuts_placed_alike_in_different_gaps_are_neither_better_nor_worse():
    between_words = transcript(
        [("one", 0.0, 1.0)], [("two", 1.5, 2.5)], [("three", 3.0, 4.0)], duration=4.0
    )
    scoring = ScoresCut(transcript=between_words)
    for scored in (scoring(2.7, 1.2), scoring(1.2, 2.7)):
        assert scored.proposed_run is scored.truth_run is None
        assert scored.in_speech is scored.truth_in_speech is False
        assert scored.speech_seconds == 1.0
        assert scored.verdict == DIFFERENT_CUT


def test_two_cuts_inside_different_words_are_neither_better_nor_worse():
    scored = ScoresCut(transcript=three_runs())(MID_WORD, 11.5)
    assert scored.in_speech is scored.truth_in_speech is True
    assert scored.verdict == DIFFERENT_CUT


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


def test_a_cut_before_the_first_word_is_in_the_head_run():
    before_any_word = transcript([("one", 4.0, 5.0)], [("two", 9.0, 10.0)])
    assert ScoresCut(transcript=before_any_word).run_of(1.0).index == 0


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


IN_HEAD_RUN = 1.0
IN_TAIL_RUN = 20.0
LATER_IN_TAIL_RUN = 29.0
BEYOND_THE_RECORDING = 40.0


def test_the_region_before_the_first_word_is_the_first_run():
    found = FindsSilenceRuns()(with_edges())
    assert [(run.index, run.start, run.end) for run in found] == [
        (0, 0.0, 4.0),
        (1, 6.0, 9.0),
        (2, 10.0, 30.0),
    ]


def test_the_region_after_the_last_word_runs_to_the_recorded_duration():
    scoring = ScoresCut(transcript=with_edges())
    assert scoring.run_of(IN_TAIL_RUN).seconds == 20.0
    assert scoring.run_of(LATER_IN_TAIL_RUN) == scoring.run_of(IN_TAIL_RUN)


def test_the_edge_run_threshold_is_the_named_constant():
    assert EDGE_RUN_SECONDS == 1.0
    just_under = transcript([("one", 0.99, 2.0)], [("two", 5.0, 6.0)], duration=6.99)
    assert [(run.start, run.end) for run in FindsSilenceRuns()(just_under)] == [(2.0, 5.0)]


def test_a_transcript_that_does_not_say_how_long_it_is_has_no_tail_run():
    assert ScoresCut(transcript=three_runs()).run_of(AFTER_EVERY_WORD) is None


def test_a_cut_past_the_recorded_duration_is_in_no_run():
    assert ScoresCut(transcript=with_edges()).run_of(BEYOND_THE_RECORDING) is None


def test_two_cuts_in_the_tail_run_are_the_same_cut():
    scored = ScoresCut(transcript=with_edges())(LATER_IN_TAIL_RUN, IN_TAIL_RUN)
    assert scored.same_run is True
    assert scored.verdict == SAME_CUT


def test_a_cut_beyond_the_recording_is_not_the_same_cut_as_one_inside_the_tail():
    scored = ScoresCut(transcript=with_edges())(BEYOND_THE_RECORDING, IN_TAIL_RUN)
    assert scored.same_run is False
    assert scored.verdict == DEGRADED


def test_leaving_a_word_gap_run_for_the_tail_run_is_a_different_cut():
    scored = ScoresCut(transcript=with_edges())(IN_TAIL_RUN, 7.0)
    assert scored.same_run is False
    assert scored.speech_seconds == 1.0
    assert scored.verdict == DIFFERENT_CUT


def test_a_cut_in_the_head_run_is_in_a_run():
    scoring = ScoresCut(transcript=with_edges())
    assert scoring.run_of(IN_HEAD_RUN).index == 0
    assert scoring(IN_HEAD_RUN, 0.0).same_run is True


def test_two_cuts_far_apart_in_no_run_at_all_are_not_the_same_cut():
    scored = ScoresCut(transcript=with_edges())(BEYOND_THE_RECORDING, BEYOND_THE_RECORDING + 20.0)
    assert scored.speech_seconds == 0.0
    assert scored.same_run is False
    assert scored.verdict == DIFFERENT_CUT


def test_two_cuts_in_one_sub_threshold_gap_are_still_the_same_cut():
    narrow = transcript([("one", 0.0, 1.0), ("two", 1.5, 2.5)], duration=2.5)
    scored = ScoresCut(transcript=narrow)(1.1, 1.4)
    assert scored.proposed_run is None
    assert scored.speech_seconds == 0.0
    assert scored.verdict == SAME_CUT


AFTER_A_WORD_ENDS = 2.03
BEFORE_A_WORD_STARTS = 6.97


def test_the_word_buffer_is_the_named_constant():
    assert WORD_BUFFER_SECONDS == 0.250


def test_a_cut_in_a_run_but_within_the_buffer_of_a_word_crowds_it():
    scoring = ScoresCut(transcript=three_runs())
    assert scoring(AFTER_A_WORD_ENDS, IN_FIRST_RUN).within_buffer is True
    assert scoring(BEFORE_A_WORD_STARTS, IN_FIRST_RUN).within_buffer is True
    assert scoring(IN_FIRST_RUN, AFTER_A_WORD_ENDS).within_buffer is False
    assert scoring(IN_FIRST_RUN, AFTER_A_WORD_ENDS).truth_within_buffer is True


def test_a_cut_on_a_word_edge_is_within_the_buffer():
    assert ScoresCut(transcript=three_runs())(2.0, IN_FIRST_RUN).within_buffer is True


def test_a_cut_exactly_the_buffer_from_a_word_is_clear_of_it():
    scoring = ScoresCut(transcript=three_runs())
    assert scoring(2.25, IN_FIRST_RUN).within_buffer is False
    assert scoring(2.249, IN_FIRST_RUN).within_buffer is True


def test_a_cut_just_inside_a_word_is_mid_word_rather_than_within_the_buffer():
    scored = ScoresCut(transcript=three_runs())(7.02, IN_FIRST_RUN)
    assert scored.in_speech is True
    assert scored.within_buffer is False


def test_within_one_run_clearing_the_buffer_is_an_improvement():
    scoring = ScoresCut(transcript=three_runs())
    assert scoring(IN_FIRST_RUN, AFTER_A_WORD_ENDS).verdict == IMPROVED
    assert scoring(AFTER_A_WORD_ENDS, IN_FIRST_RUN).verdict == DEGRADED


def test_two_cuts_within_the_buffer_at_either_end_of_one_run_are_the_same_cut():
    scored = ScoresCut(transcript=three_runs())(AFTER_A_WORD_ENDS, BEFORE_A_WORD_STARTS)
    assert scored.verdict == SAME_CUT


def test_the_buffer_can_be_widened():
    widened = ScoresCut(transcript=three_runs(), buffer_seconds=0.500)
    assert widened(2.4, IN_FIRST_RUN).within_buffer is True
    assert ScoresCut(transcript=three_runs())(2.4, IN_FIRST_RUN).within_buffer is False
