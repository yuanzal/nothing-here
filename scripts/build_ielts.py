"""Compatibility wrapper. Prefer scripts/build_ecdict.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_ecdict import main as build_main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args and args[0] not in ("-h", "--help") and "--tag" not in args and "--all" not in args:
        csv = args[0]
        rest = args[1:]
        return build_main([csv, "--tag", "ielts", *rest])
    return build_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
