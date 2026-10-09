from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(frozen=True)
class Entry:
    word: str
    phonetic: str
    translation: str


class VocabSource(Protocol):
    source_id: str
    display_name: str

    def iter_entries(self) -> Iterable[Entry]:
        ...
