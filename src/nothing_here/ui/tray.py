from __future__ import annotations

from typing import Optional, Sequence

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QColorDialog, QInputDialog, QMenu, QSystemTrayIcon

from nothing_here.domain.daily import GOAL_MAX, GOAL_MIN
from nothing_here.vocab.protocol import VocabSource


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
    ) -> None:
        super().__init__()
        self._goal = goal
        self._slain_items = list(slain_items)
        self._style_preset = style_preset
        self._text_color = text_color
        self._fill_color = fill_color
        self._fill_alpha = fill_alpha
        self._icon = QSystemTrayIcon(make_tray_icon())
        self._icon.setToolTip("Nothing Here")
        menu = QMenu()
        show_action = menu.addAction("显示卡片")
        hide_action = menu.addAction("隐藏卡片    Ctrl+Alt+S")
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
        surface_menu = menu.addMenu("功能面")
        self._word_action = surface_menu.addAction("单词")
        self._word_action.setCheckable(True)
        self._word_action.setChecked(True)
        self._exam_action = surface_menu.addAction("考试")
        self._novel_action = surface_menu.addAction("小说")
        self._exam_action.setCheckable(True)
        self._novel_action.setCheckable(True)
        self._exam_action.setToolTip("暂不可用")
        self._novel_action.setToolTip("暂不可用")
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
        self._exam_action.triggered.connect(self._reject_surface)
        self._novel_action.triggered.connect(self._reject_surface)
        quit_action.triggered.connect(self.quit_requested.emit)
        self._icon.setContextMenu(menu)
        self.set_style_state(style_preset, text_color, fill_color, fill_alpha)
        self.set_spell_tray_visible(spell_tray)
        self._rebuild_slain()
        self._icon.show()

    def set_spell_tray_visible(self, visible: bool) -> None:
        self._spell_action.setVisible(visible)

    def show_embed_failed(self) -> None:
        self._icon.showMessage(
            "Nothing Here",
            "无法嵌入桌面层，卡片未显示。",
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
        self._word_action.setChecked(surface_id == "word")

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

    def _reject_surface(self, _checked: bool = False) -> None:
        del _checked
        self._exam_action.setChecked(False)
        self._novel_action.setChecked(False)
        self._word_action.setChecked(True)

    def _rebuild_slain(self) -> None:
        self._recycle_menu.clear()
        if not self._slain_items:
            empty = self._recycle_menu.addAction("空")
            empty.triggered.connect(lambda _checked=False: None)
            return
        for key, label in self._slain_items:
            action = self._recycle_menu.addAction(label)
            action.triggered.connect(lambda _checked=False, word=key: self.restore_chosen.emit(word))


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
