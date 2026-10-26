from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton

from nothing_here.ui.read_window import ReadWindow

_APP = QApplication.instance() or QApplication([])


def _show(card: ReadWindow) -> None:
    card.set_box(320, 480)
    card.show()
    QTest.qWaitForWindowExposed(card)
    card.show_page("第一章\n甲\n第二章\n乙", (0, 8), 0, 16, 1.5)


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

    def test_dragging_a_chapter_button_does_not_recurse(self) -> None:
        card = ReadWindow()
        drags: list[object] = []
        card.moved.connect(lambda x, y: drags.append((x, y)))
        _show(card)
        start = card._prev_chapter.mapTo(card._body, card._prev_chapter.rect().center())
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(start),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.assertTrue(QApplication.sendEvent(card._body, move))
        QTest.mousePress(card._body, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(card._body, start + QPoint(24, 12))
        QTest.mouseRelease(card._body, Qt.MouseButton.LeftButton, pos=start + QPoint(24, 12))
        card.close()
        self.assertEqual(drags, [])

    def test_clicking_chapter_button_through_body_still_turns(self) -> None:
        card = ReadWindow()
        turns: list[str] = []
        card.prev_chapter.connect(lambda: turns.append("prev"))
        _show(card)
        center = card._prev_chapter.mapTo(card._body, card._prev_chapter.rect().center())
        QTest.mouseClick(card._body, Qt.MouseButton.LeftButton, pos=center)
        card.close()
        self.assertEqual(turns, ["prev"], turns)
