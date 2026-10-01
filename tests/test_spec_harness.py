import re
import subprocess
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

import pytest
from gherkin.parser import Parser

from conftest import SPEC_OUTCOMES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = PROJECT_ROOT / "features"
SPEC_MODULE = "tests/test_spec.py"
STEP_MODULE = "steps.discovery_steps"
SPEC_SHAPE = "spec OK — 34 files, 468 scenarios, 144 rules"
SPEC_TESTS = 614
SPEC_STEPS = 1939
DEFERRED_TESTS = 7
SUMMARY_LINE = re.compile(
    r"^[= ]*(?:no tests ran|\d+ [a-z]+).* in \d+\.\d+s(?: \(\d+:\d\d:\d\d\))?[= ]*$"
)


@lru_cache(maxsize=None)
def runs_pytest(*arguments, cwd=PROJECT_ROOT):
    finished = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return finished.returncode, finished.stdout + finished.stderr


def finds_summary(report):
    summaries = [line for line in report.splitlines() if SUMMARY_LINE.match(line.strip())]
    assert summaries, report
    return summaries[-1]


def counted(outcome, report):
    found = re.search(rf"(\d+) {outcome}", finds_summary(report))
    return int(found.group(1)) if found else 0


def plants_step_module(root, name, source):
    steps = root / "tests" / "steps"
    steps.mkdir(parents=True)
    (steps / name).write_text(source)
    conftest = root / "tests" / "conftest.py"
    conftest.write_text((PROJECT_ROOT / "tests" / "conftest.py").read_text())
    (root / "tests" / "test_nothing.py").write_text("def test_nothing():\n    assert True\n")


def tag_names(node):
    return {tag["name"].lstrip("@") for tag in node.get("tags", [])}


def expanded_scenarios(children, inherited, tag):
    total = 0
    for child in children:
        if "rule" in child:
            rule = child["rule"]
            total += expanded_scenarios(rule["children"], inherited | tag_names(rule), tag)
        elif "scenario" in child:
            scenario = child["scenario"]
            if tag is not None and tag not in inherited | tag_names(scenario):
                continue
            examples = scenario.get("examples") or []
            total += sum(len(one.get("tableBody") or []) for one in examples) if examples else 1
    return total


def finds_deferrals_above_scenario_level():
    offenders = []
    for spec_file in sorted(SPEC_ROOT.rglob("*.feature")):
        feature = Parser().parse(spec_file.read_text())["feature"]
        blocks = [feature] + [child["rule"] for child in feature["children"] if "rule" in child]
        offenders += [
            f"{spec_file.relative_to(SPEC_ROOT)}:{block['location']['line']}"
            for block in blocks
            if "deferred" in tag_names(block)
        ]
    return sorted(offenders)


def counts_steps_in(children):
    total = 0
    for child in children:
        for block in child.values():
            total += len(block.get("steps") or [])
            total += counts_steps_in(block.get("children") or [])
    return total


def counts_declared_steps():
    return sum(
        counts_steps_in(Parser().parse(spec_file.read_text())["feature"]["children"])
        for spec_file in sorted(SPEC_ROOT.rglob("*.feature"))
    )


def declared_scenarios(tag=None):
    total = 0
    for spec_file in sorted(SPEC_ROOT.rglob("*.feature")):
        feature = Parser().parse(spec_file.read_text())["feature"]
        total += expanded_scenarios(feature["children"], tag_names(feature), tag)
    return total


class SpecRunInSubprocess:
    def __init__(self, returncode, report):
        self.returncode = returncode
        self.report = report

    def counted(self, outcome):
        return counted(outcome, self.report)

    def executed(self):
        return self.counted("passed") + self.counted("failed")

    def intact(self):
        return "INTERNALERROR" not in self.report and self.returncode in (0, 1)

    def evidence(self):
        return self.report


class SpecRunThisSessionIsPartOf:
    def __init__(self, watcher):
        self.watcher = watcher

    def counted(self, outcome):
        return self.watcher.counted(outcome)

    def executed(self):
        return self.counted("passed") + self.counted("failed")

    def intact(self):
        return not self.watcher.internal_error

    def evidence(self):
        return self.watcher.evidence()


@pytest.fixture(scope="session")
def spec_run(pytestconfig):
    watcher = pytestconfig.pluginmanager.get_plugin(SPEC_OUTCOMES)
    if watcher is not None and watcher.sees_every_scenario(declared_scenarios()):
        return SpecRunThisSessionIsPartOf(watcher)
    return SpecRunInSubprocess(*runs_pytest("-q", SPEC_MODULE))


