from __future__ import annotations

from pathlib import Path

from .json_source import JsonVocabSource
from .protocol import Entry, VocabSource

REPO_ROOT = Path(__file__).resolve().parents[3]
IELTS_JSON = REPO_ROOT / "data" / "ielts.json"


def load_sources() -> list[VocabSource]:
    return [
        JsonVocabSource("ielts", "雅思", IELTS_JSON),
    ]


def catalog_from(source: VocabSource) -> dict[str, Entry]:
    catalog: dict[str, Entry] = {}
    for entry in source.iter_entries():
        key = entry.word.casefold()
        if key not in catalog:
            catalog[key] = entry
    return catalog
