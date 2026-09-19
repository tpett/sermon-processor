import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = PROJECT_ROOT / "features"


@pytest.fixture(scope="session")
def spec_guardrail():
    location = importlib.util.spec_from_file_location(
        "validate_spec", SPEC_ROOT / "validate_spec.py"
    )
    module = importlib.util.module_from_spec(location)
    location.loader.exec_module(module)
    return module