def test_the_spec_is_the_size_this_harness_was_built_for(spec_guardrail, capsys):
    spec_guardrail.main()
    summary = capsys.readouterr().out
    report = runs_pytest("--collect-only", "-q", SPEC_MODULE)[1]
    assert SPEC_SHAPE in summary, summary
    assert counted("tests collected", report) == SPEC_TESTS, report


def test_the_spec_declares_the_step_count_this_harness_was_built_for():
    assert counts_declared_steps() == SPEC_STEPS


def test_the_spec_module_collects_every_declared_scenario():
    returncode, report = runs_pytest("--collect-only", "-q", SPEC_MODULE)
    assert (returncode, counted("tests collected", report)) == (0, declared_scenarios()), report


def test_the_whole_suite_collects_the_spec_and_its_own_tests():
    returncode, report = runs_pytest("--collect-only", "-q")
    beside_the_spec = runs_pytest("--collect-only", "-q", f"--ignore={SPEC_MODULE}")[1]
    assert (returncode, counted("tests collected", report)) == (
        0,
        declared_scenarios() + counted("tests collected", beside_the_spec),
    ), report


def test_no_tag_the_spec_uses_is_an_unknown_mark():
    returncode, report = runs_pytest(
        "--collect-only", "-q", "-W", "error::pytest.PytestUnknownMarkWarning", SPEC_MODULE
    )
    assert "PytestUnknownMarkWarning" not in report, report
    assert returncode == 0, report


def test_the_registered_markers_are_the_tags_the_spec_declares(spec_guardrail):
    settings = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    registered = settings["tool"]["pytest"]["ini_options"].get("markers", [])
    assert {f"@{entry.split(':', 1)[0]}" for entry in registered} == spec_guardrail.declared_tags(
        SPEC_ROOT / "README.md"
    )


def test_scenarios_deferred_out_of_v1_are_skipped():
    returncode, report = runs_pytest("-q", "-m", "deferred", SPEC_MODULE)
    assert (returncode, counted("skipped", report)) == (0, DEFERRED_TESTS), report
    assert declared_scenarios("deferred") == DEFERRED_TESTS


def test_nothing_above_a_scenario_is_deferred():
    assert finds_deferrals_above_scenario_level() == []


def test_a_step_module_that_defines_a_hook_is_refused(tmp_path):
    plants_step_module(
        tmp_path,
        "hooked_steps.py",
        "def pytest_collection_modifyitems(items):\n    items.clear()\n",
    )
    returncode, report = runs_pytest("-q", cwd=tmp_path)
    assert "INTERNALERROR" not in report, report
    assert "tests/steps/hooked_steps.py" in report, report
    assert "pytest_collection_modifyitems" in report, report
    assert returncode == pytest.ExitCode.USAGE_ERROR, report


def test_a_step_module_that_cannot_be_imported_names_itself(tmp_path):
    plants_step_module(tmp_path, "unimportable_steps.py", "def broken(:\n")
    returncode, report = runs_pytest("-q", cwd=tmp_path)
    assert "INTERNALERROR" not in report, report
    assert "tests/steps/unimportable_steps.py" in report, report
    assert returncode == pytest.ExitCode.USAGE_ERROR, report


def test_a_step_module_is_the_object_the_import_system_holds(pytestconfig):
    plugin = pytestconfig.pluginmanager.get_plugin(STEP_MODULE)
    assert plugin is not None
    assert plugin is sys.modules.get(STEP_MODULE)


def test_a_scenario_with_no_step_definitions_fails_rather_than_errors(tmp_path):
    (tmp_path / "undefined.feature").write_text(
        "Feature: A scenario nobody has implemented\n"
        "  Scenario: Its steps are undefined\n"
        "    Given no step definition exists for this line\n"
    )
    (tmp_path / "test_undefined.py").write_text(
        "from pytest_bdd import scenarios\n\nscenarios('undefined.feature')\n"
    )
    returncode, report = runs_pytest("-q", cwd=tmp_path)
    assert "StepDefinitionNotFoundError" in report, report
    assert (returncode, counted("failed", report), counted("error", report)) == (1, 1, 0), report


@pytest.mark.slow
def test_running_the_spec_executes_every_scenario_it_does_not_defer(spec_run):
    assert (spec_run.executed(), spec_run.counted("skipped")) == (
        SPEC_TESTS - DEFERRED_TESTS,
        DEFERRED_TESTS,
    ), spec_run.evidence()


@pytest.mark.slow
def test_running_the_spec_reports_no_errors(spec_run):
    assert spec_run.counted("error") == 0, spec_run.evidence()
    assert spec_run.intact(), spec_run.evidence()
