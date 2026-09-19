import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT = PROJECT_ROOT / "experiments" / "baseline.py"
COMMITTED = PROJECT_ROOT / "experiments" / "data" / "extraction-baseline.json"

RESULT_ROWS = [
    {
        "config_id": "t0-rules.whole.v2",
        "stage": 1,
        "recording_id": "recording_20260405_085215",
        "split": "fresh",
        "found": False,
        "true_in": 494.325,
    },
    {
        "config_id": "t0-rules.whole.v2",
        "stage": 1,
        "recording_id": "recording_20260405_085215",
        "split": "fresh",
        "found": True,
        "true_in": 7565.47,
        "punch_in_error": 341.81,
    },
    {
        "config_id": "c-frontier.whole.v2",
        "stage": 1,
        "recording_id": "recording_20260315_102948",
        "split": "test",
        "found": True,
        "true_in": 1228.788,
        "punch_in_error": 0.012,
    },
]

BLOCK = {
    "blocks": [
        {"start": 0.0, "end": 184.9, "type": "announcements", "confidence": 0.95, "evidence": "x"},
        {"start": 184.9, "end": 4082.8, "type": "sermon", "confidence": 0.96, "evidence": "y"},
    ],
    "derived_segments": [
        {"punch_in": 1228.8, "punch_out": 4082.13, "classification": "sermon", "confidence": 0.96}
    ],
    "segments": [
        {
            "punch_in": 1228.8,
            "punch_out": 4082.13,
            "classification": "sermon",
            "confidence": 0.96,
            "boundary_source": "model-in/refined-out",
        }
    ],
    "model_segments": [{"punch_in": 1228.8, "punch_out": 4016.1}],
    "status": "ok",
    "repairs": 0,
    "config_id": "c-frontier.whole.v2",
    "recording_id": "recording_20260315_102948",
    "desktop_label": "2026-03-15 - Hebrews 9.11-14",
    "asr_config": "whole.v2",
    "wall_clock_s": None,
}

FIRST_BLOCK = "recording_20260315_102948.c-frontier.whole.v2.json"
SECOND_BLOCK = "recording_20260405_085215.t0-rules.whole.v2.json"
TRANSCRIPT = "recording_20260315_102948.whole.v2.json"
DIARIZATION = "recording_20260315_102948.json"
ACCESS_LOG = "2026-08-29T09:31:08\tc-frontier.whole.v2\ttest\tno-git\n"


def loads_instrument():
    location = importlib.util.spec_from_file_location("experiments_baseline", INSTRUMENT)
    module = importlib.util.module_from_spec(location)
    sys.modules[location.name] = module
    try:
        location.loader.exec_module(module)
    finally:
        sys.modules.pop(location.name, None)
    return module


baseline = loads_instrument()


def writes_json(path, value, **rendering):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, **rendering))


def builds_data_root(root):
    (root / "blocks").mkdir(parents=True)
    (root / "transcripts").mkdir()
    (root / "diarization").mkdir()
    writes_json(root / "blocks" / FIRST_BLOCK, BLOCK, indent=1)
    writes_json(
        root / "blocks" / SECOND_BLOCK, BLOCK | {"config_id": "t0-rules.whole.v2"}, indent=1
    )
    writes_json(root / "transcripts" / TRANSCRIPT, {"segments": [{"start": 0.0, "text": "hello"}]})
    writes_json(root / "diarization" / DIARIZATION, {"turns": [{"start": 0.0, "speaker": "A"}]})
    writes_json(root / "groundtruth.json", {"recordings": [{"recording_id": "r", "true_in": 1.5}]})
    (root / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in RESULT_ROWS))
    (root / "bucket.txt").write_text("recording_20260315_102948.flac\n")
    (root / "test_access.log").write_text(ACCESS_LOG)
    return root


@pytest.fixture
def data_root(tmp_path):
    return builds_data_root(tmp_path / "data")


@pytest.fixture
def captured(data_root):
    return baseline.CapturesBaseline(data_root=data_root)()


@pytest.fixture
def perturbed(data_root, captured, tmp_path):
    copy = tmp_path / "perturbed"
    shutil.copytree(data_root, copy)
    return copy


def drift(captured, data_root):
    return baseline.ComparesBaseline(baseline=captured, data_root=data_root)()


def kinds(findings):
    return {finding.kind for finding in findings}


