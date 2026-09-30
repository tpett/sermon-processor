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

INJECTED_SETTINGS = {"classify": ("DATA", "PROMPTS"), "segments": ("DATA_ROOT",)}

ROOT_GUARDS = ("requires_root", "requires_directory_under_root")

ROOT_CONSUMERS = {
    ("segments", "DATA_ROOT"): ("candidate_edges", "derive", "snap", "speaker_edges"),
    ("classify", "DATA"): ("load_diarization", "run_structured"),
    ("classify", "PROMPTS"): ("run_perblock", "run_structured", "run_whole"),
}

INJECTING_ROOTS = (PROJECT_ROOT / "src" / "sermon", EXPERIMENTS_SRC)

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


def reaches_the_pipeline_module(tree, module):
    wanted = names_pipeline_module(module)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.name == wanted or alias.name.startswith(f"{wanted}.")
                for alias in node.names
            ):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == wanted:
                return True
            if node.module == "sermon.pipeline" and any(
                alias.name == module for alias in node.names
            ):
                return True
    return False


def assigns_the_setting(node, setting):
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    else:
        return False
    return any(
        isinstance(named, ast.Attribute) and named.attr == setting
        for target in targets
        for named in ast.walk(target)
    )


def calls_setattr_for_the_setting(node, setting):
    if not isinstance(node, ast.Call):
        return False
    named = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
    return (
        named == "setattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == setting
    )


def configures_the_setting(tree, setting):
    return any(
        assigns_the_setting(node, setting) or calls_setattr_for_the_setting(node, setting)
        for node in ast.walk(tree)
    )


def names_the_called(node):
    return getattr(node.func, "attr", None) or getattr(node.func, "id", None)


def guards_the_setting(node, setting):
    return (
        isinstance(node, ast.Call)
        and names_the_called(node) in ROOT_GUARDS
        and any(
            isinstance(argument, ast.Constant) and argument.value == setting
            for argument in node.args
        )
    )


def parses_the_library_module(module):
    return ast.parse((PIPELINE_ROOT / f"{module}.py").read_text(encoding="utf-8"))


def names_the_functions_of(tree):
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def names_what_each_function_calls(tree):
    return {
        node.name: {
            names_the_called(held)
            for held in ast.walk(node)
            if isinstance(held, ast.Call)
        }
        for node in names_the_functions_of(tree)
    }


def finds_what_consumes_the_root(module, setting):
    tree = parses_the_library_module(module)
    calls = names_what_each_function_calls(tree)
    consumers = {
        node.name
        for node in names_the_functions_of(tree)
        if any(guards_the_setting(held, setting) for held in ast.walk(node))
    }
    assert consumers, f"nothing in {names_pipeline_module(module)} guards {setting}"
    while True:
        reaching = {
            name for name, called in calls.items() if called & consumers
        } - consumers
        if not reaching:
            return consumers
        consumers |= reaching


def reaches_what_consumes_the_root(tree, module, setting):
    consumers = finds_what_consumes_the_root(module, setting)
    wanted = names_pipeline_module(module)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == wanted:
            if any(alias.name in consumers for alias in node.names):
                return True
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in consumers
            and isinstance(node.ctx, ast.Load)
        ):
            return True
    return False


def finds_callers_that_leave_a_root_unset(roots, library=PIPELINE_ROOT):
    offenders = []
    for root in roots:
        for path in sorted(Path(root).rglob("*.py")):
            if library in path.parents:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for module, settings in sorted(INJECTED_SETTINGS.items()):
                if not reaches_the_pipeline_module(tree, module):
                    continue
                offenders += [
                    f"{path.name} leaves {names_pipeline_module(module)}.{setting} unset"
                    for setting in settings
                    if reaches_what_consumes_the_root(tree, module, setting)
                    and not configures_the_setting(tree, setting)
                ]
    return sorted(offenders)


def test_the_guard_is_not_satisfied_by_a_comment_naming_the_root():
    tree = ast.parse(
        "from sermon.pipeline import segments\n# DATA_ROOT deliberately not set here\n"
    )
    assert reaches_the_pipeline_module(tree, "segments")
    assert not configures_the_setting(tree, "DATA_ROOT")


def test_the_guard_is_not_satisfied_by_a_local_of_the_same_name():
    tree = ast.parse("from sermon.pipeline import segments\nDATA_ROOT = HERE / 'data'\n")
    assert not configures_the_setting(tree, "DATA_ROOT")


@pytest.mark.parametrize(
    "source",
    [
        "from sermon.pipeline import segments",
        "from sermon.pipeline import segments as SEG",
        "from sermon.pipeline.segments import derive",
        "import sermon.pipeline.segments",
        "import sermon.pipeline.segments as seg",
    ],
)
def test_the_guard_sees_every_way_of_reaching_the_module(source):
    assert reaches_the_pipeline_module(ast.parse(source), "segments")


