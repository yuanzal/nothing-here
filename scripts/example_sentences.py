"""Replace vocab examples with real sentences.

Tatoeba English sentences (CC BY 2.0 FR, https://tatoeba.org) are searched
first. Words still missing a sentence are filled from Youdao bilingual
examples. The app itself never calls the network.
"""

from __future__ import annotations

import argparse
import bz2
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = REPO_ROOT / "data" / "ielts.json"
DEFAULT_DUMP = REPO_ROOT / "data" / "cache" / "eng_sentences.tsv.bz2"
DEFAULT_CACHE = REPO_ROOT / "data" / "cache" / "youdao-examples.json"
TATOEBA_URL = "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2"
YOUDAO_URL = "https://dict.youdao.com/jsonapi?le=en&q="
USER_AGENT = "NothingHere/1.0 (personal vocab examples; Tatoeba CC BY 2.0 FR)"

_TOKEN = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_SPLIT = re.compile(r"(?<=[.!?])\s+")


def fill_file(path: Path, dump_path: Path, cache_path: Path) -> tuple[int, int, int]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    examples, tatoeba_hits = sentences_from_tatoeba(rows, dump_path)
    missing = [str(row.get("word") or "").strip() for row in rows]
    missing = [word for word in missing if word and not examples.get(word.casefold())]
    youdao_hits = fill_from_youdao(missing, examples, cache_path)
    filled = 0
    for row in rows:
        word = str(row.get("word") or "").strip()
        example = examples.get(word.casefold(), "")
        row["example"] = example
        if example:
            filled += 1
    payload = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
    return filled, tatoeba_hits, youdao_hits


def sentences_from_tatoeba(rows: list[dict[str, object]], dump_path: Path) -> tuple[dict[str, str], int]:
    if not dump_path.is_file():
        raise FileNotFoundError(f"Tatoeba dump not found: {dump_path}")
    wanted: set[str] = set()
    phrases: list[tuple[str, str, re.Pattern[str]]] = []
    for row in rows:
        word = str(row.get("word") or "").strip().casefold()
        if not word:
            continue
        wanted.add(word)
        if " " in word or "-" in word:
            for form in _surface_forms(word):
                phrases.append((word, form, re.compile(rf"(?<![A-Za-z]){re.escape(form)}(?![A-Za-z])")))
    best: dict[str, tuple[int, str]] = {}
    seen_lines = 0
    with bz2.open(dump_path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            seen_lines += 1
            if seen_lines % 200000 == 0:
                print(f"tatoeba scanned {seen_lines} lines, matched {len(best)}", file=sys.stderr)
            text = _sentence_text(line)
            if text is None:
                continue
            folded = text.casefold()
            seen: set[str] = set()
            for token in _TOKEN.findall(text):
                for lemma, exact in _lemmas(token.casefold(), wanted):
                    if lemma in seen:
                        continue
                    seen.add(lemma)
                    _keep(best, lemma, text, exact)
            for phrase, form, pattern in phrases:
                if form not in folded or pattern.search(folded) is None:
                    continue
                _keep(best, phrase, text, True)
    examples = {word: sentence for word, (_score, sentence) in best.items()}
    return examples, len(examples)


def fill_from_youdao(words: list[str], examples: dict[str, str], cache_path: Path) -> int:
    cache = _load_cache(cache_path)
    pending = [word for word in words if not cache.get(word.casefold())]
    if pending:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        done = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_youdao_sentence, word): word for word in pending}
            for future in as_completed(futures):
                word = futures[future]
                try:
                    cache[word.casefold()] = future.result()
                except Exception as exc:  # noqa: BLE001
                    print(f"youdao skip {word}: {exc}", file=sys.stderr)
                    cache[word.casefold()] = ""
                done += 1
                if done % 100 == 0:
                    _save_cache(cache_path, cache)
                    print(f"youdao {done}/{len(pending)}", file=sys.stderr)
        _save_cache(cache_path, cache)
    added = 0
    for word in words:
        sentence = cache.get(word.casefold(), "")
        if sentence:
            examples[word.casefold()] = sentence
            added += 1
    return added


def _youdao_sentence(word: str) -> str:
    time.sleep(0.2)
    url = YOUDAO_URL + urllib.parse.quote(word)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    delay = 0.4
    for _attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503):
                return ""
            time.sleep(delay)
            delay *= 2
        except (urllib.error.URLError, TimeoutError):
            time.sleep(delay)
            delay *= 2
    else:
        return ""
    pairs = (payload.get("blng_sents_part") or {}).get("sentence-pair") or []
    best_score: int | None = None
    best = ""
    for pair in pairs:
        raw = str(pair.get("sentence") or "")
        for piece in _pieces(raw):
            exact = _contains(piece, word)
            if exact is None:
                continue
            score = _score(piece, exact)
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_score = score
                best = piece
    return best


