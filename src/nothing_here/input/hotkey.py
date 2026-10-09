from __future__ import annotations

from collections.abc import Callable

from pynput import keyboard


class HotkeyListener:
    def __init__(self, on_toggle: Callable[[], None]) -> None:
        self._hotkeys = keyboard.GlobalHotKeys({"<ctrl>+<alt>+s": on_toggle})

    def start(self) -> None:
        self._hotkeys.start()

    def stop(self) -> None:
        self._hotkeys.stop()
