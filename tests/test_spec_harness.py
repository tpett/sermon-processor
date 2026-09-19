import re
import subprocess
import sys
import tomllib
from pathlib import Path

from gherkin.parser import Parser

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = PROJECT_ROOT / "features"
SPEC_MODULE = "tests/test_spec.py"


def runs_pytest(*arguments, cwd=PROJECT_ROOT):
    finished = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return finished.returncode, finished.stdout + finished.stderr


def counted(outcome, report):
    summary = [line for line in report.splitlines() if line.strip()][-1]
    found = re.search(rf"(\d+) {outcome}", summary)
    return int(found.group(1)) if found else 0


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


def declared_scenarios(tag=None):
    total = 0
    for spec_file in sorted(SPEC_ROOT.rglob("*.feature")):
        feature = Parser().parse(spec_file.read_text())["feature"]
        total += expanded_scenarios(feature["children"], tag_names(feature), tag)
    return total


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
    assert (returncode, counted("skipped", report)) == (0, declared_scenarios("deferred")), report


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


def test_running_the_spec_reports_no_errors():
    returncode, report = runs_pytest("-q", "--maxfail=1", SPEC_MODULE)
    assert counted("error", report) == 0, report
    assert "INTERNALERROR" not in report, report
    assert returncode in (0, 1), report
