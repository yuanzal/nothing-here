from __future__ import annotations

from enum import Enum

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nothing_here.domain.weight import accuracy_percent

CARD_WIDTH = 300
MARGIN_RIGHT = 24
MARGIN_TOP = 24
CARD_GAP = 12
PADDING = 16
RADIUS = 12
BG = QColor(255, 255, 255, 88)
WORD_COLOR = "#1C1C1C"
PHONETIC_COLOR = "#3A3A3A"
STATS_COLOR = "#555555"
TRANSLATION_COLOR = "#242424"
KNOWN_BG = "rgba(255, 255, 255, 90)"
UNKNOWN_BG = "rgba(255, 255, 255, 50)"
BUTTON_FG = "#1C1C1C"


class Face(Enum):
    FRONT = "front"
    BACK = "back"


def stats_text(correct: int, reviews: int) -> str:
    percent = accuracy_percent(correct, reviews)
    rate = "—" if percent is None else f"{percent}%"
    return f"正确率 {rate}  背诵 {reviews} 次"


class _Body(QWidget):
    """Content layer. Stays non-native so it does not punch a hole in the card fill."""

    def __init__(self, owner: "CardWindow") -> None:
        super().__init__(owner)
        self._owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.begin_drag(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._owner.drag_to(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.end_drag(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        pixels = event.pixelDelta().y()
        if pixels == 0:
            pixels = event.angleDelta().y() // 3
        self._owner.scroll_by(-pixels)
        event.accept()


class CardWindow(QWidget):
    recognized = pyqtSignal()
    unknown = pyqtSignal()
    moved = pyqtSignal(int, int)
    move_finished = pyqtSignal(int, int)
    layer_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._face = Face.FRONT
        self._origin = (0, 0)
        self._press_global: QPoint | None = None
        self._press_origin = (0, 0)
        self._scroll_offset = 0
        self.apply_layer(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(CARD_WIDTH)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._body = _Body(self)
        layout = QVBoxLayout(self._body)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        layout.setSpacing(8)

        self._word = QLabel()
        self._word.setWordWrap(True)
        self._word.setFont(_px_font("Segoe UI", 22, bold=True))
        self._word.setStyleSheet(f"color: {WORD_COLOR}; background: transparent;")

        self._phonetic = QLabel()
        self._phonetic.setWordWrap(True)
        self._phonetic.setFont(_px_font("Segoe UI", 13))
        self._phonetic.setStyleSheet(f"color: {PHONETIC_COLOR}; background: transparent;")

        self._stats = QLabel()
        self._stats.setWordWrap(True)
        self._stats.setFont(_px_font("Microsoft YaHei", 12))
        self._stats.setStyleSheet(f"color: {STATS_COLOR}; background: transparent;")

        self._translation = QLabel()
        self._translation.setWordWrap(True)
        self._translation.setFont(_px_font("Microsoft YaHei", 14))
        self._translation.setStyleSheet(f"color: {TRANSLATION_COLOR}; background: transparent;")

        self._known = QPushButton("认识")
        self._unknown = QPushButton("不认识")
        self._known.setCursor(Qt.CursorShape.PointingHandCursor)
        self._unknown.setCursor(Qt.CursorShape.PointingHandCursor)
        self._known.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._unknown.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._known.setStyleSheet(_button_style(KNOWN_BG))
        self._unknown.setStyleSheet(_button_style(UNKNOWN_BG))
        self._known.clicked.connect(self.recognized.emit)
        self._unknown.clicked.connect(self.unknown.emit)

        self._layer = QPushButton("浮在窗口上")
        self._layer.setCursor(Qt.CursorShape.PointingHandCursor)
        self._layer.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._layer.setStyleSheet(_layer_style())
        self._layer.clicked.connect(self.layer_requested.emit)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 4, 0, 0)
        buttons.setSpacing(8)
        buttons.addWidget(self._known)
        buttons.addWidget(self._unknown)
        self._button_row = QWidget()
        self._button_row.setLayout(buttons)
        self._button_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._button_row.setCursor(Qt.CursorShape.ArrowCursor)

        for label in (self._word, self._phonetic, self._stats, self._translation):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(label)
        layout.addWidget(self._button_row)
        layout.addWidget(self._layer)

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
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_layer_floating(self, floating: bool) -> None:
        self._layer.setText("回到桌面" if floating else "浮在窗口上")

    def set_screen_origin(self, x: int, y: int) -> None:
        self._origin = (x, y)

    def begin_drag(self, global_pos: QPoint) -> None:
        self._press_global = global_pos
        self._press_origin = self._origin
        self._body.setCursor(Qt.CursorShape.ClosedHandCursor)

    def drag_to(self, global_pos: QPoint) -> None:
        if self._press_global is None:
            return
        delta = global_pos - self._press_global
        self.moved.emit(self._press_origin[0] + delta.x(), self._press_origin[1] + delta.y())

    def end_drag(self, global_pos: QPoint) -> None:
        if self._press_global is None:
            return
        delta = global_pos - self._press_global
        self._press_global = None
        self._body.setCursor(Qt.CursorShape.OpenHandCursor)
        self.move_finished.emit(self._press_origin[0] + delta.x(), self._press_origin[1] + delta.y())

    def scroll_by(self, delta: int) -> None:
        content = self._content_height()
        max_offset = max(0, content - self.height())
        self._scroll_offset = min(max(0, self._scroll_offset + delta), max_offset)
        self._position_body()
        self.update()

    def set_content(
        self,
        word: str,
        phonetic: str,
        translation: str,
        correct: int,
        reviews: int,
        face: Face,
    ) -> None:
        self._face = face
        self._scroll_offset = 0
        self._word.setText(word)
        self._phonetic.setText(phonetic)
        self._phonetic.setVisible(bool(phonetic))
        self._stats.setText(stats_text(correct, reviews))
        self._translation.setText(translation)
        show_back = face is Face.BACK
        self._translation.setVisible(show_back)
        self._button_row.setVisible(show_back)
        self._position_body()
        self.update()

    def preferred_height(self) -> int:
        return max(self._content_height(), 72)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_body()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, RADIUS, RADIUS)
        painter.fillPath(path, BG)
        content = self._body.height()
        overflow = content - self.height()
        if overflow <= 0:
            return
        track = self.height() - 8
        handle = max(24, int(track * self.height() / content))
        handle = min(handle, track)
        travel = max(0, track - handle)
        handle_y = 4 + int(travel * self._scroll_offset / overflow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawRoundedRect(self.width() - 8, handle_y, 4, handle, 2, 2)

    def _content_height(self) -> int:
        width = self.width() or CARD_WIDTH
        self._body.setFixedWidth(width)
        layout = self._body.layout()
        layout.activate()
        if layout.hasHeightForWidth():
            return layout.heightForWidth(width)
        return layout.sizeHint().height()

    def _position_body(self) -> None:
        content = self._content_height()
        max_offset = max(0, content - self.height())
        self._scroll_offset = min(self._scroll_offset, max_offset)
        self._body.setGeometry(0, -self._scroll_offset, self.width(), max(content, self.height()))


def _px_font(family: str, px: int, bold: bool = False) -> QFont:
    font = QFont(family)
    font.setPixelSize(px)
    if bold:
        font.setWeight(QFont.Weight.DemiBold)
    return font


def _layer_style() -> str:
    return """
        QPushButton {
            background: transparent;
            color: #3A3A3A;
            border: none;
            border-radius: 6px;
            padding: 2px 0 0 0;
            font-family: 'Microsoft YaHei';
            font-size: 12px;
            text-align: left;
        }
        QPushButton:hover {
            color: #1C1C1C;
        }
    """


def _button_style(background: str) -> str:
    return f"""
        QPushButton {{
            background: {background};
            color: {BUTTON_FG};
            border: none;
            border-radius: 6px;
            padding: 6px 0;
            font-family: 'Microsoft YaHei';
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: rgba(255, 255, 255, 140);
        }}
    """
