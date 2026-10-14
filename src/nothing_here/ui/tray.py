from __future__ import annotations

from typing import Optional, Sequence

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QColorDialog, QInputDialog, QMenu, QMessageBox, QSystemTrayIcon

from nothing_here.domain.daily import GOAL_MAX, GOAL_MIN
from nothing_here.vocab.protocol import VocabSource

_CARD_LEVELS = (("large", "大"), ("medium", "中"), ("small", "小"))
_LEADING_LEVELS = (("loose", "大"), ("medium", "中"), ("tight", "小"))


class Tray(QObject):
    show_cards = pyqtSignal()
    hide_cards = pyqtSignal()
    goal_chosen = pyqtSignal(int)
    source_chosen = pyqtSignal(str)
    layer_chosen = pyqtSignal(bool)
    quit_requested = pyqtSignal()
    restore_chosen = pyqtSignal(str)
    style_preset_chosen = pyqtSignal(str)
    style_custom_chosen = pyqtSignal(str, str, int)
    surface_chosen = pyqtSignal(str)
    spell_start_chosen = pyqtSignal()
    book_chosen = pyqtSignal(str)
    book_import_chosen = pyqtSignal()
    book_remove_chosen = pyqtSignal()
    read_card_chosen = pyqtSignal(str)
    read_font_chosen = pyqtSignal(str)
    read_leading_chosen = pyqtSignal(str)

    def __init__(
        self,
        sources: Sequence[VocabSource],
        active_source: str,
        floating: bool,
        collected: int = 0,
        goal: int = 10,
        slain_items: Sequence[tuple[str, str]] = (),
        style_preset: str = "light",
        text_color: Optional[str] = None,
        fill_color: Optional[str] = None,
        fill_alpha: Optional[int] = None,
        spell_tray: bool = False,
        surface_id: str = "word",
        books: Sequence[tuple[str, str]] = (),
        current_book: Optional[str] = None,
        read_card: str = "medium",
        read_font: str = "medium",
        read_leading: str = "medium",
    ) -> None:
        super().__init__()
        self._goal = goal
        self._slain_items = list(slain_items)
        self._style_preset = style_preset
        self._text_color = text_color
        self._fill_color = fill_color
        self._fill_alpha = fill_alpha
        self._surface = "read" if surface_id == "read" else "word"
        self._spell_tray = spell_tray
        self._current_book = current_book
        self._book_titles: dict[str, str] = {}
        self._icon = QSystemTrayIcon(make_tray_icon())
        self._icon.setToolTip("Nothing Here")
        menu = QMenu()
        show_action = menu.addAction("显示卡片")
        hide_action = menu.addAction("隐藏卡片    Ctrl+Alt+S")
        self._book_menu = menu.addMenu("书籍")
        self._card_menu = menu.addMenu("卡片大小")
        self._font_menu = menu.addMenu("字号")
        self._leading_menu = menu.addMenu("行距")
        self._card_actions = _exclusive_levels(self._card_menu, _CARD_LEVELS, read_card, self.read_card_chosen)
        self._font_actions = _exclusive_levels(self._font_menu, _CARD_LEVELS, read_font, self.read_font_chosen)
        self._leading_actions = _exclusive_levels(
            self._leading_menu, _LEADING_LEVELS, read_leading, self.read_leading_chosen
        )
        self._goal_action = menu.addAction(_goal_label(collected, goal))
        self._spell_action = menu.addAction("开始拼写测试")
        self._spell_action.triggered.connect(self.spell_start_chosen.emit)
        self._recycle_menu = menu.addMenu("回收站")
        style_menu = menu.addMenu("风格")
        self._light_action = style_menu.addAction("浅色")
        self._dark_action = style_menu.addAction("黑底白字")
        self._light_action.setCheckable(True)
        self._dark_action.setCheckable(True)
        custom_action = style_menu.addAction("自定义…")
        vocab_menu = menu.addMenu("词库")
        self._group = QActionGroup(menu)
        self._group.setExclusive(True)
        self._source_actions: dict[str, QAction] = {}
        for source in sources:
            action = vocab_menu.addAction(source.display_name)
            action.setCheckable(True)
            action.setData(source.source_id)
            action.setChecked(source.source_id == active_source)
            self._group.addAction(action)
            self._source_actions[source.source_id] = action
            action.triggered.connect(
                lambda checked, source_id=source.source_id: self._on_source(checked, source_id)
            )
        menu.addSeparator()
        surface_menu = menu.addMenu("功能面")
        self._word_action = surface_menu.addAction("单词")
        self._read_action = surface_menu.addAction("阅读")
        self._word_action.setCheckable(True)
        self._read_action.setCheckable(True)
        self._surface_group = QActionGroup(menu)
        self._surface_group.setExclusive(True)
        self._surface_group.addAction(self._word_action)
        self._surface_group.addAction(self._read_action)
        self._exam_action = surface_menu.addAction("考试")
        self._exam_action.setCheckable(True)
        self._exam_action.setToolTip("暂不可用")
        menu.addSeparator()
        self._float_action = menu.addAction("浮在窗口上")
        self._float_action.setCheckable(True)
        self._float_action.setChecked(floating)
        self._float_action.triggered.connect(self.layer_chosen.emit)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        show_action.triggered.connect(self.show_cards.emit)
        hide_action.triggered.connect(self.hide_cards.emit)
        self._goal_action.triggered.connect(self._edit_goal)
        self._light_action.triggered.connect(lambda _checked=False: self._pick_preset("light"))
        self._dark_action.triggered.connect(lambda _checked=False: self._pick_preset("dark"))
        custom_action.triggered.connect(self._pick_custom)
        self._word_action.triggered.connect(self._keep_word_surface)
        self._read_action.triggered.connect(self._choose_read_surface)
        self._exam_action.triggered.connect(self._reject_surface)
        quit_action.triggered.connect(self.quit_requested.emit)
        self._word_only = [
            self._goal_action,
            self._spell_action,
            self._recycle_menu.menuAction(),
            vocab_menu.menuAction(),
        ]
        self._read_only = [
            self._book_menu.menuAction(),
            self._card_menu.menuAction(),
            self._font_menu.menuAction(),
            self._leading_menu.menuAction(),
        ]
        self._icon.setContextMenu(menu)
        self.set_books(books, current_book)
        self.set_style_state(style_preset, text_color, fill_color, fill_alpha)
        self.set_spell_tray_visible(spell_tray)
        self._rebuild_slain()
        self.set_surface(self._surface)
        self._icon.show()

    def set_spell_tray_visible(self, visible: bool) -> None:
        self._spell_tray = visible
        self._spell_action.setVisible(visible and self._surface != "read")

    def show_embed_failed(self) -> None:
        self._icon.showMessage(
            "Nothing Here",
            "无法嵌入桌面层，卡片未显示。",
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )

    def show_import_failed(self, message: str) -> None:
        self._icon.showMessage(
            "Nothing Here",
            message,
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )

    def set_floating(self, floating: bool) -> None:
        self._float_action.blockSignals(True)
        self._float_action.setChecked(floating)
        self._float_action.blockSignals(False)

    def set_active_source(self, source_id: str) -> None:
        action = self._source_actions.get(source_id)
        if action is not None:
            action.setChecked(True)

    def set_daily_progress(self, collected: int, goal: int) -> None:
        self._goal = goal
        self._goal_action.setText(_goal_label(collected, goal))

    def set_slain_items(self, items: Sequence[tuple[str, str]]) -> None:
        self._slain_items = list(items)
        self._rebuild_slain()

    def set_style_state(
        self,
        preset: str,
        text_color: Optional[str],
        fill_color: Optional[str],
        fill_alpha: Optional[int],
    ) -> None:
        self._style_preset = preset
        self._text_color = text_color
        self._fill_color = fill_color
        self._fill_alpha = fill_alpha
        self._light_action.blockSignals(True)
        self._dark_action.blockSignals(True)
        self._light_action.setChecked(preset == "light")
        self._dark_action.setChecked(preset == "dark")
        self._light_action.blockSignals(False)
        self._dark_action.blockSignals(False)

    def set_surface(self, surface_id: str) -> None:
        self._surface = "read" if surface_id == "read" else "word"
        read = self._surface == "read"
        for action in self._word_only:
            action.setVisible(not read)
        for action in self._read_only:
            action.setVisible(read)
        self._word_action.blockSignals(True)
        self._read_action.blockSignals(True)
        self._word_action.setChecked(not read)
        self._read_action.setChecked(read)
        self._exam_action.setChecked(False)
        self._word_action.blockSignals(False)
        self._read_action.blockSignals(False)
        self._spell_action.setVisible((not read) and self._spell_tray)

    def set_books(self, books: Sequence[tuple[str, str]], current: Optional[str]) -> None:
        self._current_book = current
        self._book_titles = {book_id: title for book_id, title in books}
        self._book_menu.clear()
        group = QActionGroup(self._book_menu)
        group.setExclusive(True)
        self._book_group = group
        for book_id, title in books:
            action = self._book_menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(book_id == current)
            group.addAction(action)
            action.triggered.connect(lambda checked, chosen=book_id: self._on_book(checked, chosen))
        self._book_menu.addSeparator()
        import_action = self._book_menu.addAction("导入…")
        import_action.triggered.connect(self.book_import_chosen.emit)
        remove_action = self._book_menu.addAction("移除")
        remove_action.setEnabled(current is not None and current in self._book_titles)
        remove_action.triggered.connect(self._confirm_remove)

    def set_read_levels(self, card: str, font: str, leading: str) -> None:
        _check_only(self._card_actions, card)
        _check_only(self._font_actions, font)
        _check_only(self._leading_actions, leading)

    def _edit_goal(self) -> None:
        value, accepted = QInputDialog.getInt(
            None,
            "每日目标",
            "每天收下的不认识词数",
            self._goal,
            GOAL_MIN,
            GOAL_MAX,
        )
        if accepted:
            self.goal_chosen.emit(value)

    def _on_source(self, checked: bool, source_id: str) -> None:
        if checked:
            self.source_chosen.emit(source_id)

    def _on_book(self, checked: bool, book_id: str) -> None:
        if checked:
            self.book_chosen.emit(book_id)

    def _confirm_remove(self, _checked: bool = False) -> None:
        del _checked
        if self._current_book is None:
            return
        title = self._book_titles.get(self._current_book, "这本书")
        box = QMessageBox()
        box.setWindowTitle("移除")
        box.setText(f"移除「{title}」？")
        box.setInformativeText("应用里的副本和阅读进度会删掉，你原来的文件还在。")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        yes = box.button(QMessageBox.StandardButton.Yes)
        no = box.button(QMessageBox.StandardButton.No)
        if yes is not None:
            yes.setText("移除")
        if no is not None:
            no.setText("取消")
        if box.exec() == int(QMessageBox.StandardButton.Yes):
            self.book_remove_chosen.emit()

    def _pick_preset(self, preset: str) -> None:
        self._light_action.setChecked(preset == "light")
        self._dark_action.setChecked(preset == "dark")
        self.style_preset_chosen.emit(preset)

    def _pick_custom(self, _checked: bool = False) -> None:
        del _checked
        text = QColorDialog.getColor(_text_seed(self._style_preset, self._text_color), None, "文字颜色")
        if not text.isValid():
            return
        # 底面保持透明。fill 只为了让已有的 custom 记录仍能通过校验。
        fill = (self._fill_color or "#000000").upper()
        alpha = 20 if self._fill_alpha is None else max(20, min(230, int(self._fill_alpha)))
        self.style_custom_chosen.emit(text.name().upper(), fill, alpha)

    def _keep_word_surface(self, _checked: bool = False) -> None:
        del _checked
        self._word_action.setChecked(True)
        self.surface_chosen.emit("word")

    def _choose_read_surface(self, _checked: bool = False) -> None:
        del _checked
        self._read_action.setChecked(True)
        self.surface_chosen.emit("read")

    def _reject_surface(self, _checked: bool = False) -> None:
        del _checked
        self._exam_action.setChecked(False)
        self._word_action.setChecked(self._surface != "read")
        self._read_action.setChecked(self._surface == "read")

    def _rebuild_slain(self) -> None:
        self._recycle_menu.clear()
        if not self._slain_items:
            empty = self._recycle_menu.addAction("空")
            empty.triggered.connect(lambda _checked=False: None)
            return
        for key, label in self._slain_items:
            action = self._recycle_menu.addAction(label)
            action.triggered.connect(lambda _checked=False, word=key: self.restore_chosen.emit(word))


