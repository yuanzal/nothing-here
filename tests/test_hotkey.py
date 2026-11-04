from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nothing_here.input.hotkey import (
    DEFAULT_HIDE_HOTKEY,
    display_hotkey,
    parse_hotkey,
    pynput_hotkey,
    qt_hotkey,
)
from nothing_here.storage.db import AppState, Store


class ParseHotkeyTests(unittest.TestCase):
    def test_default_is_ctrl_alt_s(self) -> None:
        self.assertEqual(parse_hotkey("Ctrl+Alt+S"), "ctrl+alt+s")
        self.assertEqual(DEFAULT_HIDE_HOTKEY, "ctrl+alt+s")
        self.assertEqual(display_hotkey("ctrl+alt+s"), "Ctrl+Alt+S")
        self.assertEqual(pynput_hotkey("ctrl+alt+s"), "<ctrl>+<alt>+s")
        self.assertEqual(qt_hotkey("ctrl+alt+s"), "Ctrl+Alt+S")

    def test_accepts_aliases_and_function_keys(self) -> None:
        self.assertEqual(parse_hotkey("<ctrl>+<shift>+h"), "ctrl+shift+h")
        self.assertEqual(parse_hotkey("Win-F12"), "win+f12")
        self.assertEqual(pynput_hotkey("win+f12"), "<cmd>+<f12>")
        self.assertEqual(qt_hotkey("win+s"), "Meta+S")

    def test_rejects_bare_keys_and_unknown_tokens(self) -> None:
        self.assertIsNone(parse_hotkey("s"))
        self.assertIsNone(parse_hotkey("ctrl"))
        self.assertIsNone(parse_hotkey("ctrl+alt"))
        self.assertIsNone(parse_hotkey("ctrl+space"))
        self.assertIsNone(parse_hotkey(""))


class HideHotkeyStoreTests(unittest.TestCase):
    def test_round_trip_and_invalid_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "study.db"
            store = Store(path)
            store.save_state(
                AppState(
                    hidden=False,
                    active_source="ielts",
                    word=None,
                    hide_hotkey="ctrl+shift+h",
                )
            )
            store.close()
            again = Store(path)
            self.assertEqual(again.load_state().hide_hotkey, "ctrl+shift+h")
            again.save_state(
                AppState(hidden=False, active_source="ielts", word=None, hide_hotkey="s")
            )
            self.assertEqual(again.load_state().hide_hotkey, DEFAULT_HIDE_HOTKEY)
            again.close()


class SequenceHotkeyTests(unittest.TestCase):
    def test_qt_sequence_maps_to_canonical_combo(self) -> None:
        from PyQt6.QtGui import QKeySequence

        from nothing_here.ui.hotkey_dialog import combo_from_sequence

        self.assertEqual(combo_from_sequence(QKeySequence("Ctrl+Shift+H")), "ctrl+shift+h")
        self.assertIsNone(combo_from_sequence(QKeySequence("S")))
        self.assertIsNone(combo_from_sequence(QKeySequence()))
