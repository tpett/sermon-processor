import ast
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = PROJECT_ROOT / "src" / "sermon" / "pipeline"
EXPERIMENTS_SRC = PROJECT_ROOT / "experiments" / "src"
FINGERPRINT = Path(__file__).parent / "pipeline_boundary_fingerprint.json"
LADDER = PROJECT_ROOT / "experiments" / "run_ladder.sh"
SELECTS_LADDER_PYTHON = PROJECT_ROOT / "experiments" / "ladder_python.sh"
SPIKE_DATA = Path(
    os.environ.get("SERMON_SPIKE_DATA") or PROJECT_ROOT / "experiments" / "data"
)

MOVED = {
    "audio": (
        "decode",
        "envelope",
        "cached_envelope",
        "ncc",
        "peak_and_ratio",
        "quiet_mask",
        "quiet_runs",
    ),
    "blocks": ("speech_runs", "merge_short", "candidates", "text_of", "stats"),
    "cues": ("count_hits", "any_hit"),
    "segments": (
        "speaker_edges",
        "snap_to",
        "candidate_edges",
        "snap",
        "refine_in",
        "refine_out",
        "add_tail",
        "coalesce",
        "derive",
        "choose",
    ),
    "rules": ("classify_block", "refine_punch_in", "refine_punch_out", "run"),
    "features": ("blocks_from_diarization", "describe", "render_table"),
    "acoustic": ("to_db", "find_pauses", "level_rise", "punch_out_candidates"),
    "render": ("measure", "render", "probe_loudness", "probe_format"),
    "classify": (
        "hms",
        "render_transcript",
        "ollama",
        "parse_json",
        "call_json",
        "coerce_blocks",
        "run_whole",
        "load_diarization",
        "run_structured",
        "run_perblock",
    ),
}

CLI_LEFT_BEHIND = ("render", "classify")

DRIVERS = (
    "align",
    "classify",
    "compare_asr",
    "diarize",
    "make_control_prompts",
    "render",
    "score",
    "speakerid",
    "summarize",
    "survey_unpublished",
    "transcribe_fw",
    "transcribe",
    "verify",
)


def names_pipeline_module(module):
    return f"sermon.pipeline.{module}"


def imports_pipeline_module(module):
    name = names_pipeline_module(module)
    assert importlib.util.find_spec(name) is not None, f"{name} is not importable"
    return importlib.import_module(name)


