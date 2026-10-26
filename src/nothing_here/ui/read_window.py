"""阅读面卡片：正文、四键、空状态。页怎么切由 paginate 算，章规则不在这里。"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nothing_here.domain.read import page_of
from nothing_here.ui.paginate import page_lines, page_starts
from nothing_here.ui.skins import Skin, skin_for
from nothing_here.ui.style import LIGHT, CardPalette

PADDING = 16
EMPTY_TEXT = "导入一本书开始阅读"
READ_CARD_SIZE = {
    "small": (280, 360),
    "medium": (320, 480),
    "large": (400, 640),
}
READ_FONT_PX = {"small": 14, "medium": 16, "large": 18}
READ_LEADING = {"tight": 1.25, "medium": 1.5, "loose": 1.8}


class _Body(QWidget):
    def __init__(self, owner: "ReadWindow") -> None:
        super().__init__(owner)
        self._owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._forward_button(event):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.begin_drag(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._owner._press_global is None and self._forward_button(event):
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._owner.drag_to(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._owner._press_global is None and self._forward_button(event):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.end_drag(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        self._owner.roll(event.angleDelta().y())
        event.accept()

    def _forward_button(self, event: QMouseEvent) -> bool:
        target = _button_at(self, event.position().toPoint())
        if target is None:
            return False
        local = QPointF(target.mapFrom(self, event.position().toPoint()))
        forwarded = QMouseEvent(
            event.type(),
            local,
            event.globalPosition(),
            event.button(),
            event.buttons(),
            event.modifiers(),
        )
        QApplication.sendEvent(target, forwarded)
        event.accept()
        return True


class _Page(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._lines: list[tuple[str, bool]] = []
        self._empty = False
        self._pixel_size = 16
        self._line_h = 24
        self._color = "#1C1C1C"

    def set_lines(
        self,
        lines: list[tuple[str, bool]],
        pixel_size: int,
        line_h: int,
        color: str,
        empty: bool,
    ) -> None:
        self._lines = lines
        self._pixel_size = pixel_size
        self._line_h = max(1, line_h)
        self._color = color
        self._empty = empty
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(self._color))
        if self._empty:
            font = _font(self._pixel_size, bold=False)
            painter.setFont(font)
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                EMPTY_TEXT,
            )
            return
        y = 0
        for text, heading in self._lines:
            font = _font(self._pixel_size, heading)
            painter.setFont(font)
            baseline = y + QFontMetrics(font).ascent()
            painter.drawText(0, baseline, text)
            y += self._line_h


class ReadWindow(QWidget):
    prev_page = pyqtSignal()
    next_page = pyqtSignal()
    prev_chapter = pyqtSignal()
    next_chapter = pyqtSignal()
    moved = pyqtSignal(int, int)
    move_finished = pyqtSignal(int, int)
    layer_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._origin = (0, 0)
        self._press_global: QPoint | None = None
        self._press_origin = (0, 0)
        self._palette = LIGHT
        self._skin: Skin = skin_for("plain")
        self._empty = True
        self._box = READ_CARD_SIZE["medium"]
        self.apply_layer(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(*self._box)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._body = _Body(self)
        layout = QVBoxLayout(self._body)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        layout.setSpacing(8)

        self._page = _Page()
        self._prev_chapter = self._nav_button("<<", self.prev_chapter)
        self._prev = self._nav_button("<", self.prev_page)
        self._next = self._nav_button(">", self.next_page)
        self._next_chapter = self._nav_button(">>", self.next_chapter)
        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(8)
        for button in (self._prev_chapter, self._prev, self._next, self._next_chapter):
            nav.addWidget(button)
            button.installEventFilter(self)
        self._nav = QWidget()
        self._nav.setLayout(nav)
        self._nav.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._nav.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._layer = QPushButton("浮在窗口上")
        self._layer.setCursor(Qt.CursorShape.PointingHandCursor)
        self._layer.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._layer.clicked.connect(self.layer_requested.emit)
        self._layer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._layer.installEventFilter(self)

        layout.addWidget(self._page, 1)
        layout.addWidget(self._nav)
        layout.addWidget(self._layer)
        self._set_nav_enabled(False)
        self.apply_palette(LIGHT)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if isinstance(event, QWheelEvent):
            self.roll(event.angleDelta().y())
            return True
        return super().eventFilter(watched, event)

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

    def apply_palette(self, palette: CardPalette) -> None:
        self._palette = palette
        style = _button_style(palette.known_bg, palette.button_fg)
        for button in (self._prev, self._next, self._prev_chapter, self._next_chapter, self._layer):
            button.setStyleSheet(style)
        self._page.set_lines(
            self._page._lines,
            self._page._pixel_size,
            self._page._line_h,
            palette.word,
            self._empty,
        )

    def apply_skin(self, skin: Skin) -> None:
        self._skin = skin
        self.update()

    def set_layer_floating(self, floating: bool) -> None:
        self._layer.setText("回到桌面" if floating else "浮在窗口上")

    def set_screen_origin(self, x: int, y: int) -> None:
        self._origin = (x, y)

    def set_box(self, width: int, height: int) -> None:
        self._box = (max(1, width), max(1, height))
        self.setFixedSize(*self._box)

    def preferred_width(self) -> int:
        return self._box[0]

    def preferred_height(self) -> int:
        return self._box[1]

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

    def roll(self, delta_y: int) -> None:
        if self._empty or delta_y == 0:
            return
        if delta_y > 0:
            self.prev_page.emit()
        else:
            self.next_page.emit()

    def measure_pages(self, text: str, pixel_size: int, line_ratio: float) -> tuple[int, ...]:
        width, height = self.text_viewport()
        return page_starts(text, width, height, pixel_size, line_ratio)

    def show_empty(self, pixel_size: int, line_ratio: float) -> None:
        self._empty = True
        self._set_nav_enabled(False)
        line_h = max(1, int(round(pixel_size * line_ratio)))
        self._page.set_lines([], pixel_size, line_h, self._palette.word, True)

    def show_page(
        self,
        text: str,
        starts: tuple[int, ...],
        offset: int,
        pixel_size: int,
        line_ratio: float,
    ) -> None:
        self._empty = False
        self._set_nav_enabled(True)
        index = page_of(starts, offset)
        start = starts[index] if starts else 0
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        width, _height = self.text_viewport()
        lines = page_lines(text, start, end, width, pixel_size)
        line_h = max(1, int(round(pixel_size * line_ratio)))
        self._page.set_lines(lines, pixel_size, line_h, self._palette.word, False)

    def text_viewport(self) -> tuple[int, int]:
        self._body.setGeometry(0, 0, max(1, self.width()), max(1, self.height()))
        layout = self._body.layout()
        layout.activate()
        width = self._page.width()
        height = self._page.height()
        if width > 1 and height > 1:
            return width, height
        margins = layout.contentsMargins()
        nav_h = self._nav.sizeHint().height() or 36
        layer_h = self._layer.sizeHint().height() or 32
        return (
            max(1, self.width() - margins.left() - margins.right()),
            max(1, self.height() - margins.top() - margins.bottom() - nav_h - layer_h - layout.spacing() * 2),
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._body.setGeometry(0, 0, self.width(), self.height())

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        self._skin.paint_backdrop(painter, self.rect(), self._palette)

    def _nav_button(self, label: str, signal) -> QPushButton:
        button = QPushButton(label)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(signal.emit)
        return button

    def _set_nav_enabled(self, enabled: bool) -> None:
        for button in (self._prev, self._next, self._prev_chapter, self._next_chapter):
            button.setEnabled(enabled)


def _button_at(origin: QWidget, pos: QPoint) -> QPushButton | None:
    widget = origin.childAt(pos)
    while widget is not None and widget is not origin:
        if isinstance(widget, QPushButton):
            return widget
        widget = widget.parentWidget()
    return None


def _font(pixel_size: int, bold: bool) -> QFont:
    font = QFont("Microsoft YaHei")
    font.setPixelSize(max(1, pixel_size))
    if bold:
        font.setWeight(QFont.Weight.Bold)
    return font


def _button_style(background: tuple[int, int, int, int], foreground: str) -> str:
    red, green, blue, alpha = background
    fill = f"rgba({red}, {green}, {blue}, {alpha})"
    hover_alpha = min(255, alpha + 50)
    hover = f"rgba({red}, {green}, {blue}, {hover_alpha})"
    return f"""
        QPushButton {{
            background: {fill};
            color: {foreground};
            border: none;
            border-radius: 6px;
            padding: 6px 0;
            font-family: 'Microsoft YaHei';
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: {hover};
        }}
        QPushButton:disabled {{
            background: {fill};
            color: {foreground};
        }}
    """
