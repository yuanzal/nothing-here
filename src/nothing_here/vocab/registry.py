from __future__ import annotations

from nothing_here.paths import data_file

from .json_source import JsonVocabSource
from .protocol import Entry, VocabSource

def load_sources() -> list[VocabSource]:
    return [
        JsonVocabSource("ielts", "雅思", data_file("ielts.json")),
        JsonVocabSource("cet4", "四级", data_file("cet4.json")),
        JsonVocabSource("cet6", "六级", data_file("cet6.json")),
        JsonVocabSource("ky", "考研", data_file("ky.json")),
    ]


def catalog_from(source: VocabSource) -> dict[str, Entry]:
    catalog: dict[str, Entry] = {}
    for entry in source.iter_entries():
        key = entry.word.casefold()
        if key not in catalog:
            catalog[key] = entry
    return catalog
