from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from nothing_here.ui.card_window import ROSE_SVG, CardWindow, Face

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

    def test_dragging_layer_button_does_not_recurse(self) -> None:
        card = CardWindow()
        drags: list[object] = []
        card.moved.connect(lambda x, y: drags.append((x, y)))
        _show(card)
        start = card._layer.mapTo(card._body, card._layer.rect().center())
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(start),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.assertTrue(QApplication.sendEvent(card._body, move))
        card.close()
        self.assertEqual(drags, [])

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

    def test_back_shows_example_and_rose_without_a_blank_line(self) -> None:
        card = CardWindow()
        card.resize(300, 280)
        card.show()
        card.set_content("word", "wɜːd", "词", 1, 2, Face.FRONT, "A short example.")
        self.assertFalse(card._example.isVisible())
        self.assertFalse(card._button_row.isVisible())
        card.set_content("word", "wɜːd", "词", 1, 2, Face.BACK, "A short example.")
        self.assertTrue(card._example.isVisible())
        self.assertEqual(card._example.text(), "A short example.")
        self.assertTrue(card._rose.isVisible())
        self.assertEqual(card._rose.text(), "")
        self.assertEqual(card._rose.toolTip(), "斩杀")
        self.assertTrue(ROSE_SVG.is_file(), str(ROSE_SVG))
        image = card._rose.icon().pixmap(22, 22).toImage()
        self.assertFalse(image.isNull())
        self.assertTrue(
            any(
                image.pixelColor(x, y).alpha() > 0
                for y in range(image.height())
                for x in range(image.width())
            )
        )
        card.set_content("word", "", "词", 1, 2, Face.BACK, "   ")
        self.assertFalse(card._example.isVisible())
        self.assertFalse(card._phonetic.isVisible())
        card.close()

    def test_finished_card_shows_only_the_fixed_line(self) -> None:
        card = CardWindow()
        card.resize(300, 180)
        card.show()
        card.show_finished()
        self.assertTrue(card._done.isVisible())
        self.assertEqual(card._done.text(), "厉害啦，没有更多单词了")
        self.assertFalse(card._word.isVisible())
        self.assertFalse(card._stats.isVisible())
        self.assertFalse(card._reveal.isVisible())
        self.assertFalse(card._translation.isVisible())
        self.assertFalse(card._example.isVisible())
        self.assertFalse(card._button_row.isVisible())
        self.assertTrue(card._layer.isVisible())
        card.close()

    def test_burn_fades_and_blocks_buttons(self) -> None:
        card = CardWindow()
        card.resize(300, 220)
        card.show()
        card.set_content("word", "", "词", 0, 0, Face.BACK, "")
        seen: list[float] = []
        card.burn_finished.connect(lambda: seen.append(card._fade))
        card.play_burn()
        self.assertFalse(card._known.isEnabled())
        self.assertFalse(card._rose.isEnabled())
        for _ in range(40):
            QTest.qWait(20)
            if seen:
                break
        self.assertEqual(seen, [0.0])
        card.finish_burn()
        self.assertEqual(card._fade, 1.0)
        self.assertEqual(card._sink, 0)
        self.assertTrue(card._known.isEnabled())
        card.close()


if __name__ == "__main__":
    unittest.main()
