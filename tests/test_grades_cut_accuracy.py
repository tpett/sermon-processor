import json
from datetime import UTC, date, datetime

import pytest

from sermon import cli
from sermon.analysis.measures_boundary_error import SourceDurationUnknown

from sermon.analysis.grades_cut_accuracy import (
    GradesCorpusAccuracy,
    GradesCutAccuracy,
    compares,
)
from sermon.scores_cut import DEGRADED, DIFFERENT_CUT, EQUAL, IMPROVED, SAME_CUT, ScoresCut
from sermon.store import CorpusPair, Recording, Segment, opens_store

RECORDING = "recording_20260628_130014"
LABEL = "2026-06-28 - Members Meeting"

WORDS = [
    ("one", 4.0, 5.0),
    ("two", 5.0, 6.0),
    ("three", 11.0, 12.0),
    ("four", 12.0, 13.0),
    ("five", 18.0, 19.0),
]
HEAD_RUN = (0.0, 4.0)
FIRST_GAP_RUN = (6.0, 11.0)
SECOND_GAP_RUN = (13.0, 18.0)
TAIL_RUN = (19.0, 30.0)

HUMAN_IN = 8.0
HUMAN_OUT = 25.0


def transcript():
    return {
        "recording_id": RECORDING,
        "duration": 30.0,
        "utterances": [
            {"start": start, "end": end, "text": word,
             "words": [{"w": word, "start": start, "end": end}]}
            for word, start, end in WORDS
        ],
        "silences": [],
    }


SOURCE_SECONDS = 30.0


def ground_truth(tmp_path, punch_in=HUMAN_IN, punch_out=HUMAN_OUT,
                 source_duration=SOURCE_SECONDS):
    path = tmp_path / "groundtruth.json"
    path.write_text(
        json.dumps(
            {
                "recordings": [
                    {
                        "recording_id": RECORDING,
                        "desktop_label": LABEL,
                        "source_duration": source_duration,
                        "segments": [
                            {
                                "punch_in": punch_in,
                                "punch_out": punch_out,
                                "difficulty_in": {"label": "easy"},
                                "difficulty_out": {"label": "hard"},
                            }
                        ],
                    }
                ]
            }
        )
    )
    return path


def grades(tmp_path, proposed, **labelled):
    return GradesCutAccuracy(ground_truth=ground_truth(tmp_path, **labelled))(
        RECORDING, transcript(), proposed
    )


def test_a_proposal_in_the_same_run_as_the_human_cut_is_accurate(tmp_path):
    graded = grades(tmp_path, [(7.0, 26.0)])
    assert [cut.boundary for cut in graded] == ["punch_in", "punch_out"]
    assert graded[0].score.same_run is True
    assert graded[0].score.speech_seconds == 0.0
    assert graded[1].score.same_run is True


def test_a_proposal_a_run_away_reports_the_speech_between_it_and_the_human(tmp_path):
    graded = grades(tmp_path, [(14.0, 26.0)])
    assert graded[0].score.same_run is False
    assert graded[0].score.speech_seconds == 2.0


def test_the_human_cut_and_the_difficulty_are_carried_beside_the_score(tmp_path):
    graded = grades(tmp_path, [(7.0, 26.0)])
    assert (graded[0].human, graded[0].difficulty) == (HUMAN_IN, "easy")
    assert (graded[1].human, graded[1].difficulty) == (HUMAN_OUT, "hard")
    assert graded[0].label == LABEL


def test_a_proposal_that_overlaps_no_labelled_segment_is_not_found(tmp_path):
    graded = grades(tmp_path, [(0.0, 0.5)])
    assert [cut.found for cut in graded] == [False, False]
    assert [cut.score for cut in graded] == [None, None]
    assert graded[0].human == HUMAN_IN


def test_a_human_cut_spanning_the_whole_recording_is_not_a_cut_decision(tmp_path):
    assert grades(tmp_path, [(7.0, 26.0)], punch_in=0.0, punch_out=SOURCE_SECONDS) == ()


def test_a_human_cut_that_leaves_a_fifth_of_the_recording_out_is_still_a_cut(tmp_path):
    graded = grades(tmp_path, [(7.0, 26.0)], punch_in=0.0, punch_out=24.0)
    assert [cut.boundary for cut in graded] == ["punch_in", "punch_out"]


