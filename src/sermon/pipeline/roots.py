"""Refuse an injected root that no caller configured."""

from __future__ import annotations

from pathlib import Path


class RootNotConfigured(RuntimeError):
    pass


def requires_root(module: str, setting: str, root: object) -> Path:
    if root is None:
        raise RootNotConfigured(f"nothing set {module}.{setting}; the caller owning the layout must")
    if not isinstance(root, Path):
        raise RootNotConfigured(f"{module}.{setting} is a {type(root).__name__}, not a Path")
    if not root.is_dir():
        raise RootNotConfigured(f"{module}.{setting} is {str(root)!r}, which is not a directory")
    return root


def requires_directory_under_root(module: str, setting: str, root: object, name: str) -> Path:
    under = requires_root(module, setting, root) / name
    if not under.is_dir():
        raise RootNotConfigured(
            f"{module}.{setting} is {str(under.parent)!r}, which holds no {name} directory"
        )
    return under
