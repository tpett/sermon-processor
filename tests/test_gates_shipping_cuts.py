import json

import pytest

from sermon.analysis.gates_shipping_cuts import (
    CANNOT_GATE,
    PASSED,
    PRODUCTION_TAG,
    WORSENED,
    AcceptsBaseline,
    GatesShippingCuts,
    RecordsHeldOutRead,
    HeldOutSealed,
    reads_baseline,
)
from sermon.analysis.judges_cut import BETTER, JUDGE_DIGEST, UNCHANGED, WORSE
from sermon.analysis.replays_shipping_walk import ProposedCut, ReplayedProposals

DEV = "recording_20260412_102318"
DEV_TOO = "recording_20260510_102947"
TEST = "recording_20260315_102948"
WHOLE = "recording_20260628_130014"
ASR = "fw-test+words"
WORDS = [(10.0, 11.0), (20.0, 21.0), (21.0, 22.0), (40.0, 41.0), (90.0, 91.0), (95.0, 96.0)]
HUMAN = (15.0, 93.0)
HUMANS_PAUSE_IN, HUMANS_PAUSE_OUT = 12.0, 92.0


def labelled(recording_id, split, segments=(HUMAN,), duration=120.0):
    return {
        "recording_id": recording_id,
        "desktop_label": f"label of {recording_id}",
        "split": split,
        "source_duration": duration,
        "segments": [{"punch_in": a, "punch_out": b} for a, b in segments],
    }


@pytest.fixture
def corpus(tmp_path):
    (tmp_path / "blocks").mkdir()
    (tmp_path / "transcripts").mkdir()
    recordings = [
        labelled(DEV, "dev"),
        labelled(DEV_TOO, "dev"),
        labelled(TEST, "test"),
        labelled(WHOLE, "dev", segments=((0.0, 119.0),)),
    ]
    (tmp_path / "groundtruth.json").write_text(json.dumps({"recordings": recordings}))
    for held in recordings:
        for tag in (PRODUCTION_TAG, "u3-qwen3.6.whole.v2"):
            (tmp_path / "blocks" / f"{held['recording_id']}.{tag}.json").write_text(
                json.dumps({"recording_id": held["recording_id"], "asr_config": ASR})
            )
        (tmp_path / "transcripts" / f"{held['recording_id']}.{ASR}.json").write_text(
            json.dumps({"duration": 120.0, "utterances": [
                {"words": [{"w": "w", "start": a, "end": b} for a, b in WORDS]}
            ]})
        )
    return tmp_path


def replaying(cuts):
    def replays(block_path):
        recording_id, tag = block_path.name.split(".", 1)
        tag = tag[: -len(".json")]
        found = cuts.get((recording_id, tag), cuts.get(recording_id, ((HUMANS_PAUSE_IN, HUMANS_PAUSE_OUT),)))
        return ReplayedProposals(
            block_path.name,
            recording_id,
            tag,
            tuple(ProposedCut("sermon", a, b) for a, b in found),
        )

    return replays


def accepted(corpus, tmp_path, cuts, reason="the starting point"):
    path = tmp_path / "baseline.json"
    AcceptsBaseline(
        corpus_root=corpus, path=path, replays=replaying(cuts), describes_commit=lambda: "abc1234"
    )(reason)
    return path


def gated(corpus, baseline, cuts, **options):
    return GatesShippingCuts(
        corpus_root=corpus, baseline=reads_baseline(baseline), replays=replaying(cuts), **options
    )()


def test_production_is_the_faster_whisper_transcript_reasoned_over_by_the_35b(corpus):
    assert PRODUCTION_TAG == "fw-qwen3.6.whole.v2"


def test_an_unchanged_pipeline_passes_with_every_recording_unchanged(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {})
    report = gated(corpus, baseline, {})
    assert report.outcome == PASSED
    assert [(one.recording_id, one.verdict) for one in report.recordings] == [
        (DEV, UNCHANGED),
        (DEV_TOO, UNCHANGED),
    ]


def test_the_gate_counts_recordings_of_production_config_only_by_default(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {})
    report = gated(corpus, baseline, {})
    assert {one.tag for one in report.recordings} == {PRODUCTION_TAG}


def test_a_recording_archived_whole_is_not_judged(corpus, tmp_path):
    report = gated(corpus, accepted(corpus, tmp_path, {}), {})
    assert WHOLE not in [one.recording_id for one in report.recordings]


def test_a_punch_in_moved_out_of_the_humans_pause_fails_the_gate(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {})
    report = gated(corpus, baseline, {DEV: ((23.0, HUMANS_PAUSE_OUT),)})
    assert report.outcome == WORSENED
    worse = report.recordings[0]
    assert worse.recording_id == DEV and worse.verdict == WORSE
    assert [cut.verdict for cut in worse.cuts] == [WORSE, UNCHANGED]
    assert worse.cuts[0].after.speech_seconds == 2.0
    assert worse.cuts[0].before.same_pause


def test_a_cut_moved_into_the_humans_pause_passes_and_is_reported_better(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {DEV: ((23.0, HUMANS_PAUSE_OUT),)})
    report = gated(corpus, baseline, {})
    assert report.outcome == PASSED
    assert report.recordings[0].verdict == BETTER
    assert report.counts == {BETTER: 1, WORSE: 0, "mixed": 0, UNCHANGED: 1}


def test_better_at_one_end_and_worse_at_the_other_is_mixed_and_fails(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {DEV: ((23.0, HUMANS_PAUSE_OUT),)})
    report = gated(corpus, baseline, {DEV: ((HUMANS_PAUSE_IN, 95.5),)})
    assert report.recordings[0].verdict == "mixed"
    assert report.outcome == WORSENED


