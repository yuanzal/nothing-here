from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton

from nothing_here.ui.read_window import ReadWindow

_APP = QApplication.instance() or QApplication([])


class ReadNavTests(unittest.TestCase):
    def test_nav_order_is_chapter_page_page_chapter(self) -> None:
        card = ReadWindow()
        nav = card._nav.layout()
        labels = [nav.itemAt(index).widget().text() for index in range(nav.count())]
        self.assertEqual(labels, ["<<", "<", ">", ">>"])
        for index in range(nav.count()):
            self.assertIsInstance(nav.itemAt(index).widget(), QPushButton)
        card.close()
        card.deleteLater()
