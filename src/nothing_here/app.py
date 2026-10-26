from __future__ import annotations

import ctypes
import sys
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFileDialog

from nothing_here.desktop.host import DesktopHost
from nothing_here.domain.formats import SUPPORTED_SUFFIXES, dialog_filter, extract_book_text
from nothing_here.domain.loaf import PaySettings, format_clock, needs_rates, strip_text
from nothing_here.domain.read import chapter_starts, turn_chapter, turn_page
from nothing_here.domain.daily import (
    DailyPlan,
    grade,
    resolve_current,
    restore,
    set_goal,
    slay,
    switch_catalog,
)
from nothing_here.domain.spell import (
    SpellMode,
    SpellState,
    accept_invite,
    advance_spelling,
    after_plan_change,
    answers_match,
    decline_invite,
    dismiss_invite_on_hide,
    empty_spell,
    end_spelling,
    ensure_spell_day,
    exit_spell_modes,
    mute_invite,
    register_miss,
    start_from_tray,
    toggle_example,
)
from nothing_here.fx import fetch_eur_rates
from nothing_here.input.hotkey import HotkeyListener
from nothing_here.storage.db import AppState, DailyRecord, LoafRecord, Store
from nothing_here.ui.card_window import CardWindow, Face
from nothing_here.ui.read_window import READ_CARD_SIZE, READ_FONT_PX, READ_LEADING, ReadWindow
from nothing_here.ui.skins import skin_for
from nothing_here.ui.tray import Tray
from nothing_here.ui.wage_strip import WageStrip
from nothing_here.ui.work_status_dialog import WorkStatusDialog
from nothing_here.vocab.examples import EntryExampleSource, load_example_sources, resolve_example
from nothing_here.vocab.protocol import Entry, VocabSource
from nothing_here.vocab.registry import catalog_from, load_sources

INSTANCE_NAME = "Local\\NothingHere"
_ERROR_ALREADY_EXISTS = 183
MIN_FRONT_HEIGHT = 96


class ViewState(Enum):
    HIDDEN = "hidden"
    VISIBLE = "visible"


class _RateFetch(QThread):
    loaded = pyqtSignal(object)

    def run(self) -> None:
        self.loaded.emit(fetch_eur_rates())


