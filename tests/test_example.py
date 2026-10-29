from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nothing_here.vocab.examples import (
    EntryExampleSource,
    load_example_sources,
    resolve_example,
)
from nothing_here.vocab.json_source import JsonVocabSource


class _Later:
    source_id = "later"

    def __init__(self, sentence: str) -> None:
        self._sentence = sentence

    def example_for(self, word: str) -> str:
        del word
        return self._sentence


class ExampleTests(unittest.TestCase):
    def test_blank_field_resolves_to_blank(self) -> None:
        sources = load_example_sources()
        self.assertEqual([source.source_id for source in sources], ["entry"])
        sources[0].use_examples({"quiet": ""})  # type: ignore[attr-defined]
        self.assertEqual(resolve_example(sources, "quiet"), "")

    def test_entry_sentence_is_used(self) -> None:
        sources = [
            EntryExampleSource({"quiet": "Keep the room quiet."}),
            _Later("The room is loud."),
        ]
        self.assertEqual(resolve_example(sources, "quiet"), "Keep the room quiet.")

    def test_later_source_fills_a_blank_entry(self) -> None:
        sources = [
            EntryExampleSource({"quiet": ""}),
            _Later("Stay quiet in the hall."),
        ]
        self.assertEqual(resolve_example(sources, "quiet"), "Stay quiet in the hall.")

    def test_json_example_defaults_to_blank_and_keeps_a_sentence(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "vocab.json"
            path.write_text(
                json.dumps(
                    [
                        {"word": "alpha", "phonetic": "", "translation": "甲"},
                        {
                            "word": "beta",
                            "phonetic": "",
                            "translation": "乙",
                            "example": "Beta comes next.",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            source = JsonVocabSource("sample", "样例", path, "英语")
            entries = {entry.word: entry for entry in source.iter_entries()}
            self.assertEqual(entries["alpha"].example, "")
            self.assertEqual(entries["beta"].example, "Beta comes next.")
