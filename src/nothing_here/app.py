from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from nothing_here.desktop.host import DesktopHost
from nothing_here.domain.sample import WeightedWord, pick_one
from nothing_here.domain.weight import weight
from nothing_here.input.hotkey import HotkeyListener
from nothing_here.storage.db import AppState, Store
from nothing_here.ui.card_window import CardWindow, Face
from nothing_here.ui.tray import Tray
from nothing_here.vocab.protocol import VocabSource
from nothing_here.vocab.registry import catalog_from, load_sources

INSTANCE_NAME = "nothing-here"
SLOT_COUNT = 3
MIN_FRONT_HEIGHT = 96


class ViewState(Enum):
    HIDDEN = "hidden"
    PASSTHROUGH = "passthrough"
    REVEALED = "revealed"


@dataclass
class Slot:
    key: str
    face: Face


class App(QObject):
    hotkey_pressed = pyqtSignal()
    visibility_hotkey_pressed = pyqtSignal()

    def __init__(self, qt_app: QApplication) -> None:
        super().__init__()
        self._qt_app = qt_app
        self._store = Store()
        self._sources = load_sources()
        self._source_by_id = {source.source_id: source for source in self._sources}
        persisted = self._store.load_state()
        self._active_id = _pick_source(self._sources, persisted.active_source)
        self._catalog = catalog_from(self._source_by_id[self._active_id])
        self._progress = self._store.all_progress()
        self._slots = self._resolve_slots(persisted.slots)
        self._origins: list[Optional[tuple[int, int]]] = list(persisted.origins)
        self._floating = persisted.floating
        self._hidden = persisted.hidden
        self._view = ViewState.HIDDEN
        self._cards: list[CardWindow] = []
        self._host = DesktopHost()
        self._host.floating = self._floating
        self._embed_notified = False
        self._tray = Tray(self._sources, self._active_id, self._floating)
        self._tray.show_cards.connect(self.show_cards)
        self._tray.hide_cards.connect(self.hide_cards)
        self._tray.source_chosen.connect(self.switch_source)
        self._tray.layer_chosen.connect(self.set_floating)
        self._tray.quit_requested.connect(self.quit)
        self.hotkey_pressed.connect(self.toggle_hotkey)
        self.visibility_hotkey_pressed.connect(self.toggle_visibility)
        self._hotkey = HotkeyListener(self.hotkey_pressed.emit, self.visibility_hotkey_pressed.emit)
        self._hotkey.start()
        qt_app.aboutToQuit.connect(self._teardown)

    def start(self) -> None:
        if not self._hidden:
            self.show_cards()

    def show_cards(self) -> None:
        if self._view is not ViewState.HIDDEN:
            return
        self._hidden = False
        self._slots = self._resolve_slots(self._slot_keys())
        if not self._floating and not self._host.available:
            self._notify_embed_failed()
            self._persist()
            return
        if not self._open_cards(passthrough=True):
            self._notify_embed_failed()
            self._persist()
            return
        self._view = ViewState.PASSTHROUGH
        self._persist()

    def hide_cards(self) -> None:
        if self._view is ViewState.HIDDEN:
            return
        self._destroy_windows()
        self._view = ViewState.HIDDEN
        self._hidden = True
        self._persist()

    def set_floating(self, floating: bool) -> None:
        if floating == self._floating:
            self._sync_layer_controls()
            return
        if not floating and not self._host.available:
            self._notify_embed_failed()
            self._sync_layer_controls()
            return
        previous = self._floating
        self._floating = floating
        if self._view is not ViewState.HIDDEN:
            passthrough = self._view is not ViewState.REVEALED
            if not self._open_cards(passthrough=passthrough):
                self._floating = previous
                self._open_cards(passthrough=passthrough)
                self._notify_embed_failed()
                self._sync_layer_controls()
                return
        self._sync_layer_controls()
        self._persist()

    def toggle_visibility(self) -> None:
        if self._view is ViewState.HIDDEN:
            self.show_cards()
            return
        self.hide_cards()

    def toggle_hotkey(self) -> None:
        if self._view is ViewState.HIDDEN:
            return
        if self._view is ViewState.PASSTHROUGH:
            for slot in self._slots:
                slot.face = Face.BACK
            self._view = ViewState.REVEALED
            self._render(passthrough=False)
            return
        for slot in self._slots:
            slot.face = Face.FRONT
        self._view = ViewState.PASSTHROUGH
        self._render(passthrough=True)

    def switch_source(self, source_id: str) -> None:
        if source_id not in self._source_by_id:
            return
        visible = self._view is not ViewState.HIDDEN
        self._active_id = source_id
        self._catalog = catalog_from(self._source_by_id[source_id])
        self._slots = self._resolve_slots(self._slot_keys())
        self._tray.set_active_source(source_id)
        if visible:
            self._destroy_windows()
            self._view = ViewState.HIDDEN
            needs_desktop = not self._floating and not self._host.available
            if needs_desktop or not self._open_cards(passthrough=True):
                self._notify_embed_failed()
            else:
                self._view = ViewState.PASSTHROUGH
        self._persist()

    def quit(self) -> None:
        self._persist()
        self._qt_app.quit()

    def _grade(self, index: int, known: bool) -> None:
        if self._view is not ViewState.REVEALED:
            return
        if index >= len(self._slots):
            return
        slot = self._slots[index]
        if slot.face is not Face.BACK:
            return
        correct, reviews = self._store.record(slot.key, known)
        self._progress[slot.key] = (correct, reviews)
        picked = pick_one(self._weighted(), [item.key for item in self._slots])
        if picked is None:
            slot.face = Face.FRONT
        else:
            self._slots[index] = Slot(picked, Face.FRONT)
        self._render(passthrough=False)
        self._persist()

    def _open_cards(self, passthrough: bool) -> bool:
        self._destroy_windows()
        if not self._slots:
            return True
        cards: list[CardWindow] = []
        for index, _slot in enumerate(self._slots):
            card = CardWindow()
            card.recognized.connect(lambda i=index: self._grade(i, True))
            card.unknown.connect(lambda i=index: self._grade(i, False))
            card.moved.connect(lambda x, y, i=index: self._move_card(i, x, y, persist=False))
            card.move_finished.connect(lambda x, y, i=index: self._move_card(i, x, y, persist=True))
            card.layer_requested.connect(lambda: self.set_floating(not self._floating))
            card.set_layer_floating(self._floating)
            card.apply_layer(self._floating)
            card.winId()
            if not self._host.prepare(card, self._floating):
                card.close()
                for existing in cards:
                    existing.close()
                    existing.deleteLater()
                return False
            card.show()
            cards.append(card)
        self._cards = cards
        self._render(passthrough=passthrough)
        return True

    def _render(self, passthrough: bool) -> None:
        if len(self._cards) != len(self._slots):
            if not self._open_cards(passthrough):
                self._notify_embed_failed()
                self._view = ViewState.HIDDEN
            return
        for card, slot in zip(self._cards, self._slots):
            entry = self._catalog[slot.key]
            correct, reviews = self._progress.get(slot.key, (0, 0))
            card.set_content(
                entry.word,
                entry.phonetic,
                entry.translation,
                correct,
                reviews,
                slot.face,
            )
            self._host.set_click_through(card, passthrough)
        if self._cards:
            self._host.place(self._cards, MIN_FRONT_HEIGHT, self._origins)

    def _resolve_slots(self, saved: tuple[Optional[str], ...]) -> list[Slot]:
        kept: list[str] = []
        for key in saved:
            if key and key in self._catalog and key not in kept:
                kept.append(key)
            if len(kept) == SLOT_COUNT:
                break
        target = min(SLOT_COUNT, len(self._catalog))
        while len(kept) < target:
            picked = pick_one(self._weighted(), kept)
            if picked is None:
                break
            kept.append(picked)
        return [Slot(key, Face.FRONT) for key in kept]

    def _weighted(self) -> list[WeightedWord]:
        return [
            WeightedWord(key, weight(*self._progress.get(key, (0, 0))))
            for key in self._catalog
        ]

    def _move_card(self, index: int, x: int, y: int, persist: bool) -> None:
        if index >= len(self._cards):
            return
        origin = self._host.move(self._cards[index], x, y)
        while len(self._origins) <= index:
            self._origins.append(None)
        self._origins[index] = origin
        if persist:
            self._persist()

    def _slot_keys(self) -> tuple[Optional[str], Optional[str], Optional[str]]:
        keys: list[Optional[str]] = [slot.key for slot in self._slots]
        while len(keys) < SLOT_COUNT:
            keys.append(None)
        return keys[0], keys[1], keys[2]

    def _origin_keys(
        self,
    ) -> tuple[Optional[tuple[int, int]], Optional[tuple[int, int]], Optional[tuple[int, int]]]:
        origins: list[Optional[tuple[int, int]]] = list(self._origins)
        while len(origins) < SLOT_COUNT:
            origins.append(None)
        return origins[0], origins[1], origins[2]

    def _persist(self) -> None:
        self._store.save_state(
            AppState(
                hidden=self._hidden,
                active_source=self._active_id,
                slots=self._slot_keys(),
                origins=self._origin_keys(),
                floating=self._floating,
            )
        )

    def _destroy_windows(self) -> None:
        for card in self._cards:
            card.hide()
            card.close()
            card.deleteLater()
        self._cards = []

    def _sync_layer_controls(self) -> None:
        self._tray.set_floating(self._floating)
        for card in self._cards:
            card.set_layer_floating(self._floating)

    def _notify_embed_failed(self) -> None:
        if not self._embed_notified:
            self._tray.show_embed_failed()
            self._embed_notified = True

    def _teardown(self) -> None:
        self._persist()
        self._hotkey.stop()
        self._destroy_windows()
        self._store.close()


def _pick_source(sources: list[VocabSource], wanted: str) -> str:
    ids = {source.source_id for source in sources}
    if wanted in ids:
        return wanted
    return sources[0].source_id


def _set_app_id() -> None:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NothingHere")


def acquire_instance() -> Optional[QLocalServer]:
    probe = QLocalSocket()
    probe.connectToServer(INSTANCE_NAME)
    if probe.waitForConnected(150):
        probe.disconnectFromServer()
        return None
    QLocalServer.removeServer(INSTANCE_NAME)
    server = QLocalServer()
    if not server.listen(INSTANCE_NAME):
        return None
    return server


def main() -> int:
    _set_app_id()
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Nothing Here")
    qt_app.setQuitOnLastWindowClosed(False)
    server = acquire_instance()
    if server is None:
        return 0
    app = App(qt_app)
    app._server = server  # noqa: SLF001 — keep the named pipe alive
    app.start()
    return qt_app.exec()
