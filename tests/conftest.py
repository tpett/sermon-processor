import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = PROJECT_ROOT / "features"
STEP_ROOT = Path(__file__).parent / "steps"


def loads_step_definitions(path):
    location = importlib.util.spec_from_file_location(f"{STEP_ROOT.name}.{path.stem}", path)
    module = importlib.util.module_from_spec(location)
    sys.modules[location.name] = module
    location.loader.exec_module(module)
    return module


def pytest_configure(config):
    for path in sorted(STEP_ROOT.glob("[!_]*.py")):
        config.pluginmanager.register(loads_step_definitions(path), f"{STEP_ROOT.name}.{path.stem}")


@pytest.fixture(scope="session")
def spec_guardrail():
    location = importlib.util.spec_from_file_location(
        "validate_spec", SPEC_ROOT / "validate_spec.py"
    )
    module = importlib.util.module_from_spec(location)
    sys.modules[location.name] = module
    location.loader.exec_module(module)
    return module


def pytest_bdd_apply_tag(tag, function):
    if tag != "deferred":
        return None
    pytest.mark.deferred(function)
    pytest.mark.skip(reason="Not in v1")(function)
    return True