def rendered(findings):
    return "\n".join(str(finding) for finding in findings)


def test_a_faithful_snapshot_of_the_stored_artefacts_reports_no_drift(captured, data_root):
    assert drift(captured, data_root) == []


def test_the_original_data_is_never_what_a_perturbation_touches(data_root, perturbed, captured):
    (perturbed / "blocks" / FIRST_BLOCK).unlink()
    assert drift(captured, data_root) == []
    assert drift(captured, perturbed) != []


def test_a_punch_in_that_moves_by_a_millisecond_is_drift(captured, perturbed):
    moved = json.loads((perturbed / "blocks" / FIRST_BLOCK).read_text())
    moved["derived_segments"][0]["punch_in"] = 1228.801
    writes_json(perturbed / "blocks" / FIRST_BLOCK, moved, indent=1)
    findings = drift(captured, perturbed)
    assert findings != []
    assert FIRST_BLOCK in rendered(findings)
    assert "derived_segments" in rendered(findings)
    assert "1228.801" in rendered(findings)


def test_a_punch_out_that_moves_in_the_chosen_segments_is_drift(captured, perturbed):
    moved = json.loads((perturbed / "blocks" / FIRST_BLOCK).read_text())
    moved["segments"][0]["punch_out"] = 4082.131
    writes_json(perturbed / "blocks" / FIRST_BLOCK, moved, indent=1)
    findings = drift(captured, perturbed)
    assert "segments" in rendered(findings)
    assert "4082.131" in rendered(findings)


def test_a_reclassified_block_is_drift(captured, perturbed):
    moved = json.loads((perturbed / "blocks" / FIRST_BLOCK).read_text())
    moved["blocks"][1]["type"] = "announcements"
    writes_json(perturbed / "blocks" / FIRST_BLOCK, moved, indent=1)
    assert "block_spans" in rendered(drift(captured, perturbed))


def test_evidence_text_a_hash_covers_but_no_value_line_names_is_still_drift(captured, perturbed):
    moved = json.loads((perturbed / "blocks" / FIRST_BLOCK).read_text())
    moved["blocks"][0]["evidence"] = "something else entirely"
    writes_json(perturbed / "blocks" / FIRST_BLOCK, moved, indent=1)
    findings = drift(captured, perturbed)
    assert findings != []
    assert "blocks" in rendered(findings)


def test_reordered_keys_and_a_different_indent_are_not_drift(captured, perturbed):
    same = json.loads((perturbed / "blocks" / FIRST_BLOCK).read_text())
    reversed_keys = {key: same[key] for key in reversed(list(same))}
    writes_json(perturbed / "blocks" / FIRST_BLOCK, reversed_keys, indent=4, sort_keys=False)
    assert drift(captured, perturbed) == []


def test_a_rewritten_results_log_with_the_same_values_is_not_drift(captured, perturbed):
    rows = [json.loads(line) for line in (perturbed / "results.jsonl").read_text().splitlines()]
    (perturbed / "results.jsonl").write_text(
        "".join(
            json.dumps(row, sort_keys=True, indent=None) + "\n" for row in reversed_fields(rows)
        )
    )
    assert drift(captured, perturbed) == []


def reversed_fields(rows):
    return [{key: row[key] for key in reversed(list(row))} for row in rows]


def test_an_appended_result_row_is_drift(captured, perturbed):
    with (perturbed / "results.jsonl").open("a") as log:
        log.write(json.dumps(RESULT_ROWS[0]) + "\n")
    findings = drift(captured, perturbed)
    assert "count" in kinds(findings)
    assert "results.jsonl" in rendered(findings)


