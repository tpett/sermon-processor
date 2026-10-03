import json

from sermon import cli
from sermon.analysis.regrades_stored_cuts import DerivesStoredSegments, RegradesStoredCuts
from sermon.pipeline import segments
from sermon.scores_cut import DEGRADED, DIFFERENT_CUT, EQUAL, IMPROVED, SAME_CUT

ASR = "an-asr-config"
RECORDING = "recording_20260412_102318"
TAG = "a-tag.whole.v2"

WORDS = [
    ("one", 0.0, 1.0),
    ("two", 1.0, 2.0),
    ("three", 7.0, 8.0),
    ("four", 8.0, 9.0),
    ("five", 11.0, 12.0),
    ("six", 50.0, 51.0),
]
FIRST_RUN = (2.0, 7.0)
SECOND_RUN = (9.0, 11.0)


def stages_corpus(root, stored_segments, recording_id=RECORDING, tag=TAG, transcript=True):
    (root / "blocks").mkdir(parents=True, exist_ok=True)
    (root / "transcripts").mkdir(parents=True, exist_ok=True)
    (root / "blocks" / f"{recording_id}.{tag}.json").write_text(
        json.dumps(
            {
                "recording_id": recording_id,
                "asr_config": ASR,
                "blocks": [{"start": 0.0, "end": 51.0, "type": "sermon"}],
                "model_segments": [],
                "segments": [
                    {"punch_in": punch_in, "punch_out": punch_out}
                    for punch_in, punch_out in stored_segments
                ],
            }
        )
    )
    if transcript:
        (root / "transcripts" / f"{recording_id}.{ASR}.json").write_text(
            json.dumps(
                {
                    "recording_id": recording_id,
                    "duration": 60.0,
                    "utterances": [
                        {
                            "start": start,
                            "end": end,
                            "text": word,
                            "words": [{"w": word, "start": start, "end": end}],
                        }
                        for word, start, end in WORDS
                    ],
                    "silences": [],
                }
            )
        )
    return root


def regrades(root, live, **staged):
    stages_corpus(root, **staged)
    return RegradesStoredCuts(
        corpus_root=root,
        derives=lambda stored, doc: [
            {"punch_in": punch_in, "punch_out": punch_out} for punch_in, punch_out in live
        ],
    )()


def verdicts(regraded):
    return {cut.boundary: cut.score.verdict for proposal in regraded for cut in proposal.cuts}


def test_a_cut_that_did_not_move_is_equal(tmp_path):
    regraded = regrades(tmp_path, live=[FIRST_RUN], stored_segments=[FIRST_RUN])
    assert verdicts(regraded) == {"punch_in": EQUAL, "punch_out": EQUAL}
    assert regraded[0].degraded is False


def test_a_cut_that_moved_inside_its_run_is_the_same_cut(tmp_path):
    regraded = regrades(tmp_path, live=[(6.0, 10.0)], stored_segments=[(3.0, 10.0)])
    assert verdicts(regraded)["punch_in"] == SAME_CUT
    assert regraded[0].degraded is False


def test_a_cut_that_left_its_run_for_a_word_is_a_degradation(tmp_path):
    regraded = regrades(tmp_path, live=[(7.5, 10.0)], stored_segments=[(3.0, 10.0)])
    assert verdicts(regraded)["punch_in"] == DEGRADED
    assert regraded[0].degraded is True


def test_a_cut_that_moved_to_another_run_is_a_different_cut_not_a_degradation(tmp_path):
    regraded = regrades(tmp_path, live=[(10.0, 20.0)], stored_segments=[(3.0, 20.0)])
    assert verdicts(regraded)["punch_in"] == DIFFERENT_CUT
    assert regraded[0].degraded is False


def test_a_cut_that_left_a_word_for_a_run_is_an_improvement(tmp_path):
    regraded = regrades(tmp_path, live=[(3.0, 10.0)], stored_segments=[(7.5, 10.0)])
    assert verdicts(regraded)["punch_in"] == IMPROVED
    assert regraded[0].degraded is False


def test_both_boundaries_of_every_stored_segment_are_graded(tmp_path):
    regraded = regrades(tmp_path, live=[(3.0, 10.0)], stored_segments=[(3.0, 10.0)])
    assert [cut.boundary for cut in regraded[0].cuts] == ["punch_in", "punch_out"]
    assert regraded[0].cuts[0].score.truth == 3.0
    assert regraded[0].cuts[1].score.truth == 10.0


def test_the_tag_and_the_recording_come_from_the_stored_file_name(tmp_path):
    regraded = regrades(tmp_path, live=[FIRST_RUN], stored_segments=[FIRST_RUN])
    assert regraded[0].recording_id == RECORDING
    assert regraded[0].tag == TAG
    assert regraded[0].cuts[0].tag == TAG


