import importlib
import math

import pytest

from sermon.analysis import judges_cut
from sermon.analysis.judges_cut import (
    BETTER,
    JUDGE_DIGEST,
    JUDGE_VERSION,
    SILENCE_RUN_SECONDS,
    TOLERANCE_SPEECH_SECONDS,
    UNCHANGED,
    WORSE,
    JudgesCut,
    archived_whole,
    compares,
    pairs,
)


def transcript(*words, duration=None):
    return {
        "duration": duration,
        "utterances": [{"words": [{"w": "w", "start": start, "end": end} for start, end in words]}],
    }


SPOKEN = transcript(
    (0.0, 1.0), (1.0, 2.0),
    (7.0, 8.0), (8.0, 9.0),
    (9.5, 10.0),
    (12.0, 13.0),
    duration=20.0,
)
HUMAN = 4.0


def judged(at, human=HUMAN, spoken=SPOKEN):
    return JudgesCut(transcript=spoken)(at, human)


def test_a_cut_in_the_humans_pause_is_the_humans_cut_however_many_seconds_away():
    verdict = judged(6.5)
    assert verdict.same_pause
    assert verdict.speech_seconds == 0.0
    assert verdict.seconds_from_human == 2.5


def test_a_cut_across_a_word_is_a_different_cut_measured_in_speech():
    verdict = judged(9.25)
    assert not verdict.same_pause
    assert verdict.speech_seconds == 2.0
    assert verdict.seconds_from_human == 5.25


def test_a_gap_shorter_than_a_second_is_no_pause_to_share():
    assert SILENCE_RUN_SECONDS == 1.0
    verdict = judged(9.2, human=9.3)
    assert not verdict.same_pause
    assert verdict.speech_seconds == 0.0


def test_the_quiet_before_the_first_word_and_after_the_last_are_pauses():
    spoken = transcript((3.0, 4.0), (10.0, 11.0), duration=20.0)
    assert judged(1.0, human=2.0, spoken=spoken).same_pause
    assert judged(15.0, human=19.0, spoken=spoken).same_pause


def test_inside_a_word_and_clearance_are_diagnostics_that_rank_nothing():
    inside = judged(7.5)
    assert inside.inside_word
    assert inside.clearance_seconds == 0.0
    clear = judged(6.9)
    assert not clear.inside_word
    assert clear.clearance_seconds == pytest.approx(0.1)


def test_a_missed_cut_is_ranked_behind_every_found_one():
    missed = JudgesCut(transcript=SPOKEN)(None, HUMAN)
    assert missed.missed
    assert math.isinf(missed.speech_seconds)
    assert compares(judged(12.5), missed) == WORSE
    assert compares(missed, judged(12.5)) == BETTER


def test_moving_into_the_humans_pause_is_better_and_out_of_it_worse():
    assert compares(judged(9.25), judged(5.0)) == BETTER
    assert compares(judged(5.0), judged(9.25)) == WORSE


def test_moving_inside_the_humans_pause_changes_nothing():
    assert compares(judged(3.0), judged(6.0)) == UNCHANGED


def test_leaving_the_humans_pause_counts_however_little_speech_is_crossed():
    assert compares(judged(6.95), judged(7.05)) == WORSE


def test_outside_the_humans_pause_a_move_within_the_tolerance_is_unchanged():
    assert TOLERANCE_SPEECH_SECONDS == 0.1
    assert compares(judged(12.4), judged(12.45)) == UNCHANGED
    assert compares(judged(12.9), judged(12.4)) == BETTER
    assert compares(judged(12.4), judged(12.9)) == WORSE


def test_a_proposal_pairs_with_the_human_cut_it_overlaps_most():
    human = {"punch_in": 100.0, "punch_out": 200.0}
    assert pairs([(0.0, 90.0), (110.0, 205.0), (95.0, 150.0)], human) == (110.0, 205.0)


def test_a_proposal_covering_half_the_human_cut_or_less_is_not_paired():
    human = {"punch_in": 100.0, "punch_out": 200.0}
    assert pairs([(150.0, 300.0)], human) is None
    assert pairs([], human) is None


def test_a_recording_kept_almost_whole_is_archived_rather_than_cut():
    assert archived_whole({"source_duration": 100.0, "segments": [{"punch_in": 0.0, "punch_out": 96.0}]})
    assert not archived_whole({"source_duration": 100.0, "segments": [{"punch_in": 10.0, "punch_out": 90.0}]})


def test_the_judge_names_itself_by_version_and_by_a_digest_of_its_own_source():
    assert JUDGE_VERSION == 1
    assert len(JUDGE_DIGEST) == 12
    assert JUDGE_DIGEST == judges_cut.digest_of(judges_cut.__file__)


def test_editing_the_judge_changes_its_digest(tmp_path, monkeypatch):
    edited = tmp_path / "judges_cut.py"
    edited.write_text(open(judges_cut.__file__).read().replace("= 0.1\n", "= 0.2\n", 1))
    assert judges_cut.digest_of(edited) != JUDGE_DIGEST
    assert importlib.reload(judges_cut).JUDGE_DIGEST == JUDGE_DIGEST
