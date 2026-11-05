"""录全部隐藏的组合键。必须带 Ctrl / Alt / Shift / Win。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QKeySequenceEdit,
    QVBoxLayout,
)

from nothing_here.input.hotkey import DEFAULT_HIDE_HOTKEY, parse_hotkey, qt_hotkey

_MODS = (
    (Qt.KeyboardModifier.ControlModifier, "ctrl"),
    (Qt.KeyboardModifier.AltModifier, "alt"),
    (Qt.KeyboardModifier.ShiftModifier, "shift"),
    (Qt.KeyboardModifier.MetaModifier, "win"),
)
_KEYS: dict[Qt.Key, str] = {
    getattr(Qt.Key, f"Key_{letter}"): letter.lower() for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
}
_KEYS.update({getattr(Qt.Key, f"Key_{digit}"): str(digit) for digit in range(10)})
_KEYS.update({getattr(Qt.Key, f"Key_F{index}"): f"f{index}" for index in range(1, 13)})


def combo_from_sequence(sequence: QKeySequence) -> str | None:
    if sequence.count() < 1:
        return None
    combination = sequence[0]
    token = _KEYS.get(combination.key())
    if token is None:
        return None
    mods = [
        name
        for flag, name in _MODS
        if combination.keyboardModifiers() & flag
    ]
    if not mods:
        return None
    return parse_hotkey("+".join((*mods, token)))


class HotkeyDialog(QDialog):
    def __init__(self, current: str) -> None:
        super().__init__()
        self.setWindowTitle("热键设置")
        self._combo = parse_hotkey(current) or DEFAULT_HIDE_HOTKEY
        self._edit = QKeySequenceEdit()
        self._edit.setMaximumSequenceLength(1)
        self._edit.setKeySequence(QKeySequence(qt_hotkey(self._combo)))
        self._hint = QLabel("点输入框后按下组合键。必须带 Ctrl、Alt、Shift 或 Win。")
        self._hint.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        reset = buttons.addButton("恢复默认", QDialogButtonBox.ButtonRole.ResetRole)
        reset.clicked.connect(self._restore)
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self._edit)
        layout.addWidget(self._hint)
        layout.addWidget(buttons)

    def combo(self) -> str:
        return self._combo

    def _restore(self) -> None:
        self._edit.setKeySequence(QKeySequence(qt_hotkey(DEFAULT_HIDE_HOTKEY)))

    def _try_accept(self) -> None:
        combo = combo_from_sequence(self._edit.keySequence())
        if combo is None:
            self._hint.setText("请使用带 Ctrl / Alt / Shift / Win 的组合键，例如 Ctrl+Alt+S。")
            return
        self._combo = combo
        self.accept()