@pytest.mark.parametrize("source_duration", [None, 0.0])
def test_a_recording_whose_source_duration_is_unknown_is_refused_rather_than_graded(
    tmp_path, source_duration
):
    with pytest.raises(SourceDurationUnknown, match="source duration is unknown"):
        grades(
            tmp_path,
            [(7.0, 26.0)],
            punch_in=0.0,
            punch_out=SOURCE_SECONDS,
            source_duration=source_duration,
        )


def test_a_recording_with_no_labelled_segment_grades_nothing(tmp_path):
    accuracy = GradesCutAccuracy(ground_truth=ground_truth(tmp_path))
    assert accuracy("recording_20260101_000000", transcript(), [(7.0, 26.0)]) == ()


def test_the_proposal_is_paired_to_the_human_segment_by_overlap(tmp_path):
    graded = grades(tmp_path, [(0.0, 1.0), (7.0, 26.0), (28.0, 29.0)])
    assert graded[0].proposed == 7.0
    assert graded[1].proposed == 26.0


def scores(tmp_path, proposed):
    return grades(tmp_path, [proposed])


def test_a_cut_that_did_not_move_is_equal(tmp_path):
    before = scores(tmp_path, (7.0, 26.0))
    assert compares(before[0], before[0]) == EQUAL


def test_a_cut_that_moved_closer_to_the_human_run_improved(tmp_path):
    before = scores(tmp_path, (14.0, 26.0))
    after = scores(tmp_path, (7.0, 26.0))
    assert compares(before[0], after[0]) == IMPROVED
    assert compares(after[0], before[0]) == DEGRADED


def test_a_cut_that_moved_inside_the_human_run_is_the_same_cut(tmp_path):
    before = scores(tmp_path, (7.0, 26.0))
    after = scores(tmp_path, (10.0, 26.0))
    assert before[0].score.same_run and after[0].score.same_run
    assert compares(before[0], after[0]) == SAME_CUT


def test_a_cut_that_moved_further_from_the_human_in_speech_seconds_degraded(tmp_path):
    before = scores(tmp_path, (11.5, 26.0))
    after = scores(tmp_path, (13.0, 26.0))
    assert (before[0].score.speech_seconds, after[0].score.speech_seconds) == (0.5, 2.0)
    assert compares(before[0], after[0]) == DEGRADED
    assert compares(after[0], before[0]) == IMPROVED


def test_landing_in_a_word_is_reported_but_does_not_outrank_being_closer(tmp_path):
    before = scores(tmp_path, (13.0, 26.0))
    after = scores(tmp_path, (12.5, 26.0))
    assert after[0].score.in_speech is True
    assert after[0].score.speech_seconds < before[0].score.speech_seconds
    assert compares(before[0], after[0]) == IMPROVED


def test_two_proposals_equally_far_from_the_human_are_the_same_cut(tmp_path):
    before = scores(tmp_path, (13.0, 26.0))
    after = scores(tmp_path, (14.0, 26.0))
    assert before[0].score.speech_seconds == after[0].score.speech_seconds == 2.0
    assert before[0].score.same_run == after[0].score.same_run is False
    assert compares(before[0], after[0]) == SAME_CUT


def test_a_cut_that_moved_closer_between_gaps_placed_alike_improved(tmp_path):
    packed = transcript()
    packed["utterances"] = [
        {"start": start, "end": end, "text": word,
         "words": [{"w": word, "start": start, "end": end}]}
        for word, start, end in [("a", 4.0, 5.0), ("b", 5.5, 6.5), ("c", 7.0, 8.0), ("d", 8.5, 9.5)]
    ]
    grading = GradesCutAccuracy(ground_truth=ground_truth(tmp_path, punch_in=8.2))
    before = grading(RECORDING, packed, [(5.2, 26.0)])
    after = grading(RECORDING, packed, [(6.7, 26.0)])
    assert (before[0].score.speech_seconds, after[0].score.speech_seconds) == (2.0, 1.0)
    assert compares(before[0], after[0]) == IMPROVED
    assert compares(after[0], before[0]) == DEGRADED
    assert ScoresCut(transcript=packed)(6.7, 5.2).verdict == DIFFERENT_CUT


