from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .protocol import Entry


class JsonVocabSource:
    def __init__(self, source_id: str, display_name: str, path: Path, family: str) -> None:
        self.source_id = source_id
        self.display_name = display_name
        self.family = family
        self._path = path
        self._entries: list[Entry] | None = None

    def iter_entries(self) -> Iterable[Entry]:
        if self._entries is None:
            self._entries = self._load()
        return iter(self._entries)

    def _load(self) -> list[Entry]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        entries: list[Entry] = []
        for item in raw:
            word = str(item.get("word") or "").strip()
            if not word:
                continue
            entries.append(
                Entry(
                    word=word,
                    phonetic=str(item.get("phonetic") or ""),
                    translation=str(item.get("translation") or "").replace("\\n", "\n"),
                    example=str(item.get("example") or "").strip(),
                )
            )
        return entries