def _exclusive_levels(menu: QMenu, levels: Sequence[tuple[str, str]], current: str, signal) -> dict[str, QAction]:
    group = QActionGroup(menu)
    group.setExclusive(True)
    actions: dict[str, QAction] = {}
    for value, label in levels:
        action = menu.addAction(label)
        action.setCheckable(True)
        action.setChecked(value == current)
        group.addAction(action)
        action.triggered.connect(lambda checked, chosen=value: _emit_if_checked(checked, chosen, signal))
        actions[value] = action
    return actions


def _emit_if_checked(checked: bool, value: str, signal) -> None:
    if checked:
        signal.emit(value)


def _check_only(actions: dict[str, QAction], value: str) -> None:
    for key, action in actions.items():
        action.blockSignals(True)
        action.setChecked(key == value)
        action.blockSignals(False)


def _goal_label(collected: int, goal: int) -> str:
    return f"每日目标 {collected}/{goal}"


def _text_seed(preset: str, text_color: Optional[str]) -> QColor:
    if preset == "custom" and text_color:
        return QColor(text_color)
    if preset == "dark":
        return QColor("#F5F5F5")
    return QColor("#1C1C1C")


def make_tray_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(28, 28, 28, 235))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    painter.setPen(QColor("#F5F5F5"))
    font = QFont("Segoe UI")
    font.setPixelSize(28)
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "N")
    painter.end()
    return QIcon(pixmap)