def test_inside_the_human_run_a_cut_clear_of_a_word_beats_one_within_the_buffer(tmp_path):
    before = scores(tmp_path, (6.02, 26.0))
    after = scores(tmp_path, (7.0, 26.0))
    assert before[0].score.same_run and after[0].score.same_run
    assert before[0].score.within_buffer is True
    assert compares(before[0], after[0]) == IMPROVED
    assert compares(after[0], before[0]) == DEGRADED


def test_within_the_buffer_in_the_human_run_still_beats_clear_in_another_run(tmp_path):
    before = scores(tmp_path, (14.0, 26.0))
    after = scores(tmp_path, (10.98, 26.0))
    assert after[0].score.within_buffer is True
    assert compares(before[0], after[0]) == IMPROVED


def test_two_cuts_within_the_buffer_of_the_human_run_are_the_same_cut(tmp_path):
    before = scores(tmp_path, (6.02, 26.0))
    after = scores(tmp_path, (10.98, 26.0))
    assert compares(before[0], after[0]) == SAME_CUT


def test_a_proposal_that_stops_being_found_degraded(tmp_path):
    before = scores(tmp_path, (7.0, 26.0))
    after = scores(tmp_path, (0.0, 0.5))
    assert compares(before[0], after[0]) == DEGRADED
    assert compares(after[0], before[0]) == IMPROVED


def test_a_proposal_that_was_never_found_and_still_is_not_is_equal(tmp_path):
    never = scores(tmp_path, (0.0, 0.5))
    assert compares(never[0], never[0]) == EQUAL


ASR = "an-asr-config"
TAG = "a-tag.whole.v2"
BLOCK = f"{RECORDING}.{TAG}.json"


def stages_corpus(root, tag=TAG, **labelled):
    (root / "blocks").mkdir(parents=True, exist_ok=True)
    (root / "transcripts").mkdir(parents=True, exist_ok=True)
    (root / "blocks" / f"{RECORDING}.{tag}.json").write_text(
        json.dumps(
            {
                "recording_id": RECORDING,
                "asr_config": ASR,
                "blocks": [{"start": 0.0, "end": 30.0, "type": "sermon"}],
                "model_segments": [],
                "segments": [{"punch_in": 7.0, "punch_out": 26.0}],
            }
        )
    )
    (root / "transcripts" / f"{RECORDING}.{ASR}.json").write_text(json.dumps(transcript()))
    ground_truth(root, **labelled)
    return root


def walks(root, live, before=None, tag=None):
    return GradesCorpusAccuracy(
        corpus_root=root,
        derives=lambda stored, doc: [
            {"punch_in": punch_in, "punch_out": punch_out} for punch_in, punch_out in live
        ],
        before=before,
        tag=tag,
    )()


def test_the_corpus_walk_grades_live_proposals_against_the_human_cut(tmp_path):
    stages_corpus(tmp_path)
    graded = walks(tmp_path, live=[(7.0, 26.0)])
    assert [(one.recording_id, one.tag) for one in graded] == [(RECORDING, TAG)]
    assert [cut.score.same_run for cut in graded[0].cuts] == [True, True]
    assert graded[0].was == ()


def test_the_corpus_walk_reads_the_ground_truth_beside_the_blocks(tmp_path):
    stages_corpus(tmp_path)
    graded = walks(tmp_path, live=[(14.0, 26.0)])
    assert graded[0].cuts[0].human == HUMAN_IN
    assert graded[0].cuts[0].score.speech_seconds == 2.0


def test_an_archived_whole_recording_is_left_out_of_the_walk(tmp_path):
    stages_corpus(tmp_path, punch_in=0.0, punch_out=SOURCE_SECONDS)
    assert walks(tmp_path, live=[(7.0, 26.0)]) == ()


def test_a_recording_whose_source_duration_is_unknown_is_named_and_left_out_of_the_walk(
    tmp_path,
):
    stages_corpus(tmp_path, source_duration=None)
    refused = []
    graded = GradesCorpusAccuracy(
        corpus_root=tmp_path,
        derives=lambda stored, doc: [{"punch_in": 7.0, "punch_out": 26.0}],
        refuses=refused.append,
    )()
    assert graded == ()
    assert [one.recording_id for one in refused] == [RECORDING]


