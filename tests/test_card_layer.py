from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from nothing_here.ui.card_window import CardWindow, Face

_APP = QApplication.instance() or QApplication(sys.argv)


def _show(card: CardWindow) -> None:
    card.set_content("word", "wɜːd", "词", 0, 0, Face.FRONT)
    card.resize(300, 200)
    card.show()
    QTest.qWaitForWindowExposed(card)
    card._position_body()


class CardLayerTests(unittest.TestCase):
    def test_layer_button_click_does_not_drag(self) -> None:
        card = CardWindow()
        hits: list[str] = []
        drags: list[object] = []
        card.layer_requested.connect(lambda: hits.append("layer"))
        card.moved.connect(lambda x, y: drags.append((x, y)))
        card.move_finished.connect(lambda x, y: drags.append(("end", x, y)))
        _show(card)
        QTest.mouseClick(card._layer, Qt.MouseButton.LeftButton)
        card.close()
        self.assertEqual(hits, ["layer"], hits)
        self.assertEqual(drags, [], drags)

    def test_clicking_layer_through_card_does_not_drag(self) -> None:
        card = CardWindow()
        hits: list[str] = []
        drags: list[object] = []
        card.layer_requested.connect(lambda: hits.append("layer"))
        card.moved.connect(lambda x, y: drags.append((x, y)))
        card.move_finished.connect(lambda x, y: drags.append(("end", x, y)))
        _show(card)
        center = card._layer.mapTo(card._body, card._layer.rect().center())
        QTest.mouseClick(card._body, Qt.MouseButton.LeftButton, pos=center)
        card.close()
        self.assertEqual(hits, ["layer"], hits)
        self.assertEqual(drags, [], drags)

    def test_pressing_the_word_still_drags(self) -> None:
        card = CardWindow()
        drags: list[object] = []
        card.moved.connect(lambda x, y: drags.append((x, y)))
        _show(card)
        start = card._word.mapTo(card._body, card._word.rect().center())
        QTest.mousePress(card._body, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(card._body, start + card._word.rect().center())
        QTest.mouseRelease(card._body, Qt.MouseButton.LeftButton, pos=start)
        card.close()
        self.assertTrue(drags)

    def test_layer_label_follows_floating_state(self) -> None:
        card = CardWindow()
        _show(card)
        self.assertEqual(card._layer.text(), "浮在窗口上")
        card.set_layer_floating(True)
        self.assertEqual(card._layer.text(), "回到桌面")
        card.set_layer_floating(False)
        self.assertEqual(card._layer.text(), "浮在窗口上")
        card.close()


if __name__ == "__main__":
    unittest.main()
