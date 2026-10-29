"""Build data/jp_n5.json … jp_n1.json from OpenJLPT + Tomoshi 中文释义.

Usage (from repo root):
  python scripts/build_jlpt.py
  python scripts/build_jlpt.py --offline
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
OPENJLPT = DATA / "cache" / "openjlpt"
TOMOSHI = DATA / "cache" / "tomoshi"
LEVELS = ("n5", "n4", "n3", "n2", "n1")
OPENJLPT_URL = "https://raw.githubusercontent.com/evanclan/OpenJLPT/main/data/json/vocab/{level}.json"
TOMOSHI_URL = "https://github.com/tomoshi-app/tomoshi-dict-data/releases/latest/download/tomoshi-dict-open.db.zst"


def convert(
    items: list[object],
    zh_by_id: dict[str, str],
    zh_by_form: dict[str, str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word") or "").strip()
        if not word:
            continue
        key = word.casefold()
        if key in seen:
            continue
        seen.add(key)
        jmdict_id = item.get("jmdict_id")
        zh = zh_by_id.get(str(jmdict_id)) if jmdict_id not in (None, "") else None
        if not zh:
            zh = zh_by_form.get(word)
        meanings = item.get("meanings") or []
        english = "；".join(str(part).strip() for part in meanings if str(part).strip())
        example = ""
        for sentence in item.get("examples") or []:
            if not isinstance(sentence, dict):
                continue
            ja = str(sentence.get("ja") or "").strip()
            if ja:
                example = ja
                break
        rows.append(
            {
                "word": word,
                "phonetic": str(item.get("reading") or "").strip(),
                "translation": zh or english,
                "example": example,
            }
        )
    return rows


def zh_gloss(raw: str) -> str:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    senses = payload.get("senses") or {}
    parts: list[str] = []
    keys = sorted(senses, key=lambda item: int(item) if str(item).isdigit() else 999)
    for key in keys:
        sense = senses[key]
        if not isinstance(sense, dict):
            continue
        texts = [
            str(gloss.get("text") or "").strip()
            for gloss in sense.get("glosses") or []
            if isinstance(gloss, dict)
        ]
        joined = "，".join(text for text in texts if text)
        if joined:
            parts.append(joined)
        if len(parts) >= 3:
            break
    return "；".join(parts)


def _load_level(level: str, offline: bool) -> list[object]:
    OPENJLPT.mkdir(parents=True, exist_ok=True)
    path = OPENJLPT / f"{level}.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    if offline:
        raise FileNotFoundError(path)
    url = OPENJLPT_URL.format(level=level)
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read()
    path.write_bytes(payload)
    return json.loads(payload.decode("utf-8"))


def _tomoshi_db(offline: bool) -> Path:
    TOMOSHI.mkdir(parents=True, exist_ok=True)
    db_path = TOMOSHI / "tomoshi-dict-open.db"
    zst_path = TOMOSHI / "tomoshi-dict-open.db.zst"
    if db_path.is_file():
        return db_path
    if not zst_path.is_file():
        if offline:
            raise FileNotFoundError(zst_path)
        urllib.request.urlretrieve(TOMOSHI_URL, zst_path)
    import zstandard

    with zst_path.open("rb") as src, db_path.open("wb") as dst:
        zstandard.ZstdDecompressor().copy_stream(src, dst)
    return db_path


def load_zh_maps(offline: bool) -> tuple[dict[str, str], dict[str, str]]:
    conn = sqlite3.connect(_tomoshi_db(offline))
    zh_by_id: dict[str, str] = {}
    for entry_id, data in conn.execute("SELECT entry_id, data FROM zh_defs"):
        gloss = zh_gloss(str(data))
        if gloss:
            zh_by_id[str(entry_id)] = gloss
    zh_by_form: dict[str, str] = {}
    for text, entry_id in conn.execute("SELECT text, entry_id FROM forms"):
        if text in zh_by_form:
            continue
        gloss = zh_by_id.get(str(entry_id))
        if gloss:
            zh_by_form[str(text)] = gloss
    conn.close()
    return zh_by_id, zh_by_form


def write_level(
    level: str,
    offline: bool,
    zh_by_id: dict[str, str],
    zh_by_form: dict[str, str],
) -> int:
    chunk = _load_level(level, offline)
    if not isinstance(chunk, list):
        raise ValueError(f"{level} is not a JSON array")
    rows = convert(chunk, zh_by_id, zh_by_form)
    output = DATA / f"jp_{level}.json"
    output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    chinese = sum(1 for row in rows if row["translation"] and not _looks_english(row["translation"]))
    filled = sum(1 for row in rows if row["example"])
    print(
        f"wrote {len(rows)} `{level}` entries to {output} "
        f"({chinese} with Chinese gloss, {filled} with examples)"
    )
    return len(rows)


def _looks_english(text: str) -> bool:
    letters = sum(char.isascii() and char.isalpha() for char in text)
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in text)
    return letters > 0 and cjk == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Japanese vocab JSON from OpenJLPT + Tomoshi.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Only use cached OpenJLPT / Tomoshi files; do not download",
    )
    args = parser.parse_args(argv)
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        zh_by_id, zh_by_form = load_zh_maps(offline=args.offline)
        for level in LEVELS:
            write_level(level, offline=args.offline, zh_by_id=zh_by_id, zh_by_form=zh_by_form)
    except FileNotFoundError as exc:
        print(f"cached dictionary file missing: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