def test_a_live_run_that_proposes_a_different_number_of_segments_is_a_degradation(tmp_path):
    regraded = regrades(tmp_path, live=[], stored_segments=[FIRST_RUN])
    assert regraded[0].stored_count == 1
    assert regraded[0].live_count == 0
    assert regraded[0].cuts == ()
    assert regraded[0].degraded is True


def test_a_stored_file_with_no_transcript_is_reported_and_not_regraded(tmp_path):
    regraded = regrades(tmp_path, live=[FIRST_RUN], stored_segments=[FIRST_RUN], transcript=False)
    assert regraded[0].regraded is False
    assert regraded[0].live_count is None
    assert regraded[0].degraded is False


def test_a_stored_file_proposing_nothing_and_still_proposing_nothing_is_clean(tmp_path):
    regraded = regrades(tmp_path, live=[], stored_segments=[])
    assert regraded[0].regraded is True
    assert regraded[0].cuts == ()
    assert regraded[0].degraded is False


def prints_to(collected):
    return collected.append


def runs_drift(root, live, *flags, **staged):
    stages_corpus(root, **staged)
    collected = []
    code = cli.regrades(
        arguments=["--corpus", str(root), "--drift", *flags],
        prints=prints_to(collected),
        derives=lambda stored, doc: [
            {"punch_in": punch_in, "punch_out": punch_out} for punch_in, punch_out in live
        ],
    )
    return code, "\n".join(collected)


def test_drift_reports_a_cut_that_stayed_in_its_run(tmp_path):
    code, printed = runs_drift(tmp_path, live=[(6.0, 10.0)], stored_segments=[(3.0, 10.0)])
    assert code == 0
    assert RECORDING in printed
    assert "punch-in" in printed
    assert SAME_CUT in printed
    assert "drift only, not accuracy: 1 stored proposals, 2 cut points, 1 differ" in printed


def test_drift_never_decides_the_exit_code(tmp_path):
    code, printed = runs_drift(tmp_path, live=[(7.5, 10.0)], stored_segments=[(3.0, 10.0)])
    assert code == 0
    assert DEGRADED in printed
    assert "1 differ from what the corpus recorded: 1 degraded" in printed


def test_drift_reports_the_run_each_cut_landed_in(tmp_path):
    _, printed = runs_drift(tmp_path, live=[(6.0, 10.0)], stored_segments=[(3.0, 10.0)])
    assert "run 0 (5.0s)" in printed


def test_drift_reports_the_signed_delta_beside_the_verdict(tmp_path):
    _, printed = runs_drift(tmp_path, live=[(6.0, 10.0)], stored_segments=[(3.0, 10.0)])
    assert "delta   +3.000 s" in printed
    assert "speech   0.000 s" in printed


def test_drift_prints_nothing_for_a_cut_that_did_not_move(tmp_path):
    _, printed = runs_drift(tmp_path, live=[(3.0, 10.0)], stored_segments=[(3.0, 10.0)])
    assert RECORDING not in printed.split("\n", 1)[1]


def test_the_command_refuses_a_corpus_with_no_stored_proposals(tmp_path):
    collected = []
    assert cli.regrades(
        arguments=["--corpus", str(tmp_path), "--corpus-regime"], prints=prints_to(collected)
    ) == 1
    assert "no stored proposals" in "\n".join(collected)


def test_the_command_refuses_a_corpus_that_holds_no_diarization(tmp_path, monkeypatch):
    monkeypatch.setattr(segments, "DATA_ROOT", None)
    stages_corpus(tmp_path, stored_segments=[FIRST_RUN])
    collected = []
    code = cli.regrades(
        arguments=["--corpus", str(tmp_path), "--drift"], prints=prints_to(collected)
    )
    assert code == 1
    assert "diarization" in "\n".join(collected)


def test_the_drift_mode_runs_the_real_pipeline_and_sets_the_root(tmp_path, monkeypatch):
    monkeypatch.setattr(segments, "DATA_ROOT", None)
    stages_corpus(tmp_path, stored_segments=[(0.0, 51.0)])
    (tmp_path / "diarization").mkdir()
    collected = []
    code = cli.regrades(
        arguments=["--corpus", str(tmp_path), "--drift"], prints=prints_to(collected)
    )
    printed = "\n".join(collected)
    assert code == 0
    assert "drift only, not accuracy: 1 stored proposals, 2 cut points, 1 differ" in printed
    assert segments.DATA_ROOT == tmp_path


def test_deriving_a_stored_proposal_points_the_pipeline_at_the_corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(segments, "DATA_ROOT", tmp_path / "somewhere-else")
    stages_corpus(tmp_path, stored_segments=[FIRST_RUN])
    stored = json.loads((tmp_path / "blocks" / f"{RECORDING}.{TAG}.json").read_text())
    doc = json.loads((tmp_path / "transcripts" / f"{RECORDING}.{ASR}.json").read_text())
    (tmp_path / "diarization").mkdir()
    DerivesStoredSegments(data_root=tmp_path)(stored, doc)
    assert segments.DATA_ROOT == tmp_path
