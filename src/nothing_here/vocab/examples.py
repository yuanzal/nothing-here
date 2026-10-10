from __future__ import annotations

from typing import Mapping, Protocol, Sequence


class ExampleSource(Protocol):
    source_id: str

    def example_for(self, word: str) -> str:
        ...


class EntryExampleSource:
    """例句来自当前词条上的 example 字段。"""

    source_id = "entry"

    def __init__(self, examples: Mapping[str, str] | None = None) -> None:
        self._examples: dict[str, str] = {}
        if examples:
            self.use_examples(examples)

    def use_examples(self, examples: Mapping[str, str]) -> None:
        self._examples = {key.casefold(): value for key, value in examples.items()}

    def example_for(self, word: str) -> str:
        return self._examples.get(word.casefold(), "")


def load_example_sources() -> list[ExampleSource]:
    return [EntryExampleSource()]


def resolve_example(sources: Sequence[ExampleSource], word: str) -> str:
    for source in sources:
        text = source.example_for(word).strip()
        if text:
            return text
    return ""
