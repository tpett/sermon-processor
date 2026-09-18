import ast
from importlib import import_module
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"

PACKAGES = [
    "sermon",
    "sermon.pipeline",
    "sermon.web",
    "sermon.jobs",
    "sermon.store",
]


def imported_roots(module_path):
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


@pytest.mark.parametrize("package", PACKAGES)
def test_package_imports(package):
    assert import_module(package).__name__ == package


def test_no_module_imports_from_experiments():
    modules = sorted(SOURCE_ROOT.rglob("*.py"))
    assert modules, f"no modules found under {SOURCE_ROOT}"
    offenders = sorted(
        str(path.relative_to(SOURCE_ROOT))
        for path in modules
        if "experiments" in set(imported_roots(path))
    )
    assert offenders == []
