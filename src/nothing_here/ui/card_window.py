from __future__ import annotations

from enum import Enum

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
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
BG = QColor(28, 28, 28, 200)
WORD_COLOR = "#F5F5F5"
PHONETIC_COLOR = "#C8C8C8"
STATS_COLOR = "#A3A3A3"
TRANSLATION_COLOR = "#F0F0F0"
KNOWN_BG = "#2F6F4E"
UNKNOWN_BG = "#6F3A3A"
BUTTON_FG = "#F5F5F5"


class Face(Enum):
    FRONT = "front"
    BACK = "back"


def stats_text(correct: int, reviews: int) -> str:
    percent = accuracy_percent(correct, reviews)
    rate = "—" if percent is None else f"{percent}%"
    return f"正确率 {rate}  背诵 {reviews} 次"


class CardWindow(QWidget):
    recognized = pyqtSignal()
    unknown = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._face = Face.FRONT
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(CARD_WIDTH)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            """
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 4px 2px 4px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 60); border-radius: 3px; min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            """
        )

        self._inner = QWidget()
        self._inner.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        inner_layout = QVBoxLayout(self._inner)
        inner_layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        inner_layout.setSpacing(8)

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
        self._known.setStyleSheet(_button_style(KNOWN_BG))
        self._unknown.setStyleSheet(_button_style(UNKNOWN_BG))
        self._known.clicked.connect(self.recognized.emit)
        self._unknown.clicked.connect(self.unknown.emit)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 4, 0, 0)
        buttons.setSpacing(8)
        buttons.addWidget(self._known)
        buttons.addWidget(self._unknown)
        self._button_row = QWidget()
        self._button_row.setLayout(buttons)
        self._button_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        inner_layout.addWidget(self._word)
        inner_layout.addWidget(self._phonetic)
        inner_layout.addWidget(self._stats)
        inner_layout.addWidget(self._translation)
        inner_layout.addWidget(self._button_row)
        inner_layout.addStretch()

        self._scroll.setWidget(self._inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

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
        self._word.setText(word)
        self._phonetic.setText(phonetic)
        self._phonetic.setVisible(bool(phonetic))
        self._stats.setText(stats_text(correct, reviews))
        self._translation.setText(translation)
        show_back = face is Face.BACK
        self._translation.setVisible(show_back)
        self._button_row.setVisible(show_back)
        self._inner.adjustSize()
        self.update()

    def preferred_height(self) -> int:
        self._inner.adjustSize()
        hint = self._inner.sizeHint().height()
        return max(hint, 72)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, RADIUS, RADIUS)
        painter.fillPath(path, BG)


def _px_font(family: str, px: int, bold: bool = False) -> QFont:
    font = QFont(family)
    font.setPixelSize(px)
    if bold:
        font.setWeight(QFont.Weight.DemiBold)
    return font


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
            opacity: 0.92;
        }}
    """
