from __future__ import annotations

import unittest
from pathlib import Path

from nothing_here.paths import data_file
from nothing_here.vocab.registry import catalog_from, load_sources


class JapaneseVocabTests(unittest.TestCase):
    def test_japanese_levels_are_separate_sources_under_one_family(self) -> None:
        sources = load_sources()
        english = [item for item in sources if item.family == "英语"]
        japanese = [item for item in sources if item.family == "日语"]
        self.assertEqual([item.display_name for item in english], ["雅思", "四级", "六级", "考研"])
        self.assertEqual([item.source_id for item in japanese], [
            "jp_n5",
            "jp_n4",
            "jp_n3",
            "jp_n2",
            "jp_n1",
        ])
        n5 = next(item for item in japanese if item.source_id == "jp_n5")
        self.assertTrue(Path(data_file("jp_n5.json")).is_file())
        catalog = catalog_from(n5)
        self.assertGreater(len(catalog), 100)
        self.assertEqual(catalog["会う"].phonetic, "あう")
        self.assertIn("见面", catalog["会う"].translation)
        self.assertFalse(catalog["会う"].translation.startswith("to "))
        n3 = next(item for item in japanese if item.source_id == "jp_n3")
        self.assertGreater(len(catalog_from(n3)), 100)


if __name__ == "__main__":
    unittest.main()