def test_a_walk_with_nowhere_to_report_a_refusal_does_not_drop_it_silently(tmp_path):
    stages_corpus(tmp_path, source_duration=None)
    with pytest.raises(SourceDurationUnknown):
        walks(tmp_path, live=[(7.0, 26.0)])


def test_a_recording_with_no_labelled_segment_is_left_out_of_the_walk(tmp_path):
    stages_corpus(tmp_path)
    (tmp_path / "groundtruth.json").write_text(json.dumps({"recordings": []}))
    assert walks(tmp_path, live=[(7.0, 26.0)]) == ()


def test_a_tag_filter_selects_which_stored_proposals_are_graded(tmp_path):
    stages_corpus(tmp_path)
    stages_corpus(tmp_path, tag="another-tag.perblock.v2")
    assert len(walks(tmp_path, live=[(7.0, 26.0)])) == 2
    assert [one.tag for one in walks(tmp_path, live=[(7.0, 26.0)], tag="whole")] == [TAG]


def test_a_baseline_is_graded_against_the_human_cut_beside_the_live_proposal(tmp_path):
    stages_corpus(tmp_path)
    graded = walks(tmp_path, live=[(7.0, 26.0)], before={BLOCK: [(14.0, 26.0)]})
    assert graded[0].was[0].proposed == 14.0
    assert graded[0].cuts[0].proposed == 7.0
    assert [verdict for _, _, verdict in graded[0].changes] == [IMPROVED, EQUAL]


def test_a_baseline_that_says_nothing_about_a_proposal_leaves_it_ungraded(tmp_path):
    stages_corpus(tmp_path)
    graded = walks(tmp_path, live=[(7.0, 26.0)], before={"some-other-file.json": [(1.0, 2.0)]})
    assert graded[0].was == ()
    assert graded[0].changes == ()


def runs(root, live, *flags):
    collected = []
    code = cli.regrades(
        arguments=["--corpus", str(root), "--corpus-regime", *flags],
        prints=collected.append,
        derives=lambda stored, doc: [
            {"punch_in": punch_in, "punch_out": punch_out} for punch_in, punch_out in live
        ],
    )
    return code, "\n".join(collected)


def test_the_command_grades_each_cut_point_against_the_human_by_default(tmp_path):
    stages_corpus(tmp_path)
    code, printed = runs(tmp_path, [(7.0, 26.0)])
    assert code == 0
    assert RECORDING in printed and TAG in printed
    assert "human      8.000" in printed
    assert "same run" in printed
    assert "1 proposal graded, 2 cut points: 2 in the human's run" in printed
    assert "0 mid-word, 0 not found" in printed


def test_the_command_counts_the_cuts_within_the_buffer_of_a_word(tmp_path):
    stages_corpus(tmp_path)
    code, printed = runs(tmp_path, [(6.02, 26.0)])
    assert code == 0
    assert "0 not found, 1 within 250 ms of a word" in printed
    assert "speech   0.000 s within the buffer" in printed


def test_the_command_reports_the_speech_between_a_proposal_and_the_human(tmp_path):
    stages_corpus(tmp_path)
    code, printed = runs(tmp_path, [(14.0, 26.0)])
    assert code == 0
    assert "speech   2.000 s" in printed
    assert "1 in the human's run" in printed


def test_the_command_reports_a_labelled_segment_the_proposal_missed(tmp_path):
    stages_corpus(tmp_path)
    code, printed = runs(tmp_path, [(0.0, 0.5)])
    assert code == 1
    assert "NOT FOUND" in printed
    assert "2 not found" in printed
    assert "nothing could be scored against a human cut" in printed


def test_a_corpus_where_some_proposals_are_found_still_exits_zero(tmp_path):
    stages_corpus(tmp_path)
    stages_corpus(tmp_path, tag="another-tag.whole.v2")
    code, printed = runs(tmp_path, [(7.0, 26.0)])
    assert code == 0
    assert "0 not found" in printed


def test_a_baseline_turns_the_command_into_an_improved_or_degraded_report(tmp_path):
    stages_corpus(tmp_path)
    (tmp_path / "before.json").write_text(
        json.dumps({BLOCK: {"chosen": [{"punch_in": 14.0, "punch_out": 26.0}]}})
    )
    code, printed = runs(tmp_path, [(7.0, 26.0)], "--before", str(tmp_path / "before.json"))
    assert code == 0
    assert IMPROVED in printed
    assert "before       14.000" in printed
    assert "after         7.000" in printed
    assert "2 cut points, 1 moved: 1 improved, 0 degraded, 0 same cut" in printed


