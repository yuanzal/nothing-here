"""薪条：一行今日累计，可拖，不承载功能面。"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QLabel, QWidget

from nothing_here.ui.skins import Skin, skin_for
from nothing_here.ui.style import LIGHT, CardPalette


class WageStrip(QWidget):
    moved = pyqtSignal(int, int)
    move_finished = pyqtSignal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self._origin = (0, 0)
        self._press_global: QPoint | None = None
        self._press_origin = (0, 0)
        self._line = ""
        self._width = 1
        self._height = 1
        self._look = skin_for("plain")
        self._label = QLabel(self)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.apply_palette(LIGHT)
        self.apply_skin(self._look)
        self.apply_layer(False)

    def apply_skin(self, skin: Skin) -> None:
        self._look = skin
        metrics = skin.strip_metrics
        font = QFont("Microsoft YaHei")
        font.setPixelSize(metrics.font_px)
        self._label.setFont(font)
        if self._line:
            self.set_line(self._line)
        self.update()

    def line(self) -> str:
        return self._line

    def set_line(self, text: str) -> None:
        self._line = text
        self._label.setText(text)
        hint = self._label.sizeHint()
        metrics = self._look.strip_metrics
        self._width = max(metrics.min_width, hint.width() + metrics.pad_x * 2)
        self._height = max(metrics.min_height, hint.height() + metrics.pad_y * 2)
        self._label.setGeometry(
            (self._width - hint.width()) // 2,
            (self._height - hint.height()) // 2,
            hint.width(),
            hint.height(),
        )

    def preferred_width(self) -> int:
        return self._width

    def preferred_height(self) -> int:
        return self._height

    def set_screen_origin(self, x: int, y: int) -> None:
        self._origin = (x, y)

    def apply_palette(self, palette: CardPalette) -> None:
        self._palette = palette
        self._label.setStyleSheet(f"color: {palette.word}; background: transparent;")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        self._look.paint_backdrop(painter, self.rect(), self._palette)
        # 极简无痕的底是全透明的，Windows 上点不到。铺一层几乎看不见的底，
        # 让整行文字（含一点内边距）都能拖，并且和贴边用的窗口一样大。
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))

    def apply_layer(self, floating: bool) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if floating:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_origin = self._origin
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press_global is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._press_global
            self.moved.emit(self._press_origin[0] + delta.x(), self._press_origin[1] + delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._press_global is not None:
            self._press_global = None
            self.move_finished.emit(self._origin[0], self._origin[1])
            event.accept()
            return
        super().mouseReleaseEvent(event)
