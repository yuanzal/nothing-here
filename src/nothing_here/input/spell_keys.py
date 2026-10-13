"""拼写用的字母键监听。桌面嵌入的卡片拿不到焦点，所以用 pynput，不抢 Qt 窗口焦点。"""

from __future__ import annotations

from pynput import keyboard
from PyQt6.QtCore import QObject, pyqtSignal


class SpellKeyHook(QObject):
    """运行期间把 a–z 和退格送到 Qt 主线程。"""

    letter = pyqtSignal(str)
    backspace = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener: keyboard.Listener | None = None

    @property
    def active(self) -> bool:
        return self._listener is not None

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.start()

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.stop()

    def _on_press(self, key: object) -> None:
        if key == keyboard.Key.backspace:
            self.backspace.emit()
            return
        char = getattr(key, "char", None)
        if isinstance(char, str) and len(char) == 1 and char.isalpha():
            self.letter.emit(char)
