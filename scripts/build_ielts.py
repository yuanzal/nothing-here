from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from example_sentences import sentence_for

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "ielts.json"


def has_ielts_tag(tag: str) -> bool:
    return "ielts" in tag.split()


def convert(csv_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for rec in reader:
            if not has_ielts_tag(rec.get("tag") or ""):
                continue
            word = (rec.get("word") or "").strip()
            if not word:
                continue
            translation = rec.get("translation") or ""
            rows.append(
                {
                    "word": word,
                    "phonetic": rec.get("phonetic") or "",
                    "translation": translation,
                    "example": sentence_for(word, translation),
                }
            )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build data/ielts.json from an ECDICT CSV.")
    parser.add_argument("csv_path", type=Path, help="Path to ECDICT ecdict.csv")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.csv_path.is_file():
        print(f"CSV not found: {args.csv_path}", file=sys.stderr)
        return 1

    rows = convert(args.csv_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} IELTS entries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
