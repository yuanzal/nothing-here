"""Build tagged vocab JSON files from an ECDICT CSV.

Usage (from repo root):
  python scripts/build_ecdict.py path/to/ecdict.csv --tag cet4 -o data/cet4.json
  python scripts/build_ecdict.py path/to/ecdict.csv --all
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"

# ECDICT tag → (source_id file stem, display label for logs)
KNOWN = {
    "ielts": "ielts",
    "cet4": "cet4",
    "cet6": "cet6",
    "ky": "ky",
}


def has_tag(tag_field: str, wanted: str) -> bool:
    return wanted in tag_field.split()


def convert(
    csv_path: Path,
    tag: str,
    examples: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    kept = examples or {}
    rows: list[dict[str, str]] = []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for rec in reader:
            if not has_tag(rec.get("tag") or "", tag):
                continue
            word = (rec.get("word") or "").strip()
            if not word:
                continue
            rows.append(
                {
                    "word": word,
                    "phonetic": rec.get("phonetic") or "",
                    "translation": rec.get("translation") or "",
                    "example": kept.get(word.casefold(), ""),
                }
            )
    return rows


def _saved_examples(*paths: Path) -> dict[str, str]:
    saved: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        for row in rows:
            word = str(row.get("word") or "").strip().casefold()
            example = str(row.get("example") or "").strip()
            if word and example and word not in saved:
                saved[word] = example
    return saved


def write_tag(csv_path: Path, tag: str, output: Path, example_sources: list[Path]) -> int:
    examples = _saved_examples(output, *example_sources)
    rows = convert(csv_path, tag, examples)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    filled = sum(1 for row in rows if row["example"])
    print(f"wrote {len(rows)} `{tag}` entries to {output} ({filled} with examples)")
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build vocab JSON from ECDICT by tag.")
    parser.add_argument("csv_path", type=Path, help="Path to ECDICT ecdict.csv")
    parser.add_argument("--tag", choices=sorted(KNOWN), help="Single ECDICT tag to export")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export ielts + cet4 + cet6 + ky into data/",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output path (single --tag only)")
    args = parser.parse_args(argv)

    if not args.csv_path.is_file():
        print(f"CSV not found: {args.csv_path}", file=sys.stderr)
        return 1
    if not args.all and not args.tag:
        print("Provide --tag TAG or --all", file=sys.stderr)
        return 1
    if args.all and args.tag:
        print("Use either --tag or --all, not both", file=sys.stderr)
        return 1

    shared = [DATA / "ielts.json", DATA / "cet4.json", DATA / "cet6.json", DATA / "ky.json"]

    if args.all:
        for tag, stem in KNOWN.items():
            write_tag(args.csv_path, tag, DATA / f"{stem}.json", shared)
        return 0

    out = args.output or DATA / f"{KNOWN[args.tag]}.json"
    write_tag(args.csv_path, args.tag, out, shared)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