@pytest.mark.parametrize(
    "source",
    [
        "segments.DATA_ROOT = root",
        "SEG.DATA_ROOT: Path = root",
        "library.DATA_ROOT, other.THING = root, root",
        "setattr(segments, 'DATA_ROOT', root)",
        "monkeypatch.setattr(segments, 'DATA_ROOT', root)",
    ],
)
def test_the_guard_accepts_an_assignment_that_actually_sets_the_root(source):
    assert configures_the_setting(ast.parse(source), "DATA_ROOT")


def test_the_guard_covers_a_caller_under_the_production_package(tmp_path):
    caller = tmp_path / "sermon" / "jobs"
    caller.mkdir(parents=True)
    (caller / "finds_the_sermon.py").write_text(
        "from sermon.pipeline.segments import derive\n# DATA_ROOT deliberately not set here\n"
    )
    assert finds_callers_that_leave_a_root_unset([tmp_path]) == [
        "finds_the_sermon.py leaves sermon.pipeline.segments.DATA_ROOT unset"
    ]


@pytest.mark.parametrize(
    ("module", "setting", "consumers"),
    [(module, setting, ROOT_CONSUMERS[(module, setting)])
     for module, setting in sorted(ROOT_CONSUMERS)],
    ids=[f"{module}.{setting}" for module, setting in sorted(ROOT_CONSUMERS)],
)
def test_the_functions_that_consume_a_root_are_the_ones_the_library_reaches(
    module, setting, consumers
):
    assert sorted(finds_what_consumes_the_root(module, setting)) == sorted(consumers)


@pytest.mark.parametrize(
    ("source", "setting"),
    [
        ("from sermon.pipeline.classify import run_whole", "PROMPTS"),
        ("from sermon.pipeline.classify import load_diarization", "DATA"),
        ("from sermon.pipeline import classify\nclassify.run_whole('a-model', doc)\n", "PROMPTS"),
        ("from sermon.pipeline import classify\nclassify.load_diarization('rec1')\n", "DATA"),
    ],
)
def test_the_guard_sees_a_call_that_consumes_the_root(source, setting):
    assert reaches_what_consumes_the_root(ast.parse(source), "classify", setting)


@pytest.mark.parametrize("setting", ("DATA", "PROMPTS"))
@pytest.mark.parametrize(
    "source",
    [
        "from sermon.pipeline import classify",
        "from sermon.pipeline import classify\nclassify.ENDPOINT = host\n",
        "from sermon.pipeline.classify import hms, render_transcript",
    ],
)
def test_the_guard_does_not_treat_a_call_that_spends_no_root_as_one_that_does(source, setting):
    assert not reaches_what_consumes_the_root(ast.parse(source), "classify", setting)


def test_the_guard_does_not_require_a_root_of_a_caller_that_imports_only_a_pure_function(
    tmp_path,
):
    caller = tmp_path / "sermon" / "analysis"
    caller.mkdir(parents=True)
    (caller / "blocks_a_recording.py").write_text(
        "from sermon.pipeline.segments import TAIL_GUARD_S, TAIL_S, coalesce\n"
    )
    assert finds_callers_that_leave_a_root_unset([tmp_path]) == []


def test_the_guard_requires_a_root_of_a_caller_that_reaches_it_through_the_library(tmp_path):
    caller = tmp_path / "sermon" / "analysis"
    caller.mkdir(parents=True)
    (caller / "derives_a_segment.py").write_text(
        "from sermon.pipeline.segments import derive\n"
    )
    (caller / "edges_a_recording.py").write_text(
        "from sermon.pipeline import segments\nsegments.speaker_edges(doc)\n"
    )
    assert finds_callers_that_leave_a_root_unset([tmp_path]) == [
        "derives_a_segment.py leaves sermon.pipeline.segments.DATA_ROOT unset",
        "edges_a_recording.py leaves sermon.pipeline.segments.DATA_ROOT unset",
    ]


def test_the_guard_covers_a_caller_that_runs_the_library_without_setting_roots(tmp_path):
    caller = tmp_path / "sermon" / "jobs"
    caller.mkdir(parents=True)
    (caller / "finds_the_sermon.py").write_text(
        "from sermon.pipeline import classify\n"
        "classify.ENDPOINT = configuration.model_endpoint\n"
        "classify.run_whole('a-model', doc)\n"
        "classify.load_diarization('rec1')\n"
    )
    assert finds_callers_that_leave_a_root_unset([tmp_path]) == [
        "finds_the_sermon.py leaves sermon.pipeline.classify.DATA unset",
        "finds_the_sermon.py leaves sermon.pipeline.classify.PROMPTS unset",
    ]


def test_the_guard_does_not_require_roots_of_a_bind_that_only_assigns_the_endpoint(tmp_path):
    binder = tmp_path / "sermon"
    binder.mkdir(parents=True)
    (binder / "binds_an_endpoint.py").write_text(
        "from sermon.pipeline import classify\n"
        "classify.ENDPOINT = configuration.model_endpoint\n"
    )
    assert finds_callers_that_leave_a_root_unset([tmp_path]) == []


