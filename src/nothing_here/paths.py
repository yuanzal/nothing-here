"""Resolve bundled files in development and in a PyInstaller build."""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return repo_root()


def data_file(name: str) -> Path:
    return bundle_root() / "data" / name


def ui_asset(name: str) -> Path:
    # Frozen builds extract ui files to nothing_here/ui (see scripts/nothing_here.spec).
    # In a source checkout the file sits next to this package, under src/.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "nothing_here" / "ui" / name
    return Path(__file__).resolve().parent / "ui" / name


def ui_text(name: str) -> str:
    """Read a bundled UI file as text. Frozen builds use the extracted datas copy."""
    path = ui_asset(name)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    from importlib.resources import files

    return files("nothing_here.ui").joinpath(name).read_text(encoding="utf-8")
