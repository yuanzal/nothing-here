from __future__ import annotations

from collections.abc import Callable

from pynput import keyboard

DEFAULT_HIDE_HOTKEY = "ctrl+alt+s"

_MOD_ORDER = ("ctrl", "alt", "shift", "win")
_MOD_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
    "win": "win",
    "windows": "win",
    "cmd": "win",
    "super": "win",
    "meta": "win",
}
_DISPLAY_MOD = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}
_QT_MOD = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Meta"}
_PYNPUT_MOD = {"ctrl": "<ctrl>", "alt": "<alt>", "shift": "<shift>", "win": "<cmd>"}


def parse_hotkey(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parts = [part.strip() for part in text.replace("-", "+").split("+") if part.strip()]
    mods: list[str] = []
    keys: list[str] = []
    for part in parts:
        name = part.lower().strip("<>")
        if name in _MOD_ALIASES:
            canonical = _MOD_ALIASES[name]
            if canonical not in mods:
                mods.append(canonical)
            continue
        key = _key_token(name)
        if key is None:
            return None
        keys.append(key)
    if len(keys) != 1 or not mods:
        return None
    ordered = [mod for mod in _MOD_ORDER if mod in mods]
    return "+".join((*ordered, keys[0]))


def display_hotkey(value: object) -> str:
    return _join_hotkey(value, _DISPLAY_MOD)


def qt_hotkey(value: object) -> str:
    return _join_hotkey(value, _QT_MOD)


def pynput_hotkey(value: object) -> str:
    combo = parse_hotkey(value) or DEFAULT_HIDE_HOTKEY
    parts: list[str] = []
    for token in combo.split("+"):
        mapped = _PYNPUT_MOD.get(token)
        if mapped is not None:
            parts.append(mapped)
        elif token.startswith("f") and token[1:].isdigit():
            parts.append(f"<{token}>")
        else:
            parts.append(token)
    return "+".join(parts)


class HotkeyListener:
    def __init__(
        self,
        on_visibility: Callable[[], None],
        combo: str = DEFAULT_HIDE_HOTKEY,
    ) -> None:
        self._on_visibility = on_visibility
        self._combo = parse_hotkey(combo) or DEFAULT_HIDE_HOTKEY
        self._hotkeys: keyboard.GlobalHotKeys | None = None

    def set_combo(self, combo: str) -> None:
        self._combo = parse_hotkey(combo) or DEFAULT_HIDE_HOTKEY

    def start(self) -> None:
        self.stop()
        self._hotkeys = keyboard.GlobalHotKeys(
            {pynput_hotkey(self._combo): self._on_visibility}
        )
        self._hotkeys.start()

    def stop(self) -> None:
        if self._hotkeys is None:
            return
        self._hotkeys.stop()
        self._hotkeys = None


def _key_token(raw: str) -> str | None:
    if len(raw) == 1 and raw.isalnum():
        return raw
    if raw.startswith("f") and raw[1:].isdigit():
        number = int(raw[1:])
        if 1 <= number <= 12:
            return f"f{number}"
    return None


def _join_hotkey(value: object, labels: dict[str, str]) -> str:
    combo = parse_hotkey(value) or DEFAULT_HIDE_HOTKEY
    shown: list[str] = []
    for token in combo.split("+"):
        shown.append(labels.get(token, token.upper()))
    return "+".join(shown)