class App(QObject):
    visibility_hotkey_pressed = pyqtSignal()

    def __init__(self, qt_app: QApplication) -> None:
        super().__init__()
        self._qt_app = qt_app
        self._store = Store()
        self._sources = load_sources()
        self._source_by_id = {source.source_id: source for source in self._sources}
        self._catalogs: dict[str, dict[str, Entry]] = {}
        self._spellings: dict[str, str] = {}
        for source in self._sources:
            catalog = catalog_from(source)
            self._catalogs[source.source_id] = catalog
            for key, entry in catalog.items():
                self._spellings.setdefault(key, entry.word)
        persisted = self._store.load_state()
        self._active_id = _pick_source(self._sources, persisted.active_source)
        self._catalog = self._catalogs[self._active_id]
        self._example_sources = load_example_sources()
        self._bind_examples()
        self._progress = self._store.all_progress()
        self._slain = set(self._store.slain_words())
        self._spell = _spell_from_store(self._store, persisted, _today())
        plan = resolve_current(
            self._spell.plan,
            list(self._catalog),
            self._progress,
            slain=self._slain_seq(),
        )
        if plan is not self._spell.plan:
            self._spell = after_plan_change(
                self._spell,
                self._spell.plan,
                plan,
                self._progress,
                consider_invite=False,
            )
        self._origin = persisted.origin
        self._floating = persisted.floating
        self._hidden = persisted.hidden
        self._style_preset = persisted.style_preset
        self._text_color = persisted.text_color
        self._fill_color = persisted.fill_color
        self._fill_alpha = persisted.fill_alpha
        self._button_preset = persisted.button_preset
        self._surface_id = persisted.surface_id if persisted.surface_id in ("word", "read") else "word"
        self._read_origin = persisted.read_origin
        self._read_card = persisted.read_card
        self._read_font = persisted.read_font
        self._read_leading = persisted.read_leading
        self._books = self._store.list_books()
        known_books = {book.book_id for book in self._books}
        self._current_book = persisted.current_book if persisted.current_book in known_books else None
        if self._current_book is None and self._books:
            self._current_book = self._books[0].book_id
        self._book_text = ""
        self._offset = 0
        self._chapters: tuple[int, ...] = (0,)
        self._page_starts: tuple[int, ...] = (0,)
        if self._current_book:
            self._load_open_book(self._current_book)
        loaf = self._store.load_loaf()
        self._pay = _pay_from(loaf)
        self._loaf_hidden = loaf.hidden
        self._loaf_origin = loaf.origin
        self._skin_id = skin_for(self._store.load_skin()).skin_id
        self._fx_attempted, fx_raw = self._store.load_fx()
        self._fx_rates = _rates_from(fx_raw)
        self._fx_missing_tried = False
        self._suppressed = False
        self._closing = False
        self._loaf: Optional[WageStrip] = None
        self._fx_thread: Optional[_RateFetch] = None
        self._loaf_timer = QTimer(self)
        self._loaf_timer.setInterval(1000)
        self._loaf_timer.timeout.connect(self._refresh_loaf)
        self._view = ViewState.HIDDEN
        self._face = Face.FRONT
        self._card: Optional[CardWindow | ReadWindow] = None
        self._pending_plan: Optional[DailyPlan] = None
        self._burning = False
        self._host = DesktopHost()
        self._host.floating = self._floating
        self._embed_notified = False
        self._tray = Tray(
            self._sources,
            self._active_id,
            self._floating,
            self._spell.plan.count,
            self._spell.plan.goal,
            self._slain_items(),
            self._style_preset,
            self._text_color,
            self._fill_color,
            self._fill_alpha,
            spell_tray=self._spell.tray_unlocked,
            surface_id=self._surface_id,
            books=[(book.book_id, book.title) for book in self._books],
            current_book=self._current_book,
            read_card=self._read_card,
            read_font=self._read_font,
            read_leading=self._read_leading,
        )
        self._sync_loaf_tray()
        self._tray.set_card_hidden(self._hidden)
        self._tray.card_hidden_chosen.connect(self.set_card_hidden)
        self._tray.goal_chosen.connect(self.change_goal)
        self._tray.source_chosen.connect(self.switch_source)
        self._tray.layer_chosen.connect(self.set_floating)
        self._tray.quit_requested.connect(self.quit)
        self._tray.restore_chosen.connect(self.restore_word)
        self._tray.style_preset_chosen.connect(self.choose_style_preset)
        self._tray.style_custom_chosen.connect(self.choose_custom_style)
        self._tray.surface_chosen.connect(self.choose_surface)
        self._tray.spell_start_chosen.connect(self.start_spell_from_tray)
        self._tray.book_chosen.connect(self.choose_book)
        self._tray.book_import_chosen.connect(self.import_book)
        self._tray.book_remove_chosen.connect(self.remove_current_book)
        self._tray.read_card_chosen.connect(self.choose_read_card)
        self._tray.read_font_chosen.connect(self.choose_read_font)
        self._tray.read_leading_chosen.connect(self.choose_read_leading)
        self._tray.loaf_hidden_chosen.connect(self.set_loaf_hidden)
        self._tray.loaf_display_chosen.connect(self.set_loaf_display)
        self._tray.loaf_status_chosen.connect(self.edit_work_status)
        self._tray.skin_chosen.connect(self.set_skin)
        self._tray.suppress_chosen.connect(self.toggle_visibility)
        self._tray.set_skin(self._skin_id)
        self.visibility_hotkey_pressed.connect(self.toggle_visibility)
        self._hotkey = HotkeyListener(self.visibility_hotkey_pressed.emit)
        self._hotkey.start()
        self._day_timer = QTimer(self)
        self._day_timer.timeout.connect(self._check_day)
        self._day_timer.start(60_000)
        qt_app.aboutToQuit.connect(self._teardown)

    @property
    def _plan(self) -> DailyPlan:
        return self._spell.plan

    @_plan.setter
    def _plan(self, value: DailyPlan) -> None:
        self._spell = replace(self._spell, plan=value)

    def start(self) -> None:
        if not self._hidden:
            self.show_cards()
        self._apply_loaf()
        self._ensure_rates()

    def set_card_hidden(self, hidden: bool) -> None:
        if hidden:
            self.hide_cards()
        else:
            self.show_cards()
        self._tray.set_card_hidden(self._hidden)

    def show_cards(self) -> None:
        if self._view is not ViewState.HIDDEN:
            return
        self._check_day()
        self._hidden = False
        before = self._spell.plan
        after = resolve_current(
            before,
            list(self._catalog),
            self._progress,
            slain=self._slain_seq(),
        )
        if after is not before:
            self._spell = after_plan_change(
                self._spell, before, after, self._progress, consider_invite=False
            )
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
        self._tray.set_card_hidden(False)
        self._persist()

    def hide_cards(self) -> None:
        self._hidden = True
        self._tray.set_card_hidden(True)
        if self._view is ViewState.HIDDEN:
            self._persist()
            return
        self._take_pending_slay()
        self._spell = dismiss_invite_on_hide(self._spell)
        self._destroy_windows()
        self._view = ViewState.HIDDEN
        self._hidden = True
        self._face = Face.FRONT
        self._persist()

    def change_goal(self, goal: int) -> None:
        if self._burning or self._surface_id != "word":
            return
        self._check_day()
        previous = self._plan
        was_mode = self._spell.mode
        next_plan = set_goal(
            self._plan,
            goal,
            list(self._catalog),
            self._progress,
            slain=self._slain_seq(),
        )
        if next_plan == previous and was_mode is SpellMode.NORMAL:
            return
        unsealed = previous.sealed and not next_plan.sealed
        current_dropped = (
            was_mode is not SpellMode.NORMAL
            and previous.current is not None
            and (
                next_plan.current != previous.current
                or (previous.current not in next_plan.collected and next_plan.sealed)
            )
        )
        self._spell = replace(self._spell, plan=next_plan)
        if unsealed or current_dropped or (
            was_mode is not SpellMode.NORMAL and not next_plan.sealed
        ):
            self._spell = exit_spell_modes(self._spell)
            self._face = Face.FRONT
        elif was_mode is SpellMode.NORMAL:
            word_changed = next_plan.current != previous.current
            just_sealed = not previous.sealed and next_plan.sealed
            if word_changed or just_sealed:
                self._face = Face.FRONT
            if just_sealed:
                self._spell = after_plan_change(
                    self._spell, previous, next_plan, self._progress
                )
        self._sync_daily_tray()
        if self._view is ViewState.VISIBLE:
            if self._card is None or self._face is Face.FRONT or was_mode is not SpellMode.NORMAL:
                if not self._open_card(self._face):
                    self._notify_embed_failed()
                    self._view = ViewState.HIDDEN
            else:
                self._render()
        self._persist()

    def _request_layer_toggle(self) -> None:
        QTimer.singleShot(0, lambda: self.set_floating(not self._floating))

    def set_floating(self, floating: bool) -> None:
        if self._burning:
            self._sync_layer_controls()
            return
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
        if not self._loaf_hidden and not self._suppressed:
            self._open_loaf()
        self._sync_layer_controls()
        self._persist()

    def toggle_visibility(self) -> None:
        if self._suppressed:
            self._suppressed = False
            if not self._hidden:
                self.show_cards()
            self._apply_loaf()
            return
        card_on = self._view is ViewState.VISIBLE
        loaf_on = self._loaf is not None
        if not card_on and not loaf_on:
            return
        self._suppressed = True
        if card_on:
            self._take_pending_slay()
            self._spell = dismiss_invite_on_hide(self._spell)
            self._destroy_windows()
            self._view = ViewState.HIDDEN
            self._face = Face.FRONT
        self._close_loaf()

    def switch_source(self, source_id: str) -> None:
        if self._burning or self._surface_id != "word" or source_id not in self._source_by_id:
            return
        self._check_day()
        visible = self._view is ViewState.VISIBLE
        self._active_id = source_id
        self._catalog = self._catalogs[source_id]
        self._bind_examples()
        before = self._plan
        after = switch_catalog(
            before,
            list(self._catalog),
            self._progress,
            slain=self._slain_seq(),
        )
        self._spell = exit_spell_modes(replace(self._spell, plan=after))
        self._face = Face.FRONT
        self._tray.set_active_source(source_id)
        self._sync_daily_tray()
        if visible:
            needs_desktop = not self._floating and not self._host.available
            if needs_desktop or not self._open_card(Face.FRONT):
                self._destroy_windows()
                self._view = ViewState.HIDDEN
                self._notify_embed_failed()
            else:
                self._view = ViewState.VISIBLE
        self._persist()

    def start_spell_from_tray(self) -> None:
        if self._burning or self._surface_id != "word":
            return
        self._check_day()
        previous = self._spell
        self._spell = start_from_tray(self._spell, self._progress)
        if self._spell is previous or self._spell.mode is not SpellMode.SPELLING:
            self._sync_daily_tray()
            return
        self._face = Face.FRONT
        self._sync_daily_tray()
        if self._view is ViewState.HIDDEN:
            self.show_cards()
        elif self._card is None:
            if not self._open_card(Face.FRONT):
                self._notify_embed_failed()
                self._view = ViewState.HIDDEN
        else:
            self._render()
        self._persist()

    def restore_word(self, word: str) -> None:
        if self._burning or self._surface_id != "word":
            return
        key = word.casefold()
        if key not in self._slain:
            return
        was_finished = self._plan.current is None
        self._store.restore_word(key)
        self._slain.discard(key)
        self._plan = restore(
            self._plan,
            key,
            list(self._catalog),
            self._progress,
            self._slain_seq(),
        )
        self._tray.set_slain_items(self._slain_items())
        if was_finished and self._plan.current is not None and self._view is ViewState.VISIBLE:
            self._face = Face.FRONT
            opened = True
            if self._card is None:
                opened = self._open_card(Face.FRONT)
            else:
                self._render()
            if not opened:
                self._notify_embed_failed()
                self._view = ViewState.HIDDEN
        self._persist()

    def choose_style_preset(self, preset: str) -> None:
        if preset not in ("light", "dark"):
            self._sync_style_tray()
            return
        if self._style_preset == preset:
            self._sync_style_tray()
            return
        self._style_preset = preset
        self._button_preset = preset
        self._text_color = None
        self._fill_color = None
        self._fill_alpha = None
        self._sync_style_tray()
        self._apply_style()
        self._persist()

    def set_skin(self, skin_id: str) -> None:
        chosen = skin_for(skin_id).skin_id
        if chosen == self._skin_id:
            self._tray.set_skin(self._skin_id)
            return
        self._skin_id = chosen
        self._store.save_skin(chosen)
        self._tray.set_skin(chosen)
        self._apply_style()
        if self._loaf is not None:
            self._loaf.apply_skin(skin_for(chosen))
            self._place_loaf()

    def choose_custom_style(self, text: str, fill: str, alpha: int) -> None:
        self._style_preset = "custom"
        self._text_color = text.upper()
        self._fill_color = fill.upper()
        self._fill_alpha = max(20, min(230, int(alpha)))
        self._sync_style_tray()
        self._apply_style()
        self._persist()

    def choose_surface(self, surface_id: str) -> None:
        if surface_id not in ("word", "read"):
            self._tray.set_surface(self._surface_id)
            return
        if surface_id == self._surface_id:
            self._tray.set_surface(self._surface_id)
            return
        if self._surface_id == "word":
            self._take_pending_slay()
            if self._spell.mode is SpellMode.INVITE:
                self._spell = dismiss_invite_on_hide(self._spell)
            if self._spell.mode is not SpellMode.SPELLING:
                self._face = Face.FRONT
        self._surface_id = surface_id
        self._tray.set_surface(surface_id)
        if self._view is ViewState.VISIBLE:
            if not self._open_card(self._face):
                self._notify_embed_failed()
                self._view = ViewState.HIDDEN
        self._persist()

    def choose_book(self, book_id: str) -> None:
        self._books = self._store.list_books()
        if book_id not in {book.book_id for book in self._books}:
            self._sync_book_tray()
            return
        if book_id == self._current_book:
            self._sync_book_tray()
            return
        self._current_book = book_id
        self._load_open_book(book_id)
        self._sync_book_tray()
        if self._view is ViewState.VISIBLE and self._surface_id == "read":
            self._render_read()
        self._persist()

    def import_book(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(None, "导入", "", dialog_filter())
        if not path:
            return
        source = Path(path)
        suffix = source.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            self._tray.show_import_failed("导入失败：只能导入 txt、md、html、epub、docx、odt、fb2。")
            return
        try:
            data = source.read_bytes()
        except OSError:
            self._tray.show_import_failed("导入失败：读不到这个文件。")
            return
        text = extract_book_text(suffix, data)
        if text is None:
            self._tray.show_import_failed(
                "导入失败：读不出正文。文件可能是空的、加密的，或不是 UTF-8 / GB18030。"
            )
            return
        record = self._store.add_book(source.stem or "未命名", text)
        self._books = self._store.list_books()
        self._current_book = record.book_id
        self._load_open_book(record.book_id)
        self._sync_book_tray()
        if self._view is ViewState.VISIBLE and self._surface_id == "read":
            self._render_read()
        self._persist()

    def remove_current_book(self) -> None:
        if not self._current_book:
            return
        removed = self._current_book
        nxt = _book_after([book.book_id for book in self._books], removed)
        self._store.remove_book(removed)
        self._books = self._store.list_books()
        ids = {book.book_id for book in self._books}
        self._current_book = nxt if nxt in ids else (self._books[0].book_id if self._books else None)
        if self._current_book:
            self._load_open_book(self._current_book)
        else:
            self._book_text = ""
            self._offset = 0
            self._chapters = (0,)
            self._page_starts = (0,)
        self._sync_book_tray()
        if self._view is ViewState.VISIBLE and self._surface_id == "read":
            self._render_read()
        self._persist()

    def choose_read_card(self, size: str) -> None:
        self._choose_read_level("card", size)

    def choose_read_font(self, size: str) -> None:
        self._choose_read_level("font", size)

    def choose_read_leading(self, leading: str) -> None:
        self._choose_read_level("leading", leading)

    def set_loaf_hidden(self, hidden: bool) -> None:
        self._loaf_hidden = bool(hidden)
        self._apply_loaf()
        self._sync_loaf_tray()
        self._persist_loaf()

    def set_loaf_display(self, display: str) -> None:
        if display == self._pay.display:
            self._sync_loaf_tray()
            return
        self._pay = replace(self._pay, display=display)
        self._sync_loaf()

    def edit_work_status(self) -> None:
        dialog = WorkStatusDialog(
            self._pay.pay_mode,
            format(self._pay.daily_amount, "f"),
            format(self._pay.monthly_amount, "f"),
            self._pay.unit,
            _clock_text(self._pay.work_start),
            _clock_text(self._pay.work_end),
            _clock_text(self._pay.lunch_start),
            _clock_text(self._pay.lunch_end),
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        result = dialog.commit()
        if not result.ok:
            return
        self._pay = replace(
            self._pay,
            pay_mode=dialog.pay_mode(),
            daily_amount=Decimal(dialog.daily_amount()),
            monthly_amount=Decimal(dialog.monthly_amount()),
            unit=dialog.unit(),
            work_start=result.work_start,
            work_end=result.work_end,
            lunch_start=result.lunch_start,
            lunch_end=result.lunch_end,
        )
        self._sync_loaf()

    def quit(self) -> None:
        self._take_pending_slay()
        self._persist()
        self._qt_app.quit()

    def _grade(self, known: bool) -> None:
        if self._burning or self._spell.mode is not SpellMode.NORMAL:
            return
        self._check_day()
        if self._view is not ViewState.VISIBLE or self._face is not Face.BACK:
            return
        if self._plan.current is None:
            return
        correct, reviews = self._store.record(self._plan.current, known)
        self._progress[self._plan.current] = (correct, reviews)
        before = self._plan
        after = grade(
            before,
            known,
            list(self._catalog),
            self._progress,
            slain=self._slain_seq(),
        )
        self._spell = after_plan_change(self._spell, before, after, self._progress)
        self._face = Face.FRONT
        self._sync_daily_tray()
        if self._card is None:
            if not self._open_card(Face.FRONT):
                self._notify_embed_failed()
                self._view = ViewState.HIDDEN
        else:
            self._render()
        self._persist()

    def _on_invite_start(self) -> None:
        self._spell = accept_invite(self._spell)
        self._face = Face.FRONT
        self._sync_daily_tray()
        self._render()
        self._persist()

    def _on_invite_later(self) -> None:
        self._spell = decline_invite(self._spell)
        self._face = Face.FRONT
        self._sync_daily_tray()
        self._render()
        self._persist()

    def _on_invite_mute(self) -> None:
        self._spell = mute_invite(self._spell)
        self._face = Face.FRONT
        self._sync_daily_tray()
        self._render()
        self._persist()

    def _on_spell_end(self) -> None:
        self._spell = end_spelling(self._spell)
        self._face = Face.FRONT
        self._sync_daily_tray()
        self._render()
        self._persist()

    def _on_spell_submitted(self, typed: str) -> None:
        if self._spell.mode is not SpellMode.SPELLING or self._plan.current is None:
            return
        word = self._plan.current
        entry = self._catalog.get(word)
        expected = entry.word if entry is not None else word
        if answers_match(expected, typed):
            self._spell = advance_spelling(
                self._spell,
                list(self._catalog),
                self._progress,
                slain=self._slain_seq(),
            )
            self._sync_daily_tray()
            self._render()
            self._persist()
            return
        self._spell = register_miss(self._spell)
        if isinstance(self._card, CardWindow):
            self._card.clear_spell_letters()
            self._render()
        self._persist()

    def _on_spell_skip(self) -> None:
        if self._spell.mode is not SpellMode.SPELLING or not self._spell.example_open:
            return
        self._spell = advance_spelling(
            self._spell,
            list(self._catalog),
            self._progress,
            slain=self._slain_seq(),
        )
        self._sync_daily_tray()
        self._render()
        self._persist()

    def _toggle_face(self) -> None:
        if self._burning or self._view is ViewState.HIDDEN or self._card is None:
            return
        if self._spell.mode is SpellMode.SPELLING:
            self._spell = toggle_example(self._spell)
            self._render()
            self._persist()
            return
        if self._spell.mode is not SpellMode.NORMAL:
            return
        if self._plan.current is None or self._plan.current not in self._catalog:
            return
        self._face = Face.BACK if self._face is Face.FRONT else Face.FRONT
        self._render()

    def _slay(self) -> None:
        if (
            self._burning
            or self._spell.mode is not SpellMode.NORMAL
            or self._view is not ViewState.VISIBLE
            or self._face is not Face.BACK
        ):
            return
        if not isinstance(self._card, CardWindow) or self._plan.current is None:
            return
        if self._plan.current not in self._catalog:
            return
        word = self._plan.current
        self._store.slay_word(word)
        self._slain.add(word.casefold())
        self._pending_plan = slay(
            self._plan,
            list(self._catalog),
            self._progress,
            self._slain_seq(),
        )
        self._burning = True
        self._tray.set_slain_items(self._slain_items())
        self._card.play_burn()

    def _on_burn_finished(self) -> None:
        pending = self._pending_plan
        self._pending_plan = None
        self._burning = False
        if pending is not None:
            before = self._plan
            self._spell = after_plan_change(self._spell, before, pending, self._progress)
        self._face = Face.FRONT
        self._sync_daily_tray()
        if self._view is ViewState.VISIBLE and isinstance(self._card, CardWindow):
            self._render()
            self._card.finish_burn()
        self._persist()

    def _open_card(self, face: Face) -> bool:
        if self._surface_id == "read":
            return self._open_read_card()
        self._destroy_windows()
        self._face = face
        card = CardWindow()
        card.recognized.connect(lambda: self._grade(True))
        card.unknown.connect(lambda: self._grade(False))
        card.reveal_toggled.connect(self._toggle_face)
        card.slay_requested.connect(self._slay)
        card.burn_finished.connect(self._on_burn_finished)
        card.moved.connect(lambda x, y: self._move_card(x, y, persist=False))
        card.move_finished.connect(lambda x, y: self._move_card(x, y, persist=True))
        card.layer_requested.connect(self._request_layer_toggle)
        card.invite_start.connect(self._on_invite_start)
        card.invite_later.connect(self._on_invite_later)
        card.invite_mute.connect(self._on_invite_mute)
        card.spell_end.connect(self._on_spell_end)
        card.spell_skip.connect(self._on_spell_skip)
        card.spell_submitted.connect(self._on_spell_submitted)
        card.set_layer_floating(self._floating)
        self._dress(card)
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
        if self._surface_id == "read":
            self._render_read()
            return
        if not isinstance(self._card, CardWindow):
            return
        self._dress(self._card)
        self._card.set_layer_floating(self._floating)
        mode = self._spell.mode
        if mode is SpellMode.INVITE:
            self._card.show_invite()
        elif mode is SpellMode.SPELLING:
            word = self._plan.current
            if not word or word not in self._catalog:
                self._spell = end_spelling(self._spell)
                self._card.show_finished()
            else:
                entry = self._catalog[word]
                example = resolve_example(self._example_sources, entry.word)
                self._card.show_spelling(
                    entry.word,
                    entry.phonetic,
                    entry.translation,
                    example,
                    self._spell.example_open,
                    floating=self._floating,
                )
        else:
            word = self._plan.current
            if not word or word not in self._catalog:
                self._card.show_finished()
            else:
                entry = self._catalog[word]
                correct, reviews = self._progress.get(word, (0, 0))
                example = ""
                if self._face is Face.BACK:
                    example = resolve_example(self._example_sources, entry.word)
                self._card.set_content(
                    entry.word,
                    entry.phonetic,
                    entry.translation,
                    correct,
                    reviews,
                    self._face,
                    example,
                )
        self._host.set_click_through(self._card, False)
        placed = self._host.place([self._card], MIN_FRONT_HEIGHT, [self._origin])
        if self._origin is not None and placed:
            self._origin = placed[0]

    def _move_card(self, x: int, y: int, persist: bool) -> None:
        if self._card is None or self._burning:
            return
        origin = self._host.move(self._card, x, y)
        if self._surface_id == "read":
            self._read_origin = origin
        else:
            self._origin = origin
        if persist:
            self._persist()

    def _sync_loaf(self) -> None:
        self._sync_loaf_tray()
        self._ensure_rates()
        self._apply_loaf()
        self._persist_loaf()

    def _sync_loaf_tray(self) -> None:
        self._tray.set_loaf(self._pay.display, self._loaf_hidden)

    def _apply_loaf(self) -> None:
        if self._loaf_hidden or self._suppressed:
            self._close_loaf()
            return
        if self._loaf is None:
            self._open_loaf()
            return
        self._dress(self._loaf)
        self._refresh_loaf()

    def _open_loaf(self) -> bool:
        self._close_loaf()
        strip = WageStrip()
        self._dress(strip)
        strip.apply_layer(self._floating)
        strip.set_line(self._loaf_line())
        strip.moved.connect(lambda x, y: self._move_loaf(x, y, False))
        strip.move_finished.connect(lambda x, y: self._move_loaf(x, y, True))
        strip.winId()
        if not self._host.prepare(strip, self._floating):
            strip.close()
            strip.deleteLater()
            if not self._floating:
                self._notify_embed_failed()
            return False
        origin = self._loaf_origin or self._default_loaf_origin()
        self._loaf_origin = self._host.move(strip, origin[0], origin[1])
        strip.show()
        self._loaf = strip
        self._loaf_timer.start()
        return True

    def _close_loaf(self) -> None:
        self._loaf_timer.stop()
        if self._loaf is None:
            return
        self._loaf.hide()
        self._loaf.close()
        self._loaf.deleteLater()
        self._loaf = None

    def _refresh_loaf(self) -> None:
        if self._loaf is None:
            return
        text = self._loaf_line()
        if text == self._loaf.line():
            return
        self._loaf.set_line(text)
        self._place_loaf()

    def _place_loaf(self) -> None:
        if self._loaf is None:
            return
        origin = self._loaf_origin or self._default_loaf_origin()
        self._loaf_origin = self._host.move(self._loaf, origin[0], origin[1])

    def _move_loaf(self, x: int, y: int, persist: bool) -> None:
        if self._loaf is None:
            return
        self._loaf_origin = self._host.move(self._loaf, x, y)
        if persist:
            self._persist_loaf()

    def _default_loaf_origin(self) -> tuple[int, int]:
        work = self._host.work_rect()
        return (work.left() + 24, work.top() + 24)

    def _loaf_line(self) -> str:
        return strip_text(self._pay, datetime.now(), self._fx_rates)

    def _ensure_rates(self) -> None:
        if self._closing or self._pay.display == self._pay.unit:
            return
        today = date.today().isoformat()
        if self._fx_attempted != today:
            self._fx_missing_tried = False
        if self._fx_thread is not None:
            return
        missing = needs_rates(self._pay.unit, self._pay.display, self._fx_rates)
        if not missing and self._fx_attempted == today:
            return
        if missing and self._fx_missing_tried:
            return
        if missing:
            self._fx_missing_tried = True
        self._fx_attempted = today
        self._store.save_fx(today, None)
        job = _RateFetch(self)
        job.loaded.connect(self._on_rates)
        job.finished.connect(job.deleteLater)
        self._fx_thread = job
        job.start()

    def _on_rates(self, rates: object) -> None:
        self._fx_thread = None
        if self._closing or not isinstance(rates, dict):
            self._refresh_loaf()
            return
        if "VND" not in rates and self._fx_rates and "VND" in self._fx_rates:
            rates = {**rates, "VND": self._fx_rates["VND"]}
        self._fx_rates = rates
        self._store.save_fx(
            self._fx_attempted,
            {str(key): format(value, "f") for key, value in rates.items()},
        )
        self._refresh_loaf()

    def _persist(self) -> None:
        self._store.save_state(
            AppState(
                hidden=self._hidden,
                active_source=self._active_id,
                word=self._plan.current,
                origin=self._origin,
                floating=self._floating,
                daily_goal=self._plan.goal,
                style_preset=self._style_preset,
                text_color=self._text_color,
                fill_color=self._fill_color,
                fill_alpha=self._fill_alpha,
                surface_id=self._surface_id,
                button_preset=self._button_preset,
                read_origin=self._read_origin,
                read_card=self._read_card,
                read_font=self._read_font,
                read_leading=self._read_leading,
                current_book=self._current_book,
            )
        )
        self._store.save_daily(
            DailyRecord(
                day=self._plan.day,
                collected=self._plan.collected,
                queue=self._plan.queue,
                phase=self._plan.phase,
                spell_mode=self._spell.mode.value,
                spell_cooldown=self._spell.cooldown,
                spell_mute=self._spell.mute_invite,
                spell_tray=self._spell.tray_unlocked,
                spell_misses=self._spell.miss_count,
                spell_example_open=self._spell.example_open,
            )
        )
        self._persist_loaf()

    def _persist_loaf(self) -> None:
        self._store.save_loaf(
            LoafRecord(
                hidden=self._loaf_hidden,
                pay_mode=self._pay.pay_mode,
                daily_amount=format(self._pay.daily_amount, "f"),
                monthly_amount=format(self._pay.monthly_amount, "f"),
                unit=self._pay.unit,
                display=self._pay.display,
                work_start=self._pay.work_start,
                work_end=self._pay.work_end,
                lunch_start=self._pay.lunch_start,
                lunch_end=self._pay.lunch_end,
                origin=self._loaf_origin,
            )
        )

    def _destroy_windows(self) -> None:
        if self._card is None:
            return
        if isinstance(self._card, CardWindow):
            self._card.cancel_burn()
            self._card.release_spell_input()
        self._card.hide()
        self._card.close()
        self._card.deleteLater()
        self._card = None

    def _take_pending_slay(self) -> None:
        if isinstance(self._card, CardWindow):
            self._card.cancel_burn()
        if self._pending_plan is not None:
            self._plan = self._pending_plan
            self._pending_plan = None
            self._face = Face.FRONT
        self._burning = False

    def _sync_layer_controls(self) -> None:
        self._tray.set_floating(self._floating)
        if self._card is not None:
            self._card.set_layer_floating(self._floating)

    def _sync_daily_tray(self) -> None:
        self._tray.set_daily_progress(self._plan.count, self._plan.goal)
        self._tray.set_spell_tray_visible(self._spell.tray_unlocked)

    def _sync_style_tray(self) -> None:
        self._tray.set_style_state(
            self._style_preset,
            self._text_color,
            self._fill_color,
            self._fill_alpha,
        )

    def _dress(self, widget) -> None:
        widget.apply_skin(skin_for(self._skin_id))
        widget.apply_palette(self._palette())

    def _apply_style(self) -> None:
        if self._card is not None:
            self._dress(self._card)
        if self._loaf is not None:
            self._dress(self._loaf)

    def _palette(self):
        return skin_for(self._skin_id).palette(
            self._style_preset,
            self._text_color,
            self._fill_color,
            self._fill_alpha,
            self._button_preset,
        )

    def _check_day(self) -> None:
        self._ensure_rates()
        if self._burning:
            return
        today = _today()
        updated = ensure_spell_day(self._spell, today)
        if updated is self._spell:
            return
        self._spell = updated
        self._face = Face.FRONT
        self._sync_daily_tray()
        if self._view is ViewState.VISIBLE and self._card is not None:
            self._render()
        self._persist()

    def _notify_embed_failed(self) -> None:
        if not self._embed_notified:
            self._tray.show_embed_failed()
            self._embed_notified = True

    def _teardown(self) -> None:
        self._closing = True
        self._take_pending_slay()
        self._persist()
        self._hotkey.stop()
        self._day_timer.stop()
        self._loaf_timer.stop()
        self._close_loaf()
        self._destroy_windows()
        self._store.close()

    def _open_read_card(self) -> bool:
        self._destroy_windows()
        card = ReadWindow()
        card.prev_page.connect(lambda: self._turn_read("page", -1))
        card.next_page.connect(lambda: self._turn_read("page", 1))
        card.prev_chapter.connect(lambda: self._turn_read("chapter", -1))
        card.next_chapter.connect(lambda: self._turn_read("chapter", 1))
        card.moved.connect(lambda x, y: self._move_card(x, y, persist=False))
        card.move_finished.connect(lambda x, y: self._move_card(x, y, persist=True))
        card.layer_requested.connect(self._request_layer_toggle)
        card.set_layer_floating(self._floating)
        self._dress(card)
        card.apply_layer(self._floating)
        card.winId()
        if not self._host.prepare(card, self._floating):
            card.close()
            card.deleteLater()
            return False
        card.show()
        self._card = card
        self._render_read()
        return True

    def _render_read(self) -> None:
        if not isinstance(self._card, ReadWindow):
            return
        card = self._card
        card.apply_palette(self._palette())
        card.set_layer_floating(self._floating)
        work = self._host.work_rect()
        preset_w, preset_h = READ_CARD_SIZE.get(self._read_card, READ_CARD_SIZE["medium"])
        card.set_box(min(preset_w, max(1, work.width())), min(preset_h, max(1, work.height())))
        placed = self._host.place([card], card.preferred_height(), [self._read_origin])
        if self._read_origin is not None and placed:
            self._read_origin = placed[0]
        self._host.set_click_through(card, False)
        pixel = READ_FONT_PX.get(self._read_font, 16)
        ratio = READ_LEADING.get(self._read_leading, 1.5)
        if not self._current_book:
            self._page_starts = (0,)
            card.show_empty(pixel, ratio)
            return
        self._page_starts = card.measure_pages(self._book_text, pixel, ratio)
        if self._book_text:
            self._offset = max(0, min(self._offset, len(self._book_text)))
        card.show_page(self._book_text, self._page_starts, self._offset, pixel, ratio)

    def _turn_read(self, kind: str, step: int) -> None:
        if not isinstance(self._card, ReadWindow) or not self._current_book:
            return
        if kind == "chapter":
            new_offset = turn_chapter(self._chapters, self._offset, step)
        else:
            new_offset = turn_page(self._page_starts, self._offset, step)
        if new_offset == self._offset:
            return
        self._offset = max(0, min(new_offset, len(self._book_text)))
        self._store.set_book_offset(self._current_book, self._offset)
        pixel = READ_FONT_PX.get(self._read_font, 16)
        ratio = READ_LEADING.get(self._read_leading, 1.5)
        self._card.show_page(self._book_text, self._page_starts, self._offset, pixel, ratio)

    def _choose_read_level(self, kind: str, value: str) -> None:
        allowed = {
            "card": READ_CARD_SIZE,
            "font": READ_FONT_PX,
            "leading": READ_LEADING,
        }[kind]
        current = {"card": self._read_card, "font": self._read_font, "leading": self._read_leading}[kind]
        if value not in allowed:
            self._tray.set_read_levels(self._read_card, self._read_font, self._read_leading)
            return
        if value == current:
            return
        if kind == "card":
            self._read_card = value
        elif kind == "font":
            self._read_font = value
        else:
            self._read_leading = value
        self._tray.set_read_levels(self._read_card, self._read_font, self._read_leading)
        if self._view is ViewState.VISIBLE and self._surface_id == "read":
            self._render_read()
        self._persist()

    def _load_open_book(self, book_id: str) -> None:
        text = self._store.read_book_text(book_id)
        stored = 0
        for book in self._books:
            if book.book_id == book_id:
                stored = book.offset
                break
        offset = max(0, min(stored, len(text))) if text else 0
        self._book_text = text
        self._offset = offset
        self._chapters = chapter_starts(text) if text else (0,)
        if offset != stored:
            self._store.set_book_offset(book_id, offset)

    def _sync_book_tray(self) -> None:
        self._tray.set_books(
            [(book.book_id, book.title) for book in self._books],
            self._current_book,
        )

    def _bind_examples(self) -> None:
        source = self._example_sources[0]
        if isinstance(source, EntryExampleSource):
            source.use_examples({key: entry.example for key, entry in self._catalog.items()})

    def _slain_seq(self) -> tuple[str, ...]:
        return tuple(self._slain)

    def _slain_items(self) -> list[tuple[str, str]]:
        return [(word, self._spellings.get(word, word)) for word in self._store.slain_words()]


def _spell_from_store(store: Store, persisted: AppState, today: str) -> SpellState:
    record = store.load_daily()
    if record is None or record.day != today:
        return empty_spell(
            DailyPlan(
                goal=persisted.daily_goal,
                day=today,
                collected=(),
                queue=(),
                phase=0,
                current=persisted.word,
            )
        )
    plan = DailyPlan(
        goal=persisted.daily_goal,
        day=record.day,
        collected=record.collected,
        queue=record.queue,
        phase=record.phase,
        current=persisted.word,
    )
    mode = SpellMode.NORMAL
    if record.spell_mode == "spelling" and plan.current is not None:
        mode = SpellMode.SPELLING
    return SpellState(
        plan=plan,
        mode=mode,
        cooldown=record.spell_cooldown,
        mute_invite=record.spell_mute,
        tray_unlocked=record.spell_tray,
        miss_count=record.spell_misses if mode is SpellMode.SPELLING else 0,
        example_open=record.spell_example_open if mode is SpellMode.SPELLING else False,
    )


def _today() -> str:
    return date.today().isoformat()


def _book_after(ids: list[str], removed: str) -> Optional[str]:
    if removed not in ids:
        return None
    index = ids.index(removed)
    for candidate in ids[index + 1 :]:
        return candidate
    for candidate in ids:
        if candidate != removed:
            return candidate
    return None


def _pick_source(sources: list[VocabSource], wanted: str) -> str:
    ids = {source.source_id for source in sources}
    if wanted in ids:
        return wanted
    return sources[0].source_id


def _clock_text(minute: Optional[int]) -> str:
    if minute is None:
        return ""
    return format_clock(minute)


def _pay_from(record: LoafRecord) -> PaySettings:
    return PaySettings(
        pay_mode=record.pay_mode,
        daily_amount=_money(record.daily_amount),
        monthly_amount=_money(record.monthly_amount),
        unit=record.unit,
        display=record.display,
        work_start=record.work_start,
        work_end=record.work_end,
        lunch_start=record.lunch_start,
        lunch_end=record.lunch_end,
    )


def _money(text: str) -> Decimal:
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return Decimal(0)
    if amount < 0:
        return Decimal(0)
    return amount


def _rates_from(raw: dict[str, str]) -> dict[str, Decimal]:
    rates: dict[str, Decimal] = {}
    for key, value in raw.items():
        try:
            rate = Decimal(value)
        except InvalidOperation:
            continue
        if rate > 0:
            rates[key] = rate
    return rates


def _set_app_id() -> None:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NothingHere")


class _SingleInstance:
    """进程活着就握着这把互斥量。系统在进程退出或崩溃时放开。"""

    def __init__(self, handle: int) -> None:
        self._handle = handle

    def close(self) -> None:
        if not self._handle:
            return
        ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = 0


def acquire_instance(name: str = INSTANCE_NAME) -> Optional[_SingleInstance]:
    """同一 Windows 会话里只留一个进程。创建互斥量是原子的，两个进程一起启动也不会都通过。"""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.SetLastError(0)
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle or kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        if handle:
            kernel32.CloseHandle(handle)
        return None
    return _SingleInstance(int(handle))


def main() -> int:
    _set_app_id()
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Nothing Here")
    qt_app.setQuitOnLastWindowClosed(False)
    instance = acquire_instance()
    if instance is None:
        return 0
    app = App(qt_app)
    app._instance = instance  # noqa: SLF001 — 进程结束前不放开互斥量
    app.start()
    return qt_app.exec()
