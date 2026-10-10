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
    return bundle_root() / "nothing_here" / "ui" / name
