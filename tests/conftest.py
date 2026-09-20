import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = PROJECT_ROOT / "features"
STEP_ROOT = Path(__file__).parent / "steps"


def names_step_module(path):
    return ".".join((STEP_ROOT.name, *path.relative_to(STEP_ROOT).with_suffix("").parts))


def loads_step_definitions(path):
    location = importlib.util.spec_from_file_location(names_step_module(path), path)
    module = importlib.util.module_from_spec(location)
    sys.modules[location.name] = module
    try:
        location.loader.exec_module(module)
    except Exception as failure:
        raise pytest.UsageError(
            f"{path.relative_to(PROJECT_ROOT)} could not be imported: "
            f"{type(failure).__name__}: {failure}"
        ) from failure
    return module


def refuses_hooks(manager, module, path):
    hooks = sorted(name for name in dir(module) if manager.parse_hookimpl_opts(module, name))
    if hooks:
        raise pytest.UsageError(
            f"{path.relative_to(PROJECT_ROOT)} defines {', '.join(hooks)}; "
            f"a pytest hook belongs in a conftest, not in a step definition module"
        )


def pytest_configure(config):
    for path in sorted(STEP_ROOT.rglob("[!_]*.py")):
        module = loads_step_definitions(path)
        refuses_hooks(config.pluginmanager, module, path)
        config.pluginmanager.register(module, names_step_module(path))


@pytest.fixture(scope="session")
def spec_guardrail():
    location = importlib.util.spec_from_file_location(
        "validate_spec", SPEC_ROOT / "validate_spec.py"
    )
    module = importlib.util.module_from_spec(location)
    location.loader.exec_module(module)
    return module


def pytest_bdd_apply_tag(tag, function):
    if tag != "deferred":
        return None
    pytest.mark.deferred(function)
    pytest.mark.skip(reason="Not in v1")(function)
    return True


@pytest.fixture
def segment(store):
    from datetime import UTC, datetime

    from sermon.store import Recording, Segment

    existing = store.lists(Segment)
    if existing:
        return existing[0]
    recordings = store.lists(Recording)
    if not recordings:
        recordings = [
            store.saves(
                Recording(
                    recording_id="recording_20260816_090014",
                    object_key="recordings/recording_20260816_090014.flac",
                    state="awaiting_review",
                    started_at=datetime(2026, 8, 16, 9, 0, 14, tzinfo=UTC),
                    started_at_source="key",
                    size_bytes=1,
                )
            )
        ]
    return store.saves(
        Segment(
            recording_id=recordings[0].recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=7220.0,
            span_end_seconds=9812.0,
            punch_in_seconds=7220.0,
            punch_out_seconds=9812.0,
        )
    )