def test_a_move_inside_the_tolerance_is_unchanged(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {DEV: ((20.5, HUMANS_PAUSE_OUT),)})
    report = gated(corpus, baseline, {DEV: ((20.55, HUMANS_PAUSE_OUT),)})
    assert report.recordings[0].verdict == UNCHANGED
    assert report.outcome == PASSED


def test_losing_the_proposal_altogether_is_worse(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {})
    report = gated(corpus, baseline, {DEV: ()})
    assert report.recordings[0].verdict == WORSE
    assert report.recordings[0].cuts[0].after.missed


def test_a_new_proposal_the_human_did_not_cut_is_worse(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {})
    report = gated(corpus, baseline, {DEV: ((HUMANS_PAUSE_IN, HUMANS_PAUSE_OUT), (100.0, 119.0))})
    assert report.recordings[0].verdict == WORSE
    assert (report.recordings[0].unpaired_before, report.recordings[0].unpaired_after) == (0, 1)


def test_nothing_to_compare_cannot_gate(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {})
    report = gated(corpus, baseline, {}, tag="no-such-config")
    assert report.recordings == ()
    assert report.outcome == CANNOT_GATE


def test_a_recording_missing_from_the_baseline_is_reported_and_not_compared(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {})
    data = json.loads(baseline.read_text())
    del data["proposals"][f"{DEV}.{PRODUCTION_TAG}.json"]
    baseline.write_text(json.dumps(data))
    report = gated(corpus, baseline, {})
    assert report.not_in_baseline == (DEV,)
    assert [one.recording_id for one in report.recordings] == [DEV_TOO]


def test_the_test_split_is_refused_unless_unsealed(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {})
    with pytest.raises(HeldOutSealed):
        gated(corpus, baseline, {}, splits=("test",))


def test_unsealing_the_test_split_records_the_read_before_judging_it(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {})
    log = tmp_path / "held_out_reads.log"
    log.write_text("")
    records = RecordsHeldOutRead(
        path=log, clock=lambda: "2026-10-03T20:00:00+00:00", describes_commit=lambda: "abc1234"
    )
    report = gated(
        corpus, baseline, {}, splits=("test",), unsealed="checking the buffer change", records=records
    )
    assert [one.recording_id for one in report.recordings] == [TEST]
    line = log.read_text()
    assert "2026-10-03T20:00:00+00:00" in line and "abc1234" in line
    assert "checking the buffer change" in line and PRODUCTION_TAG in line and JUDGE_DIGEST in line


def test_a_held_out_read_with_nowhere_to_record_it_is_refused(corpus, tmp_path):
    baseline = accepted(corpus, tmp_path, {})
    records = RecordsHeldOutRead(path=tmp_path / "missing" / "held_out_reads.log")
    with pytest.raises(HeldOutSealed):
        gated(corpus, baseline, {}, splits=("test",), unsealed="why", records=records)


def test_the_baseline_records_who_accepted_it_why_and_under_which_judge(corpus, tmp_path):
    path = accepted(corpus, tmp_path, {}, reason="first acceptance")
    baseline = reads_baseline(path)
    assert baseline.judge == JUDGE_DIGEST
    assert baseline.accepted[-1]["reason"] == "first acceptance"
    assert baseline.accepted[-1]["commit"] == "abc1234"
    assert f"{TEST}.{PRODUCTION_TAG}.json" in baseline.proposals


def test_accepting_again_keeps_the_history_and_counts_what_moved(corpus, tmp_path):
    accepted(corpus, tmp_path, {}, reason="first")
    path = tmp_path / "baseline.json"
    outcome = AcceptsBaseline(
        corpus_root=corpus,
        path=path,
        replays=replaying({(DEV, PRODUCTION_TAG): ((23.0, HUMANS_PAUSE_OUT),)}),
        describes_commit=lambda: "def5678",
    )("second")
    assert outcome.moved == (f"{DEV}.{PRODUCTION_TAG}.json",)
    assert [entry["reason"] for entry in reads_baseline(path).accepted] == ["first", "second"]


def test_an_acceptance_needs_a_reason(corpus, tmp_path):
    with pytest.raises(ValueError):
        accepted(corpus, tmp_path, {}, reason="  ")


def test_a_changed_judge_cannot_gate_until_accepted(corpus, tmp_path):
    path = accepted(corpus, tmp_path, {})
    data = json.loads(path.read_text())
    data["judge"] = "000000000000"
    path.write_text(json.dumps(data))
    report = gated(corpus, path, {})
    assert report.judge_changed
    assert report.outcome == CANNOT_GATE


def test_a_judge_change_and_a_pipeline_change_cannot_be_accepted_together(corpus, tmp_path):
    path = accepted(corpus, tmp_path, {})
    data = json.loads(path.read_text())
    data["judge"] = "000000000000"
    path.write_text(json.dumps(data))
    accepts = AcceptsBaseline(
        corpus_root=corpus,
        path=path,
        replays=replaying({DEV: ((23.0, HUMANS_PAUSE_OUT),)}),
        describes_commit=lambda: "def5678",
    )
    outcome = accepts("both at once")
    assert outcome.refused
    assert json.loads(path.read_text())["judge"] == "000000000000"
    unmoved = AcceptsBaseline(
        corpus_root=corpus, path=path, replays=replaying({}), describes_commit=lambda: "def5678"
    )("the judge alone")
    assert not unmoved.refused
    assert reads_baseline(path).judge == JUDGE_DIGEST
