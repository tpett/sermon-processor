import json

import pytest

from sermon import cli
from sermon.analysis.judges_cut import JUDGE_DIGEST, JUDGE_VERSION

from test_gates_shipping_cuts import (
    DEV,
    HUMANS_PAUSE_OUT,
    PRODUCTION_TAG,
    corpus,  # noqa: F401
    replaying,
)


def runs(corpus, cuts, *flags, tmp_path):
    printed = []
    code = cli.regrades(
        arguments=[
            "--corpus", str(corpus),
            "--baseline", str(tmp_path / "baseline.json"),
            "--access-log", str(tmp_path / "held_out_reads.log"),
            *flags,
        ],
        prints=printed.append,
        replays=replaying(cuts),
    )
    return code, "\n".join(printed)


@pytest.fixture
def accepted(corpus, tmp_path):  # noqa: F811
    code, printed = runs(corpus, {}, "--accept", "the starting point", tmp_path=tmp_path)
    assert code == 0, printed
    return corpus


def test_the_gate_with_no_baseline_says_how_to_make_one_and_cannot_pass(corpus, tmp_path):  # noqa: F811
    code, printed = runs(corpus, {}, tmp_path=tmp_path)
    assert code == 2
    assert "--accept" in printed


def test_accepting_prints_what_it_recorded(corpus, tmp_path):  # noqa: F811
    code, printed = runs(corpus, {}, "--accept", "the starting point", tmp_path=tmp_path)
    assert code == 0
    assert "accepted" in printed and "the starting point" in printed
    assert json.loads((tmp_path / "baseline.json").read_text())["accepted"][0]["reason"] == (
        "the starting point"
    )


def test_the_gate_names_its_judge_population_and_reference(accepted, tmp_path):
    code, printed = runs(accepted, {}, tmp_path=tmp_path)
    assert code == 0
    assert f"judge v{JUDGE_VERSION} {JUDGE_DIGEST}" in printed
    assert PRODUCTION_TAG in printed and "dev split" in printed
    assert "the starting point" in printed
    assert "production's analyze walk" in printed
    assert "2 recordings judged: 0 better, 0 worse, 0 mixed, 2 unchanged" in printed


def test_a_worse_recording_is_spelled_out_for_the_owner_and_fails(accepted, tmp_path):
    code, printed = runs(accepted, {DEV: ((23.0, HUMANS_PAUSE_OUT),)}, tmp_path=tmp_path)
    assert code == 1
    assert f"label of {DEV}" in printed
    assert "WORSE" in printed
    assert "human 0:00:15.0" in printed
    assert "before 0:00:12.0  3.00 s early, in the human's pause" in printed
    assert "after  0:00:23.0  8.00 s late, 2.00 s of speech away" in printed
    assert "1 recordings judged" not in printed
    assert "2 recordings judged: 0 better, 1 worse, 0 mixed, 1 unchanged" in printed
    assert "worse by 2.00 speech-s" in printed


def test_unchanged_recordings_are_summarised_rather_than_spelled_out(accepted, tmp_path):
    code, printed = runs(accepted, {DEV: ((23.0, HUMANS_PAUSE_OUT),)}, tmp_path=tmp_path)
    assert "recording_20260510_102947" not in printed.split("recordings judged")[0].split("WORSE")[1]


def test_every_recording_is_spelled_out_on_request(accepted, tmp_path):
    code, printed = runs(accepted, {}, "--all", tmp_path=tmp_path)
    assert "label of recording_20260510_102947" in printed


def test_the_test_split_is_refused_without_unsealing(accepted, tmp_path):
    code, printed = runs(accepted, {}, "--split", "test", tmp_path=tmp_path)
    assert code == 2
    assert "held out" in printed
    assert not (tmp_path / "held_out_reads.log").exists() or not (
        tmp_path / "held_out_reads.log"
    ).read_text()


def test_unsealing_the_test_split_warns_and_records_the_read(accepted, tmp_path):
    code, printed = runs(
        accepted, {}, "--split", "test", "--unseal", "one look", tmp_path=tmp_path
    )
    assert "WARNING" in printed and "held out" in printed
    assert "one look" in (tmp_path / "held_out_reads.log").read_text()


def test_corpus_regime_flags_still_reach_the_old_replay(accepted, tmp_path):
    printed = []
    code = cli.regrades(
        arguments=["--corpus", str(accepted), "--drift"],
        prints=printed.append,
        derives=lambda stored, doc: [],
    )
    assert "corpus regime" in "\n".join(printed)
    assert code == 0


def test_a_corpus_with_no_stored_answers_cannot_gate(tmp_path):
    (tmp_path / "blocks").mkdir()
    code, printed = runs(tmp_path, {}, tmp_path=tmp_path)
    assert code == 2
    assert "no stored model answers" in printed


def test_a_corpus_with_no_answer_key_cannot_gate(accepted, tmp_path):
    (accepted / "groundtruth.json").unlink()
    code, printed = runs(accepted, {}, tmp_path=tmp_path)
    assert code == 2
    assert "no answer key" in printed


def test_cuts_that_moved_without_changing_the_judgement_are_counted(accepted, tmp_path):
    code, printed = runs(accepted, {DEV: ((13.0, HUMANS_PAUSE_OUT),)}, tmp_path=tmp_path)
    assert code == 0
    assert "1 cut moved without changing its judgement" in printed
