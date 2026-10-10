from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_POS = re.compile(r"^(vt|vi|adv|adj|abbr|prep|conj|pron|num|pl|n|v|ad|a)\b", re.IGNORECASE)

_NOUN = (
    "She came across the term {word} in the reading.",
    "He remembered the term {word} from the lecture.",
    "They talked about the term {word} after class.",
)
_VERB = (
    "They decided to {word} the old plan.",
    "She offered to {word} the request.",
    "The group agreed to {word} the idea.",
)
_INTRANSITIVE = (
    "The situation started to {word}.",
    "Nothing seemed to {word} after that.",
    "It continued to {word}.",
)
_ADJECTIVE = (
    "The result looked {word} to everyone.",
    "They described the change as {word}.",
    "The street looked {word} at dawn.",
)
_ADVERB = (
    "She replied {word} and smiled.",
    "He worked {word} until midnight.",
    "They listened {word} to the lecture.",
)
_ANY = (
    "She came across the term {word} in the reading.",
    "He remembered the term {word} from the lecture.",
    "They talked about the term {word} after class.",
)
_ABBR = (
    "The report shortens the name to {word}.",
    "Students write it as {word}.",
    "The footnote expands {word}.",
)

_TEMPLATES = {
    "n": _NOUN,
    "pl": _NOUN,
    "num": ("The sequence includes {word}.", "The chart marks {word}.", "The list reaches {word}."),
    "vt": _VERB,
    "v": _VERB,
    "vi": _INTRANSITIVE,
    "a": _ADJECTIVE,
    "adj": _ADJECTIVE,
    "ad": _ADVERB,
    "adv": _ADVERB,
    "abbr": _ABBR,
    "any": _ANY,
}


def sentence_for(word: str, translation: str = "") -> str:
    token = " ".join(word.split())
    if not token or any(char in token for char in "\"{}\\\n\r\t"):
        return ""
    if len(token) > 48:
        return ""
    kind = _kind(translation)
    if kind == "any" and " " in token:
        kind = "vt"
    templates = _TEMPLATES.get(kind, _ANY)
    digest = hashlib.sha256(token.casefold().encode("utf-8")).digest()
    sentence = templates[digest[0] % len(templates)].format(word=token)
    if token.casefold() not in sentence.casefold():
        return ""
    return sentence


def _kind(translation: str) -> str:
    line = translation.replace("\\n", "\n").lstrip().split("\n", 1)[0].strip().lower()
    match = _POS.match(line)
    if match is None:
        return "any"
    return match.group(1).lower()


def fill_file(path: Path) -> tuple[int, int]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    filled = 0
    for row in rows:
        example = sentence_for(str(row.get("word") or ""), str(row.get("translation") or ""))
        row["example"] = example
        if example:
            filled += 1
    payload = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
    return filled, len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill example sentences in a vocab JSON file.")
    parser.add_argument("json_path", type=Path, nargs="?", default=Path(__file__).resolve().parents[1] / "data" / "ielts.json")
    args = parser.parse_args(argv)
    if not args.json_path.is_file():
        print(f"JSON not found: {args.json_path}", file=sys.stderr)
        return 1
    filled, total = fill_file(args.json_path)
    print(f"wrote {filled} examples of {total} entries to {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