def test_a_baseline_exits_non_zero_when_a_cut_moved_away_from_the_human(tmp_path):
    stages_corpus(tmp_path)
    (tmp_path / "before.json").write_text(
        json.dumps({BLOCK: {"chosen": [{"punch_in": 7.0, "punch_out": 26.0}]}})
    )
    code, printed = runs(tmp_path, [(14.0, 26.0)], "--before", str(tmp_path / "before.json"))
    assert code == 1
    assert DEGRADED in printed
    assert "1 degraded" in printed


def test_a_baseline_identical_to_the_live_output_reports_no_change_and_exits_zero(tmp_path):
    stages_corpus(tmp_path)
    (tmp_path / "before.json").write_text(
        json.dumps({BLOCK: {"chosen": [{"punch_in": 7.0, "punch_out": 26.0}]}})
    )
    code, printed = runs(tmp_path, [(7.0, 26.0)], "--before", str(tmp_path / "before.json"))
    assert code == 0
    assert "2 cut points, 0 moved: 0 improved, 0 degraded, 0 same cut" in printed


def test_saving_the_live_proposals_writes_a_baseline_the_command_can_read_back(tmp_path):
    stages_corpus(tmp_path)
    saved = tmp_path / "saved.json"
    code, _ = runs(tmp_path, [(7.0, 26.0)], "--save", str(saved))
    assert code == 0
    assert json.loads(saved.read_text()) == {
        BLOCK: {"chosen": [{"punch_in": 7.0, "punch_out": 26.0}]}
    }
    again, printed = runs(tmp_path, [(7.0, 26.0)], "--before", str(saved))
    assert again == 0
    assert "0 moved" in printed


def test_the_drift_mode_never_decides_the_exit_code(tmp_path):
    stages_corpus(tmp_path)
    code, printed = runs(tmp_path, [(12.5, 26.0)], "--drift")
    assert code == 0
    assert "drift" in printed
    assert DEGRADED in printed


def test_a_tag_filter_reaches_the_command(tmp_path):
    stages_corpus(tmp_path)
    stages_corpus(tmp_path, tag="another-tag.perblock.v2")
    _, printed = runs(tmp_path, [(7.0, 26.0)], "--tag", "perblock")
    assert "another-tag.perblock.v2" in printed
    assert "1 proposal graded" in printed


def unlabelled_corpus(root, tag=TAG):
    stages_corpus(root, tag=tag)
    (root / "groundtruth.json").write_text(json.dumps({"recordings": []}))
    return root


