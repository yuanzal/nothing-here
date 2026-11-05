"""Print the release zip version.

On a GitHub tag build, GITHUB_REF_NAME is the tag (v0.5.4 -> 0.5.4).
Otherwise fall back to src/nothing_here/__init__.py.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "src" / "nothing_here" / "__init__.py"
_PATTERN = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.M)


def package_version() -> str:
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        return version_from_tag(os.environ.get("GITHUB_REF_NAME", ""))
    return _version_from_init()


def version_from_tag(ref_name: str) -> str:
    name = ref_name.strip()
    if name.startswith("v"):
        name = name[1:]
    if not name:
        raise SystemExit(f"empty version in tag {ref_name!r}")
    return name


def _version_from_init() -> str:
    match = _PATTERN.search(INIT.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"no __version__ in {INIT}")
    return match.group(1)


if __name__ == "__main__":
    print(package_version())
