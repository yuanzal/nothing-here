from __future__ import annotations

from nothing_here.paths import data_file

from .json_source import JsonVocabSource
from .protocol import Entry, VocabSource

def load_sources() -> list[VocabSource]:
    return [
        JsonVocabSource("ielts", "雅思", data_file("ielts.json"), "英语"),
        JsonVocabSource("cet4", "四级", data_file("cet4.json"), "英语"),
        JsonVocabSource("cet6", "六级", data_file("cet6.json"), "英语"),
        JsonVocabSource("ky", "考研", data_file("ky.json"), "英语"),
        JsonVocabSource("jp_n5", "N5", data_file("jp_n5.json"), "日语"),
        JsonVocabSource("jp_n4", "N4", data_file("jp_n4.json"), "日语"),
        JsonVocabSource("jp_n3", "N3", data_file("jp_n3.json"), "日语"),
        JsonVocabSource("jp_n2", "N2", data_file("jp_n2.json"), "日语"),
        JsonVocabSource("jp_n1", "N1", data_file("jp_n1.json"), "日语"),
    ]


def catalog_from(source: VocabSource) -> dict[str, Entry]:
    catalog: dict[str, Entry] = {}
    for entry in source.iter_entries():
        key = entry.word.casefold()
        if key not in catalog:
            catalog[key] = entry
    return catalog