def renders_canonically(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def reads_spike_json(path):
    return json.loads(path.read_text())


def has_spike_artefacts():
    return all((SPIKE_DATA / name).is_dir() for name in ("blocks", "transcripts"))


spike_data_required = pytest.mark.skipif(
    not has_spike_artefacts(),
    reason=(
        f"{SPIKE_DATA}/blocks and /transcripts are gitignored and exist only in the "
        f"primary working tree; point SERMON_SPIKE_DATA at one that has them"
    ),
)


@pytest.mark.parametrize("module", sorted(MOVED))
def test_the_pipeline_package_carries_the_moved_module(module):
    assert importlib.util.find_spec(names_pipeline_module(module)) is not None


@pytest.mark.parametrize(
    ("module", "callable_name"),
    [(module, name) for module, names in sorted(MOVED.items()) for name in names],
)
def test_the_pipeline_package_exposes_the_moved_callable(module, callable_name):
    carried = imports_pipeline_module(module)
    assert callable(getattr(carried, callable_name, None))


@pytest.mark.parametrize("module", sorted(set(MOVED) - set(CLI_LEFT_BEHIND)))
def test_the_moved_module_no_longer_sits_in_experiments(module):
    assert not (EXPERIMENTS_SRC / f"{module}.py").exists()


@pytest.mark.parametrize("stayed", CLI_LEFT_BEHIND)
def test_the_driver_left_in_experiments_keeps_its_main_and_imports_the_package(stayed):
    source = (EXPERIMENTS_SRC / f"{stayed}.py").read_text(encoding="utf-8")
    assert "def main(" in source
    assert "sermon.pipeline" in source


def reads_its_own_location(source):
    return any(
        isinstance(node, ast.Name) and node.id == "__file__"
        for node in ast.walk(ast.parse(source))
    )


def test_no_moved_module_resolves_a_path_from_its_own_location():
    modules = sorted(PIPELINE_ROOT.rglob("*.py"))
    assert modules, f"no modules found under {PIPELINE_ROOT}"
    offenders = sorted(
        str(path.relative_to(PIPELINE_ROOT))
        for path in modules
        if reads_its_own_location(path.read_text(encoding="utf-8"))
    )
    assert offenders == []


def test_every_module_that_derives_segments_sets_the_data_root_it_needs():
    offenders = sorted(
        path.name
        for path in EXPERIMENTS_SRC.glob("*.py")
        if "from sermon.pipeline import segments" in path.read_text(encoding="utf-8")
        and "DATA_ROOT" not in path.read_text(encoding="utf-8")
    )
    assert offenders == []


def test_speaker_edges_reads_the_diarization_under_the_data_root_it_is_given(
    tmp_path, monkeypatch
):
    segments = imports_pipeline_module("segments")
    root = tmp_path / "data"
    (root / "diarization").mkdir(parents=True)
    (root / "diarization" / "rec1.json").write_text(
        json.dumps({"turns": [{"start": 1.0004, "end": 2.5}, {"start": 2.5, "end": 9.87654}]})
    )
    monkeypatch.setattr(segments, "DATA_ROOT", root)
    assert segments.speaker_edges({"recording_id": "rec1"}) == [1.0, 2.5, 9.877]


def test_speaker_edges_finds_nothing_when_no_data_root_is_set(monkeypatch):
    segments = imports_pipeline_module("segments")
    monkeypatch.setattr(segments, "DATA_ROOT", None)
    assert segments.speaker_edges({"recording_id": "rec1"}) == []


def test_speaker_edges_finds_nothing_when_the_recording_was_not_diarized(tmp_path, monkeypatch):
    segments = imports_pipeline_module("segments")
    (tmp_path / "diarization").mkdir()
    monkeypatch.setattr(segments, "DATA_ROOT", tmp_path)
    assert segments.speaker_edges({"recording_id": "never-diarized"}) == []


def derives_every_stored_block(segments):
    derived = {}
    for path in sorted((SPIKE_DATA / "blocks").glob("*.json")):
        stored = reads_spike_json(path)
        transcript = (
            SPIKE_DATA / "transcripts" / f"{stored['recording_id']}.{stored['asr_config']}.json"
        )
        if not transcript.exists():
            continue
        doc = reads_spike_json(transcript)
        segments._EDGE_CACHE.clear()
        segments_derived = segments.derive(stored["blocks"], doc)
        derived[path.name] = {
            "derived": segments_derived,
            "chosen": segments.choose(stored.get("model_segments") or [], segments_derived, doc),
        }
    return derived


@spike_data_required
def test_deriving_every_stored_block_reproduces_the_boundaries_measured_before_the_move(
    monkeypatch,
):
    segments = imports_pipeline_module("segments")
    monkeypatch.setattr(segments, "DATA_ROOT", SPIKE_DATA)
    expected = json.loads(FINGERPRINT.read_text())
    found = derives_every_stored_block(segments)
    assert sorted(found) == sorted(expected)
    drifted = sorted(
        name
        for name, boundaries in found.items()
        if renders_canonically(boundaries) != renders_canonically(expected[name])
    )
    assert drifted == []


def selects_the_ladder_interpreter(**overrides):
    return subprocess.run(
        ["/bin/bash", str(SELECTS_LADDER_PYTHON)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, **overrides},
    )


def names_an_interpreter_without_the_package():
    return str(Path(sys.base_prefix) / "bin" / "python3")


def test_the_documented_entry_point_delegates_its_interpreter_choice():
    source = LADDER.read_text(encoding="utf-8")
    assert SELECTS_LADDER_PYTHON.name in source
    assert ".venv/bin/python" not in source


def test_the_ladder_interpreter_imports_the_pipeline_package():
    chosen = selects_the_ladder_interpreter()
    assert chosen.returncode == 0, chosen.stdout + chosen.stderr
    imported = subprocess.run(
        [chosen.stdout.strip(), "-c", "import sermon.pipeline.classify"],
        capture_output=True,
        text=True,
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr


def test_the_ladder_refuses_an_interpreter_that_cannot_import_the_pipeline_package():
    bare = names_an_interpreter_without_the_package()
    refused = selects_the_ladder_interpreter(LADDER_PYTHON=bare)
    assert refused.returncode != 0, refused.stdout
    assert bare in refused.stderr, refused.stderr


@pytest.mark.parametrize("driver", DRIVERS)
def test_the_frozen_driver_still_runs(driver):
    chosen = selects_the_ladder_interpreter()
    assert chosen.returncode == 0, chosen.stdout + chosen.stderr
    finished = subprocess.run(
        [chosen.stdout.strip(), str(EXPERIMENTS_SRC / f"{driver}.py"), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    report = finished.stdout + finished.stderr
    assert finished.returncode == 0, report
    assert "ModuleNotFoundError" not in report, report
