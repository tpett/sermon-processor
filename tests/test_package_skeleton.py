import importlib.util
import shutil
import subprocess
import sys
import zipfile
from importlib import import_module
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
EXPERIMENTS_ROOT = PROJECT_ROOT / "experiments"
WEB_ASSETS = ("templates/index.html", "templates/partials/segment.html", "static/waveform.js")
BUILDS_A_WHEEL = "from setuptools import build_meta; print(build_meta.build_wheel('.'))"

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


def modules_reached_through(packages):
    pending = [import_module(name) for name in packages]
    seen = set()
    found = {}
    while pending:
        module = pending.pop()
        if not isinstance(module, ModuleType):
            continue
        marker = id(module)
        if marker in seen:
            continue
        seen.add(marker)
        name = getattr(module, "__name__", None)
        if name:
            found[name] = module
        try:
            values = vars(module).values()
        except TypeError:
            continue
        for value in values:
            if isinstance(value, ModuleType):
                pending.append(value)
                continue
            origin = getattr(value, "__module__", None)
            if origin and (other := sys.modules.get(origin)) is not None:
                pending.append(other)
    return found


def experiments_modules_reached_through(packages):
    return sorted(
        name
        for name, module in modules_reached_through(packages).items()
        if loaded_from_experiments(module)
    )


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
    assert experiments_modules_reached_through(PACKAGES) == []


def test_hygiene_guard_ignores_experiments_modules_loaded_elsewhere():
    location = importlib.util.spec_from_file_location(
        "experiments_baseline_probe", EXPERIMENTS_ROOT / "baseline.py"
    )
    module = importlib.util.module_from_spec(location)
    sys.modules[location.name] = module
    try:
        location.loader.exec_module(module)
        assert experiments_modules_reached_through(PACKAGES) == []
    finally:
        sys.modules.pop(location.name, None)


def plants_web_assets(root):
    shutil.copy(PROJECT_ROOT / "pyproject.toml", root / "pyproject.toml")
    shutil.copytree(SOURCE_ROOT, root / "src", ignore=shutil.ignore_patterns("__pycache__"))
    for asset in WEB_ASSETS:
        planted = root / "src" / "sermon" / "web" / asset
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(f"the {asset} a wheel must carry\n")


def builds_a_wheel(root):
    built = subprocess.run(
        [sys.executable, "-c", BUILDS_A_WHEEL],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    return root / built.stdout.splitlines()[-1]


def test_a_built_wheel_carries_the_templates_and_client_assets_under_the_web_package(tmp_path):
    plants_web_assets(tmp_path)
    with zipfile.ZipFile(builds_a_wheel(tmp_path)) as wheel:
        carried = set(wheel.namelist())
    assert "sermon/web/__init__.py" in carried
    assert {f"sermon/web/{asset}" for asset in WEB_ASSETS} <= carried
