from __future__ import annotations

from typing import Sequence

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QInputDialog, QMenu, QSystemTrayIcon

from nothing_here.domain.daily import GOAL_MAX, GOAL_MIN
from nothing_here.vocab.protocol import VocabSource


class Tray(QObject):
    show_cards = pyqtSignal()
    hide_cards = pyqtSignal()
    goal_chosen = pyqtSignal(int)
    source_chosen = pyqtSignal(str)
    layer_chosen = pyqtSignal(bool)
    quit_requested = pyqtSignal()

    def __init__(
        self,
        sources: Sequence[VocabSource],
        active_source: str,
        floating: bool,
        collected: int = 0,
        goal: int = 10,
    ) -> None:
        super().__init__()
        self._goal = goal
        self._icon = QSystemTrayIcon(make_tray_icon())
        self._icon.setToolTip("Nothing Here")
        menu = QMenu()
        show_action = menu.addAction("显示卡片")
        hide_action = menu.addAction("隐藏卡片    Ctrl+Alt+S")
        self._goal_action = menu.addAction(_goal_label(collected, goal))
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
        quit_action.triggered.connect(self.quit_requested.emit)
        self._icon.setContextMenu(menu)
        self._icon.show()

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


def _goal_label(collected: int, goal: int) -> str:
    return f"每日目标 {collected}/{goal}"


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
