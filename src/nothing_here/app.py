from __future__ import annotations

import ctypes
import sys
from datetime import date
from enum import Enum
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from nothing_here.desktop.host import DesktopHost
from nothing_here.domain.daily import DailyPlan, ensure_day, grade, resolve_current, set_goal, switch_catalog
from nothing_here.input.hotkey import HotkeyListener
from nothing_here.storage.db import AppState, DailyRecord, Store
from nothing_here.ui.card_window import CardWindow, Face
from nothing_here.ui.tray import Tray
from nothing_here.vocab.protocol import VocabSource
from nothing_here.vocab.registry import catalog_from, load_sources

INSTANCE_NAME = "nothing-here"
MIN_FRONT_HEIGHT = 96


class ViewState(Enum):
    HIDDEN = "hidden"
    VISIBLE = "visible"


class App(QObject):
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
        self._plan = _plan_from_store(self._store, persisted, _today())
        self._plan = resolve_current(self._plan, list(self._catalog), self._progress)
        self._origin = persisted.origin
        self._floating = persisted.floating
        self._hidden = persisted.hidden
        self._view = ViewState.HIDDEN
        self._face = Face.FRONT
        self._card: Optional[CardWindow] = None
        self._host = DesktopHost()
        self._host.floating = self._floating
        self._embed_notified = False
        self._tray = Tray(
            self._sources,
            self._active_id,
            self._floating,
            self._plan.count,
            self._plan.goal,
        )
        self._tray.show_cards.connect(self.show_cards)
        self._tray.hide_cards.connect(self.hide_cards)
        self._tray.goal_chosen.connect(self.change_goal)
        self._tray.source_chosen.connect(self.switch_source)
        self._tray.layer_chosen.connect(self.set_floating)
        self._tray.quit_requested.connect(self.quit)
        self.visibility_hotkey_pressed.connect(self.toggle_visibility)
        self._hotkey = HotkeyListener(self.visibility_hotkey_pressed.emit)
        self._hotkey.start()
        self._day_timer = QTimer(self)
        self._day_timer.timeout.connect(self._check_day)
        self._day_timer.start(60_000)
        qt_app.aboutToQuit.connect(self._teardown)

    def start(self) -> None:
        if not self._hidden:
            self.show_cards()

    def show_cards(self) -> None:
        if self._view is not ViewState.HIDDEN:
            return
        self._check_day()
        self._hidden = False
        self._plan = resolve_current(self._plan, list(self._catalog), self._progress)
        self._face = Face.FRONT
        if not self._floating and not self._host.available:
            self._notify_embed_failed()
            self._persist()
            return
        if not self._open_card(Face.FRONT):
            self._notify_embed_failed()
            self._persist()
            return
        self._view = ViewState.VISIBLE
        self._persist()

    def hide_cards(self) -> None:
        if self._view is ViewState.HIDDEN:
            return
        self._destroy_windows()
        self._view = ViewState.HIDDEN
        self._hidden = True
        self._face = Face.FRONT
        self._persist()

    def change_goal(self, goal: int) -> None:
        self._check_day()
        previous = self._plan
        self._plan = set_goal(self._plan, goal, list(self._catalog), self._progress)
        if self._plan == previous:
            return
        word_changed = self._plan.current != previous.current
        just_sealed = not previous.sealed and self._plan.sealed
        if word_changed or just_sealed:
            self._face = Face.FRONT
        self._sync_daily_tray()
        if self._view is ViewState.VISIBLE:
            if self._plan.current is None:
                self._destroy_windows()
            elif word_changed or just_sealed or self._card is None:
                if not self._open_card(self._face):
                    self._notify_embed_failed()
                    self._view = ViewState.HIDDEN
            else:
                self._render()
        self._persist()

    def _request_layer_toggle(self) -> None:
        QTimer.singleShot(0, lambda: self.set_floating(not self._floating))

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
        if self._view is ViewState.VISIBLE:
            if not self._open_card(self._face):
                self._floating = previous
                self._open_card(self._face)
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

    def switch_source(self, source_id: str) -> None:
        if source_id not in self._source_by_id:
            return
        self._check_day()
        visible = self._view is ViewState.VISIBLE
        self._active_id = source_id
        self._catalog = catalog_from(self._source_by_id[source_id])
        self._plan = switch_catalog(self._plan, list(self._catalog), self._progress)
        self._face = Face.FRONT
        self._tray.set_active_source(source_id)
        if visible:
            self._destroy_windows()
            self._view = ViewState.HIDDEN
            needs_desktop = not self._floating and not self._host.available
            if self._plan.current is None:
                self._view = ViewState.VISIBLE
            elif needs_desktop or not self._open_card(Face.FRONT):
                self._notify_embed_failed()
            else:
                self._view = ViewState.VISIBLE
        self._persist()

    def quit(self) -> None:
        self._persist()
        self._qt_app.quit()

    def _grade(self, known: bool) -> None:
        self._check_day()
        if self._view is not ViewState.VISIBLE or self._face is not Face.BACK:
            return
        if self._plan.current is None:
            return
        correct, reviews = self._store.record(self._plan.current, known)
        self._progress[self._plan.current] = (correct, reviews)
        self._plan = grade(self._plan, known, list(self._catalog), self._progress)
        self._face = Face.FRONT
        self._sync_daily_tray()
        if self._plan.current is None:
            self._destroy_windows()
        elif self._card is None:
            if not self._open_card(Face.FRONT):
                self._notify_embed_failed()
                self._view = ViewState.HIDDEN
        else:
            self._render()
        self._persist()

    def _toggle_face(self) -> None:
        if self._view is ViewState.HIDDEN or self._card is None:
            return
        self._face = Face.BACK if self._face is Face.FRONT else Face.FRONT
        self._render()

    def _open_card(self, face: Face) -> bool:
        self._destroy_windows()
        self._face = face
        if not self._plan.current or self._plan.current not in self._catalog:
            return True
        card = CardWindow()
        card.recognized.connect(lambda: self._grade(True))
        card.unknown.connect(lambda: self._grade(False))
        card.reveal_toggled.connect(self._toggle_face)
        card.moved.connect(lambda x, y: self._move_card(x, y, persist=False))
        card.move_finished.connect(lambda x, y: self._move_card(x, y, persist=True))
        card.layer_requested.connect(self._request_layer_toggle)
        card.set_layer_floating(self._floating)
        card.apply_layer(self._floating)
        card.winId()
        if not self._host.prepare(card, self._floating):
            card.close()
            card.deleteLater()
            return False
        card.show()
        self._card = card
        self._render()
        return True

    def _render(self) -> None:
        if self._card is None or not self._plan.current or self._plan.current not in self._catalog:
            return
        entry = self._catalog[self._plan.current]
        correct, reviews = self._progress.get(self._plan.current, (0, 0))
        self._card.set_content(
            entry.word,
            entry.phonetic,
            entry.translation,
            correct,
            reviews,
            self._face,
        )
        self._host.set_click_through(self._card, False)
        placed = self._host.place([self._card], MIN_FRONT_HEIGHT, [self._origin])
        if self._origin is not None and placed:
            self._origin = placed[0]

    def _move_card(self, x: int, y: int, persist: bool) -> None:
        if self._card is None:
            return
        self._origin = self._host.move(self._card, x, y)
        if persist:
            self._persist()

    def _persist(self) -> None:
        self._store.save_state(
            AppState(
                hidden=self._hidden,
                active_source=self._active_id,
                word=self._plan.current,
                origin=self._origin,
                floating=self._floating,
                daily_goal=self._plan.goal,
            )
        )
        self._store.save_daily(
            DailyRecord(
                day=self._plan.day,
                collected=self._plan.collected,
                queue=self._plan.queue,
                phase=self._plan.phase,
            )
        )

    def _destroy_windows(self) -> None:
        if self._card is None:
            return
        self._card.hide()
        self._card.close()
        self._card.deleteLater()
        self._card = None

    def _sync_layer_controls(self) -> None:
        self._tray.set_floating(self._floating)
        if self._card is not None:
            self._card.set_layer_floating(self._floating)

    def _sync_daily_tray(self) -> None:
        self._tray.set_daily_progress(self._plan.count, self._plan.goal)

    def _check_day(self) -> None:
        updated = ensure_day(self._plan, _today())
        if updated is self._plan:
            return
        self._plan = updated
        self._sync_daily_tray()
        self._persist()

    def _notify_embed_failed(self) -> None:
        if not self._embed_notified:
            self._tray.show_embed_failed()
            self._embed_notified = True

    def _teardown(self) -> None:
        self._persist()
        self._hotkey.stop()
        self._day_timer.stop()
        self._destroy_windows()
        self._store.close()


def _plan_from_store(store: Store, persisted: AppState, today: str) -> DailyPlan:
    record = store.load_daily()
    if record is None or record.day != today:
        return DailyPlan(
            goal=persisted.daily_goal,
            day=today,
            collected=(),
            queue=(),
            phase=0,
            current=persisted.word,
        )
    return DailyPlan(
        goal=persisted.daily_goal,
        day=record.day,
        collected=record.collected,
        queue=record.queue,
        phase=record.phase,
        current=persisted.word,
    )


def _today() -> str:
    return date.today().isoformat()


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