def test_every_caller_of_the_library_sets_the_roots_it_needs():
    assert finds_callers_that_leave_a_root_unset(INJECTING_ROOTS) == []


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


def reaches_a_diarization_artefact(segments):
    return segments.speaker_edges({"recording_id": "rec1"})


def reaches_a_diarization_artefact_through_classify(classify):
    return classify.load_diarization("rec1")


def reaches_a_prompt_template(classify):
    return classify.run_whole("a-model", {"started_at": "", "duration": 0.0, "utterances": []})


INJECTED_ROOTS = (
    ("segments", "DATA_ROOT", reaches_a_diarization_artefact),
    ("classify", "DATA", reaches_a_diarization_artefact_through_classify),
    ("classify", "PROMPTS", reaches_a_prompt_template),
)

injected_root = pytest.mark.parametrize(
    ("module", "setting", "reaches_it"),
    INJECTED_ROOTS,
    ids=[f"{module}.{setting}" for module, setting, _ in INJECTED_ROOTS],
)


def refuses_the_root(module, setting, reaches_it, root, monkeypatch):
    roots = importlib.import_module("sermon.pipeline.roots")
    carried = imports_pipeline_module(module)
    monkeypatch.setattr(carried, setting, root)
    with pytest.raises(roots.RootNotConfigured) as refused:
        reaches_it(carried)
    return str(refused.value)


@injected_root
def test_an_unset_root_names_the_module_and_the_setting(
    module, setting, reaches_it, monkeypatch
):
    complaint = refuses_the_root(module, setting, reaches_it, None, monkeypatch)
    assert names_pipeline_module(module) in complaint
    assert setting in complaint


@injected_root
def test_a_root_that_is_not_a_path_names_the_module_and_the_setting(
    module, setting, reaches_it, tmp_path, monkeypatch
):
    complaint = refuses_the_root(module, setting, reaches_it, str(tmp_path), monkeypatch)
    assert names_pipeline_module(module) in complaint
    assert setting in complaint
    assert "str" in complaint


@injected_root
def test_a_root_that_is_not_a_directory_names_the_module_and_the_setting(
    module, setting, reaches_it, tmp_path, monkeypatch
):
    plain = tmp_path / "not-a-directory"
    plain.write_text("")
    complaint = refuses_the_root(module, setting, reaches_it, plain, monkeypatch)
    assert names_pipeline_module(module) in complaint
    assert setting in complaint
    assert str(plain) in complaint


@pytest.mark.parametrize(
    ("module", "setting", "reaches_it"),
    [entry for entry in INJECTED_ROOTS if entry[1] != "PROMPTS"],
    ids=["segments.DATA_ROOT", "classify.DATA"],
)
def test_a_root_holding_no_diarization_at_all_names_the_module_and_the_setting(
    module, setting, reaches_it, tmp_path, monkeypatch
):
    complaint = refuses_the_root(module, setting, reaches_it, tmp_path, monkeypatch)
    assert names_pipeline_module(module) in complaint
    assert setting in complaint
    assert "diarization" in complaint


def test_load_diarization_finds_nothing_when_the_recording_was_not_diarized(
    tmp_path, monkeypatch
):
    classify = imports_pipeline_module("classify")
    (tmp_path / "diarization").mkdir()
    monkeypatch.setattr(classify, "DATA", tmp_path)
    assert classify.load_diarization("never-diarized") is None


def test_speaker_edges_finds_nothing_when_the_recording_was_not_diarized(tmp_path, monkeypatch):
    segments = imports_pipeline_module("segments")
    (tmp_path / "diarization").mkdir()
    monkeypatch.setattr(segments, "DATA_ROOT", tmp_path)
    assert segments.speaker_edges({"recording_id": "never-diarized"}) == []


AMEN_SEAM = "recording_20260419_102511.t0-rules.whole.v2.json"
AMEN_ENDS = 5075.52
PITCH_BEGINS = 5077.16


def derives_one_stored_block(segments, name):
    stored = reads_spike_json(SPIKE_DATA / "blocks" / name)
    doc = reads_spike_json(
        SPIKE_DATA / "transcripts" / f"{stored['recording_id']}.{stored['asr_config']}.json"
    )
    segments._EDGE_CACHE.clear()
    derived = segments.derive(stored["blocks"], doc)
    return segments.choose(stored.get("model_segments") or [], derived, doc)


@spike_data_required
def test_the_punch_out_lands_in_the_silence_between_the_closing_amen_and_what_follows(
    monkeypatch,
):
    segments = imports_pipeline_module("segments")
    monkeypatch.setattr(segments, "DATA_ROOT", SPIKE_DATA)
    chosen = derives_one_stored_block(segments, AMEN_SEAM)
    assert [AMEN_ENDS <= held["punch_out"] <= PITCH_BEGINS for held in chosen] == [True]


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
