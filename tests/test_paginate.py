from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from nothing_here.domain.read import chapter_starts, page_of
from nothing_here.ui.paginate import page_starts

_APP = QApplication.instance() or QApplication([])


class PageStartTests(unittest.TestCase):
    def test_chapter_heading_starts_a_new_page(self) -> None:
        text = "第一行\n第二行\n第一章 标题\n第三行\n第四行\n第五行"
        heading = chapter_starts(text)[0]
        self.assertEqual(heading, text.index("第一章"))
        starts = page_starts(text, width=400, height=96, pixel_size=16, line_ratio=1.5)
        self.assertIn(heading, starts)
        self.assertEqual(starts[page_of(starts, heading)], heading)
