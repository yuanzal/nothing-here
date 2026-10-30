"""Print src/nothing_here/__init__.py version. Used by release zip naming."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "src" / "nothing_here" / "__init__.py"
_PATTERN = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.M)


def package_version() -> str:
    match = _PATTERN.search(INIT.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"no __version__ in {INIT}")
    return match.group(1)


if __name__ == "__main__":
    print(package_version())
