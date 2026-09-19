import subprocess
import sys
from importlib import import_module
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
EXPERIMENTS_ROOT = PROJECT_ROOT / "experiments"

PACKAGES = [
    "sermon",
    "sermon.pipeline",
    "sermon.web",
    "sermon.jobs",
    "sermon.store",
]


def loaded_from_experiments(module):
    location = getattr(module, "__file__", None)
    return bool(location) and EXPERIMENTS_ROOT in Path(location).resolve().parents


@pytest.mark.parametrize("package", PACKAGES)
def test_package_imports(package):
    assert import_module(package).__name__ == package


@pytest.mark.parametrize(
    "stray",
    [
        "sermon.sqlite3",
        "data/sermon.sqlite3",
        "data/sermon.sqlite3-wal",
        "src/sermon/store/sermon.sqlite3",
    ],
)
def test_the_repository_ignores_a_database_wherever_one_lands(stray):
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", stray], cwd=PROJECT_ROOT, check=False
    )
    assert ignored.returncode == 0


def test_no_module_mentions_experiments():
    modules = sorted(SOURCE_ROOT.rglob("*.py"))
    assert modules, f"no modules found under {SOURCE_ROOT}"
    offenders = sorted(
        str(path.relative_to(SOURCE_ROOT))
        for path in modules
        if "experiments" in path.read_text(encoding="utf-8")
    )
    assert offenders == []


def test_no_package_loads_a_module_from_experiments():
    for package in PACKAGES:
        import_module(package)
    offenders = sorted(
        name
        for name, module in list(sys.modules.items())
        if module is not None and loaded_from_experiments(module)
    )
    assert offenders == []