def _sentence_text(line: str) -> str | None:
    parts = line.rstrip("\n").split("\t", 2)
    if len(parts) < 3 or parts[1] != "eng":
        return None
    text = " ".join(parts[2].split())
    if _score(text, True) is None and _score(text, False) is None:
        return None
    return text


def _keep(best: dict[str, tuple[int, str]], word: str, text: str, exact: bool) -> None:
    score = _score(text, exact)
    if score is None:
        return
    score += _surface_bonus(text, word)
    current = best.get(word)
    if current is None or score > current[0] or (score == current[0] and len(text) < len(current[1])):
        best[word] = (score, text)


def _score(text: str, exact: bool) -> int | None:
    if not text or _CJK.search(text):
        return None
    if any(mark in text for mark in "{}[]<>\\"):
        return None
    folded = text.casefold()
    if "http" in folded or "www." in folded:
        return None
    words = text.split()
    count = len(words)
    if count < 5 or count > 22 or len(text) > 140:
        return None
    letters = sum(char.isalpha() for char in text)
    if letters < len(text) * 0.65:
        return None
    if text.isupper():
        return None
    score = 200 if exact else 40
    score -= abs(count - 10) * 6
    if text[-1] in ".!?":
        score += 25
    if text[0].isupper():
        score += 10
    return score


def _surface_bonus(text: str, word: str) -> int:
    """Prefer a normal use over a capitalized name such as Bill or August."""
    if " " in word or not word.islower():
        return 0
    lowers = 0
    capitals = 0
    for token in _TOKEN.findall(text):
        if token.casefold() != word:
            continue
        if token.islower():
            lowers += 1
        else:
            capitals += 1
    if lowers:
        return 80
    if capitals:
        return -180
    return 0


def _surface_forms(word: str) -> list[str]:
    forms = [word]
    if "-" in word:
        forms.append(word.replace("-", " "))
        forms.append(word.replace("-", ""))
    return forms


def _contains(text: str, word: str) -> bool | None:
    folded = word.casefold()
    if " " in folded or "-" in folded:
        haystack = text.casefold()
        for form in _surface_forms(folded):
            if re.search(rf"(?<![A-Za-z]){re.escape(form)}(?![A-Za-z])", haystack):
                return True
        return None
    for token in _TOKEN.findall(text):
        token_folded = token.casefold()
        if token_folded == folded:
            return True
        if folded in _stems(token_folded):
            return False
    return None


def _pieces(text: str) -> list[str]:
    cleaned = " ".join(text.replace("<b>", "").replace("</b>", "").split())
    parts = [part.strip() for part in _SPLIT.split(cleaned) if part.strip()]
    return parts or ([cleaned] if cleaned else [])


def _lemmas(token: str, wanted: set[str]) -> list[tuple[str, bool]]:
    hits: list[tuple[str, bool]] = []
    if token in wanted:
        hits.append((token, True))
    for stem in _stems(token):
        if stem in wanted and stem != token:
            hits.append((stem, False))
    return hits


def _stems(token: str) -> list[str]:
    if len(token) < 5:
        return []
    stems: list[str] = []
    if token.endswith("ies"):
        stems.append(token[:-3] + "y")
    if token.endswith("ing") and len(token) > 5:
        stem = token[:-3]
        stems.append(stem)
        stems.append(stem + "e")
        if len(stem) > 2 and stem[-1] == stem[-2]:
            stems.append(stem[:-1])
    if token.endswith("ied"):
        stems.append(token[:-3] + "y")
    if token.endswith("ed") and len(token) > 4:
        stem = token[:-2]
        stems.append(stem)
        stems.append(stem + "e")
        if len(stem) > 2 and stem[-1] == stem[-2]:
            stems.append(stem[:-1])
    if token.endswith("es") and len(token) > 4:
        stems.append(token[:-2])
    if token.endswith("s") and not token.endswith("ss") and len(token) > 4:
        stems.append(token[:-1])
    return stems


def _load_cache(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _save_cache(path: Path, cache: dict[str, str]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _download_dump(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".bz2.part")
    request = urllib.request.Request(TATOEBA_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as handle:
        while True:
            chunk = response.read(1 << 16)
            if not chunk:
                break
            handle.write(chunk)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill vocab JSON with real example sentences.")
    parser.add_argument("json_path", type=Path, nargs="?", default=DEFAULT_JSON)
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args(argv)
    if not args.json_path.is_file():
        print(f"JSON not found: {args.json_path}", file=sys.stderr)
        return 1
    if not args.dump.is_file():
        print(f"downloading Tatoeba sentences to {args.dump}", file=sys.stderr)
        _download_dump(args.dump)
    filled, tatoeba_hits, youdao_hits = fill_file(args.json_path, args.dump, args.cache)
    total = json.loads(args.json_path.read_text(encoding="utf-8"))
    print(
        f"wrote {filled} examples of {len(total)} entries "
        f"({tatoeba_hits} from Tatoeba, {youdao_hits} from Youdao)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