def test_a_changed_result_field_names_the_row_the_field_and_both_values(captured, perturbed):
    rows = [json.loads(line) for line in (perturbed / "results.jsonl").read_text().splitlines()]
    rows[2]["punch_in_error"] = 0.013
    (perturbed / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    report = rendered(drift(captured, perturbed))
    assert "row 2" in report
    assert "punch_in_error" in report
    assert "0.012" in report
    assert "0.013" in report


def test_a_result_field_that_disappears_is_drift(captured, perturbed):
    rows = [json.loads(line) for line in (perturbed / "results.jsonl").read_text().splitlines()]
    del rows[2]["punch_in_error"]
    (perturbed / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert "missing" in kinds(drift(captured, perturbed))


def test_duplicate_result_rows_are_compared_by_position_rather_than_identity(captured, perturbed):
    rows = [json.loads(line) for line in (perturbed / "results.jsonl").read_text().splitlines()]
    rows[0], rows[1] = rows[1], rows[0]
    (perturbed / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    findings = drift(captured, perturbed)
    assert findings != []
    assert "row 0" in rendered(findings)


def test_a_missing_derived_artefact_is_drift(captured, perturbed):
    (perturbed / "blocks" / FIRST_BLOCK).unlink()
    findings = drift(captured, perturbed)
    assert "missing" in kinds(findings)
    assert FIRST_BLOCK in rendered(findings)


def test_a_configuration_that_was_not_in_the_baseline_is_drift(captured, perturbed):
    writes_json(perturbed / "blocks" / "recording_20260315_102948.t9-new.whole.v2.json", BLOCK)
    findings = drift(captured, perturbed)
    assert "unexpected" in kinds(findings)
    assert "t9-new" in rendered(findings)


@pytest.mark.parametrize("absent", ["blocks", "transcripts", "diarization"])
def test_a_whole_derived_directory_going_absent_cannot_be_compared(captured, perturbed, absent):
    shutil.rmtree(perturbed / absent)
    with pytest.raises(baseline.BaselineUnusable) as refused:
        drift(captured, perturbed)
    assert absent in str(refused.value)


def test_a_data_root_without_the_gitignored_artefacts_exits_two_rather_than_reporting_drift(
    captured, perturbed, tmp_path
):
    written = tmp_path / "baseline.json"
    written.write_text(json.dumps(captured))
    for name in ("blocks", "transcripts", "diarization"):
        shutil.rmtree(perturbed / name)
    assert baseline.main(["--baseline", str(written), "--data", str(perturbed)]) == 2


def test_one_artefact_going_absent_from_a_directory_that_is_there_is_still_drift(
    captured, perturbed
):
    (perturbed / "blocks" / FIRST_BLOCK).unlink()
    findings = drift(captured, perturbed)
    assert "missing" in kinds(findings)
    assert FIRST_BLOCK in rendered(findings)


def test_a_transcript_that_moved_under_the_baseline_is_drift(captured, perturbed):
    writes_json(perturbed / "transcripts" / TRANSCRIPT, {"segments": [{"start": 0.1}]})
    findings = drift(captured, perturbed)
    assert TRANSCRIPT in rendered(findings)


def test_a_changed_diarization_artefact_is_drift(captured, perturbed):
    writes_json(perturbed / "diarization" / DIARIZATION, {"turns": []})
    assert DIARIZATION in rendered(drift(captured, perturbed))


def test_a_line_appended_to_the_held_out_access_log_is_drift(captured, perturbed):
    with (perturbed / "test_access.log").open("a") as log:
        log.write("2026-09-19T00:00:00\tt3-qwen3.6.whole.v2\ttest\tdeadbee\n")
    findings = drift(captured, perturbed)
    assert "test_access.log" in rendered(findings)


def test_a_changed_ground_truth_is_drift(captured, perturbed):
    writes_json(perturbed / "groundtruth.json", {"recordings": [{"recording_id": "r"}]})
    assert "groundtruth.json" in rendered(drift(captured, perturbed))


def test_an_unreadable_artefact_is_drift_rather_than_a_crash(captured, perturbed):
    (perturbed / "blocks" / FIRST_BLOCK).write_text("{ truncated")
    findings = drift(captured, perturbed)
    assert "unreadable" in kinds(findings)
    assert FIRST_BLOCK in rendered(findings)


def test_a_missing_loose_artefact_is_drift_rather_than_a_crash(captured, perturbed):
    (perturbed / "results.jsonl").unlink()
    (perturbed / "test_access.log").unlink()
    report = rendered(drift(captured, perturbed))
    assert "results.jsonl" in report
    assert "test_access.log" in report


def test_a_data_root_that_is_not_there_cannot_be_compared(captured, tmp_path):
    with pytest.raises(baseline.BaselineUnusable):
        drift(captured, tmp_path / "absent")


def test_a_baseline_that_is_not_there_cannot_be_read(tmp_path):
    with pytest.raises(baseline.BaselineUnusable):
        baseline.reads_baseline(tmp_path / "absent.json")


def test_a_baseline_that_is_not_json_cannot_be_read(tmp_path):
    unparseable = tmp_path / "baseline.json"
    unparseable.write_text("{ truncated")
    with pytest.raises(baseline.BaselineUnusable):
        baseline.reads_baseline(unparseable)


def test_a_baseline_of_another_schema_cannot_be_compared(captured, data_root):
    with pytest.raises(baseline.BaselineUnusable):
        drift(captured | {"schema": "extraction-baseline/0"}, data_root)


@pytest.mark.parametrize("collection", ["results", "blocks", "transcripts", "diarization"])
def test_a_truncated_baseline_cannot_be_compared(captured, data_root, collection):
    with pytest.raises(baseline.BaselineUnusable):
        drift(captured | {collection: type(captured[collection])()}, data_root)


def test_a_baseline_whose_counts_disagree_with_what_it_holds_cannot_be_compared(
    captured, data_root
):
    with pytest.raises(baseline.BaselineUnusable):
        drift(captured | {"counts": captured["counts"] | {"block_files": 999}}, data_root)


def test_a_baseline_that_records_no_counts_cannot_be_compared(captured, data_root):
    with pytest.raises(baseline.BaselineUnusable):
        drift({key: value for key, value in captured.items() if key != "counts"}, data_root)


def test_capturing_a_baseline_of_an_absent_data_root_is_refused(tmp_path):
    with pytest.raises(baseline.BaselineUnusable):
        baseline.CapturesBaseline(data_root=tmp_path / "absent")()


def test_capturing_a_baseline_of_a_data_root_with_no_derived_artefacts_is_refused(tmp_path):
    empty = tmp_path / "data"
    (empty / "blocks").mkdir(parents=True)
    with pytest.raises(baseline.BaselineUnusable):
        baseline.CapturesBaseline(data_root=empty)()


def test_the_comparison_exits_zero_on_no_drift_and_one_on_drift(captured, perturbed, tmp_path):
    written = tmp_path / "baseline.json"
    written.write_text(json.dumps(captured))
    unchanged = ["--baseline", str(written), "--data", str(perturbed)]
    assert baseline.main(unchanged) == 0
    (perturbed / "blocks" / FIRST_BLOCK).unlink()
    assert baseline.main(unchanged) == 1


def test_an_instrument_that_cannot_compare_exits_two_rather_than_zero(data_root, tmp_path):
    absent = ["--baseline", str(tmp_path / "absent.json"), "--data", str(data_root)]
    assert baseline.main(absent) == 2


def test_capturing_refuses_to_overwrite_a_baseline_that_is_already_there(data_root, tmp_path):
    written = tmp_path / "baseline.json"
    written.write_text("{}")
    capture = ["--capture", "--baseline", str(written), "--data", str(data_root)]
    assert baseline.main(capture) == 2
    assert written.read_text() == "{}"
    assert baseline.main([*capture, "--force"]) == 0
    assert baseline.reads_baseline(written)["counts"]["block_files"] == 2


def test_the_committed_baseline_pins_the_counts_every_stored_number_rests_on():
    assert COMMITTED.exists(), f"{COMMITTED} is the instrument's reference and is not committed"
    counts = baseline.reads_baseline(COMMITTED)["counts"]
    assert counts == {
        "results_rows": 232,
        "result_configs": 5,
        "result_recordings": 39,
        "result_splits": {"dev": 96, "fresh": 24, "negative": 74, "test": 38},
        "block_files": 181,
        "block_configs": 13,
        "transcript_files": 48,
        "diarization_files": 14,
        "access_log_lines": 11,
    }


def test_a_report_on_a_text_artefact_names_the_line_count_it_moved_to(captured, perturbed):
    with (perturbed / "test_access.log").open("a") as log:
        log.write("2026-09-19T00:00:00\tt3-qwen3.6.whole.v2\ttest\tdeadbee\n")
    report = rendered(drift(captured, perturbed))
    assert "lines was 1, is 2" in report
    assert "digest was" in report


def test_a_digest_that_moved_is_reported_even_where_a_value_line_already_named_it(
    captured, perturbed
):
    moved = json.loads((perturbed / "blocks" / FIRST_BLOCK).read_text())
    moved["derived_segments"][0]["punch_in"] = 1228.801
    writes_json(perturbed / "blocks" / FIRST_BLOCK, moved, indent=1)
    assert "digest was" in rendered(drift(captured, perturbed))