def stages_store(root, duration=SOURCE_SECONDS):
    data_root = root / "data"
    store = opens_store(data_root)
    store.saves(
        Recording(
            recording_id=RECORDING,
            object_key=f"recordings/{RECORDING}.flac",
            state="reviewed",
            started_at=datetime(2026, 6, 28, 13, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=duration,
        )
    )
    store.close()
    return data_root


def labels(data_root, punch_in=HUMAN_IN, punch_out=HUMAN_OUT, **overrides):
    store = opens_store(data_root)
    store.saves(
        CorpusPair(
            recording_id=RECORDING,
            classification="sermon",
            provenance=overrides.pop("provenance", "human"),
            alignment=overrides.pop("alignment", "aligned"),
            punch_in_seconds=punch_in,
            punch_out_seconds=punch_out,
            punch_in_difficulty="easy",
            punch_out_difficulty="hard",
            **overrides,
        )
    )
    store.close()


def test_the_command_grades_against_the_stored_corpus_when_given_a_store(tmp_path):
    unlabelled_corpus(tmp_path)
    labels(stages_store(tmp_path))
    code, printed = runs(tmp_path, [(7.0, 26.0)], "--store", str(tmp_path / "data"))
    assert code == 0
    assert "1 proposal graded, 2 cut points: 2 in the human's run" in printed
    assert "human      8.000" in printed


def test_the_frozen_file_is_still_what_the_command_reads_without_a_store(tmp_path):
    unlabelled_corpus(tmp_path)
    labels(stages_store(tmp_path))
    code, printed = runs(tmp_path, [(7.0, 26.0)])
    assert code == 1
    assert "0 proposals graded, 0 cut points" in printed


def test_a_newly_added_pair_changes_the_reported_number(tmp_path):
    unlabelled_corpus(tmp_path)
    data_root = stages_store(tmp_path)
    before_code, before = runs(tmp_path, [(7.0, 26.0)], "--store", str(data_root))
    labels(data_root)
    after_code, after = runs(tmp_path, [(7.0, 26.0)], "--store", str(data_root))
    assert (before_code, after_code) == (1, 0)
    assert "0 proposals graded, 0 cut points" in before
    assert "1 proposal graded, 2 cut points: 2 in the human's run" in after


def unlabelled_pair(data_root, provenance="human", alignment="cannot be aligned"):
    store = opens_store(data_root)
    store.saves(
        CorpusPair(
            recording_id=RECORDING,
            classification="sermon",
            provenance=provenance,
            alignment=alignment,
        )
    )
    store.close()


def test_a_refused_pair_added_to_the_store_changes_no_reported_number(tmp_path):
    unlabelled_corpus(tmp_path)
    data_root = stages_store(tmp_path)
    unlabelled_pair(data_root)
    code, printed = runs(tmp_path, [(7.0, 26.0)], "--store", str(data_root))
    assert code == 1
    assert "0 proposals graded, 0 cut points" in printed


def test_a_machine_pair_added_to_the_store_changes_no_reported_number(tmp_path):
    unlabelled_corpus(tmp_path)
    data_root = stages_store(tmp_path)
    unlabelled_pair(data_root, provenance="machine", alignment=None)
    code, printed = runs(tmp_path, [(7.0, 26.0)], "--store", str(data_root))
    assert code == 1
    assert "0 proposals graded, 0 cut points" in printed


def test_the_command_names_the_stored_corpus_it_graded_against(tmp_path):
    unlabelled_corpus(tmp_path)
    data_root = stages_store(tmp_path)
    labels(data_root)
    _, printed = runs(tmp_path, [(7.0, 26.0)], "--store", str(data_root))
    assert f"against {data_root}" in printed
    assert "groundtruth.json" not in printed


def test_a_recording_archived_whole_is_left_out_of_the_stored_corpus_walk(tmp_path):
    unlabelled_corpus(tmp_path)
    data_root = stages_store(tmp_path)
    labels(data_root, punch_in=0.0, punch_out=SOURCE_SECONDS)
    code, printed = runs(tmp_path, [(7.0, 26.0)], "--store", str(data_root))
    assert code == 1
    assert "0 proposals graded, 0 cut points" in printed


def test_the_stored_corpus_reaches_the_regression_gate(tmp_path):
    unlabelled_corpus(tmp_path)
    data_root = stages_store(tmp_path)
    labels(data_root)
    (tmp_path / "before.json").write_text(
        json.dumps({BLOCK: {"chosen": [{"punch_in": 7.0, "punch_out": 26.0}]}})
    )
    code, printed = runs(
        tmp_path,
        [(7.0, 26.0)],
        "--store",
        str(data_root),
        "--before",
        str(tmp_path / "before.json"),
    )
    assert code == 0
    assert "2 cut points, 0 moved: 0 improved, 0 degraded, 0 same cut" in printed


@pytest.mark.parametrize(
    ("punch_in", "punch_out"), [(0.0, SOURCE_SECONDS), (HUMAN_IN, HUMAN_OUT)]
)
def test_a_stored_pair_whose_recording_has_no_measured_duration_is_refused_by_name(
    tmp_path, punch_in, punch_out
):
    unlabelled_corpus(tmp_path)
    stages_corpus(tmp_path, tag="another-tag.whole.v2")
    (tmp_path / "groundtruth.json").write_text(json.dumps({"recordings": []}))
    data_root = stages_store(tmp_path, duration=None)
    labels(data_root, punch_in=punch_in, punch_out=punch_out)
    code, printed = runs(tmp_path, [(7.0, 26.0)], "--store", str(data_root))
    assert code == 1
    assert printed.count(f"{RECORDING} is not graded: its source duration is unknown") == 1
    assert "0 proposals graded, 0 cut points" in printed


def test_a_stored_pair_whose_duration_is_unknown_is_refused_by_the_gate_too(tmp_path):
    unlabelled_corpus(tmp_path)
    data_root = stages_store(tmp_path, duration=None)
    labels(data_root)
    (tmp_path / "before.json").write_text(
        json.dumps({BLOCK: {"chosen": [{"punch_in": 14.0, "punch_out": 26.0}]}})
    )
    code, printed = runs(
        tmp_path, [(7.0, 26.0)], "--store", str(data_root), "--before", str(tmp_path / "before.json")
    )
    assert f"{RECORDING} is not graded: its source duration is unknown" in printed
    assert "0 proposals graded, 0 cut points, 0 moved" in printed


@pytest.mark.parametrize("gated", [False, True])
def test_a_corpus_with_no_answer_key_and_no_store_is_refused_with_a_sentence(tmp_path, gated):
    stages_corpus(tmp_path)
    (tmp_path / "groundtruth.json").unlink()
    (tmp_path / "before.json").write_text(json.dumps({}))
    flags = ("--before", str(tmp_path / "before.json")) if gated else ()
    code, printed = runs(tmp_path, [(7.0, 26.0)], *flags)
    assert code == 1
    assert f"no answer key at {tmp_path / 'groundtruth.json'}" in printed
    assert "--store" in printed


def test_the_drift_mode_needs_no_answer_key(tmp_path):
    stages_corpus(tmp_path)
    (tmp_path / "groundtruth.json").unlink()
    code, printed = runs(tmp_path, [(7.0, 26.0)], "--drift")
    assert code == 0
    assert "drift only, not accuracy" in printed


def publishes(data_root, boundary_source, published_on=date(2026, 6, 28)):
    store = opens_store(data_root)
    store.saves(
        Segment(
            recording_id=RECORDING,
            classification="sermon",
            state="complete",
            intent="publish",
            span_start_seconds=0.0,
            span_end_seconds=30.0,
            punch_in_seconds=HUMAN_IN,
            punch_out_seconds=HUMAN_OUT,
            boundary_source=boundary_source,
            publication_date=published_on,
        )
    )
    store.close()


def test_the_proportion_approved_with_no_edit_is_read_from_the_approval_record(tmp_path):
    unlabelled_corpus(tmp_path)
    data_root = stages_store(tmp_path)
    labels(data_root)
    publishes(data_root, "model")
    publishes(data_root, "human")
    publishes(data_root, "refined")
    code, printed = runs(tmp_path, [(14.0, 26.0)], "--store", str(data_root))
    assert code == 0
    assert (
        "from the approval record, not this run: 2 of 3 published Segments "
        "approved with no boundary edit (67%)"
    ) in printed


def test_an_approval_record_with_nothing_published_reports_no_proportion(tmp_path):
    unlabelled_corpus(tmp_path)
    data_root = stages_store(tmp_path)
    labels(data_root)
    code, printed = runs(tmp_path, [(7.0, 26.0)], "--store", str(data_root))
    assert code == 0
    assert (
        "from the approval record, not this run: nothing has been published, "
        "so there is no proportion approved with no boundary edit"
    ) in printed


def test_the_frozen_file_carries_no_approval_record(tmp_path):
    stages_corpus(tmp_path)
    _, printed = runs(tmp_path, [(7.0, 26.0)])
    assert "approval record" not in printed


def test_a_publication_with_no_date_is_counted_rather_than_vanishing_from_the_record(tmp_path):
    unlabelled_corpus(tmp_path)
    data_root = stages_store(tmp_path)
    labels(data_root)
    publishes(data_root, "model", published_on=None)
    _, printed = runs(tmp_path, [(7.0, 26.0)], "--store", str(data_root))
    assert "nothing has been published" not in printed
    assert (
        "from the approval record, not this run: 1 published Segment carries no "
        "publication date and is not counted"
    ) in printed


def test_a_baseline_that_compared_nothing_does_not_pass(tmp_path):
    stages_corpus(tmp_path, source_duration=None)
    (tmp_path / "before.json").write_text(
        json.dumps({BLOCK: {"chosen": [{"punch_in": 7.0, "punch_out": 26.0}]}})
    )
    code, printed = runs(tmp_path, [(7.0, 26.0)], "--before", str(tmp_path / "before.json"))
    assert code == 1
    assert "nothing could be compared against a human cut" in printed
