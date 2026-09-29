import itertools
import json
import os
import statistics
from pathlib import Path

import pytest

from sermon.scores_cut import LONG_RUN_SECONDS, ScoresCut

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPIKE_DATA = Path(os.environ.get("SERMON_SPIKE_DATA") or PROJECT_ROOT / "experiments" / "data")
CANONICAL_ASR = "whisper-large-v3-turbo+words"

LABELLED_CUT_POINTS = 62
INSIDE_A_RUN = 49
INSIDE_A_WORD = 10
BETWEEN_WORDS = 3
INSIDE_A_LONG_RUN = 1
RUN_LENGTH_AT_A_HUMAN_CUT = (1.04, 2.54, 16.34, 43.74)

spike_data_required = pytest.mark.skipif(
    not all((SPIKE_DATA / name).is_dir() for name in ("blocks", "transcripts")),
    reason=(
        f"{SPIKE_DATA}/blocks and /transcripts are gitignored and exist only in the "
        f"primary working tree; point SERMON_SPIKE_DATA at one that has them"
    ),
)


def reads_human_cut_points():
    corpus = json.loads((SPIKE_DATA / "groundtruth.json").read_text())
    for recording in corpus["recordings"]:
        if not recording["segments"]:
            continue
        named = f"{recording['recording_id']}.{CANONICAL_ASR}.json"
        transcript = SPIKE_DATA / "transcripts" / named
        scoring = ScoresCut(transcript=json.loads(transcript.read_text()))
        for segment in recording["segments"]:
            for boundary in ("punch_in", "punch_out"):
                yield scoring, segment[boundary]


def places_every_human_cut_point():
    placed = {"run": [], "word": [], "gap": []}
    for scoring, at in reads_human_cut_points():
        run = scoring.run_of(at)
        if run is not None:
            placed["run"].append(run)
        elif scoring.speaks_at(at):
            placed["word"].append(at)
        else:
            placed["gap"].append(at)
    return placed


@spike_data_required
def test_word_gap_runs_hold_most_of_the_labelled_human_cut_points():
    placed = places_every_human_cut_point()
    counted = {where: len(found) for where, found in placed.items()}
    assert sum(counted.values()) == LABELLED_CUT_POINTS
    assert counted == {"run": INSIDE_A_RUN, "word": INSIDE_A_WORD, "gap": BETWEEN_WORDS}


@spike_data_required
def test_only_one_labelled_human_cut_point_sits_in_a_long_run():
    runs = places_every_human_cut_point()["run"]
    assert sum(run.seconds > LONG_RUN_SECONDS for run in runs) == INSIDE_A_LONG_RUN


@spike_data_required
def test_the_runs_holding_a_human_cut_point_are_short_enough_to_mean_something():
    lengths = sorted(run.seconds for run in places_every_human_cut_point()["run"])
    smallest, median, ninetieth, largest = RUN_LENGTH_AT_A_HUMAN_CUT
    assert (round(lengths[0], 2), round(lengths[-1], 2)) == (smallest, largest)
    assert round(statistics.median(lengths), 2) == median
    assert round(statistics.quantiles(lengths, n=10)[-1], 2) == ninetieth


@spike_data_required
def test_landing_in_the_same_run_is_symmetric_over_the_corpus():
    for scoring, at in reads_human_cut_points():
        for one, other in itertools.combinations(
            (at - 3.0, at - 0.5, at, at + 0.5, at + 3.0, at + 40.0), 2
        ):
            assert scoring(one, other).same_run == scoring(other, one).same_run


@spike_data_required
def test_two_cuts_in_one_run_are_separated_by_no_speech_over_the_corpus():
    for scoring, at in reads_human_cut_points():
        for one, other in itertools.combinations(
            (at - 3.0, at - 0.5, at, at + 0.5, at + 3.0, at + 40.0), 2
        ):
            scored = scoring(one, other)
            assert not scored.same_run or scored.speech_seconds == 0.0
