from __future__ import annotations

from enum import Enum
from PyQt6.QtCore import QElapsedTimer, QPoint, QPointF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QImage, QMouseEvent, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nothing_here.domain.spell import SpellCell, cells_for
from nothing_here.domain.weight import accuracy_percent
from nothing_here.paths import ui_asset
from nothing_here.ui.style import LIGHT, CardPalette

CARD_WIDTH = 300
MARGIN_RIGHT = 24
MARGIN_TOP = 24
CARD_GAP = 12
PADDING = 16
FINISHED_TEXT = "厉害啦，没有更多单词了"
INVITE_TEXT = "是否开始拼写测试？"
BURN_MS = 400
SINK_PX = 12
CELL_SIZE = 22
CELL_GAP = 4
ROSE_SVG = ui_asset("rose.svg")


class Face(Enum):
    FRONT = "front"
    BACK = "back"


def stats_text(correct: int, reviews: int) -> str:
    percent = accuracy_percent(correct, reviews)
    rate = "—" if percent is None else f"{percent}%"
    return f"正确率 {rate}  背诵 {reviews} 次"


class _Body(QWidget):
    """Content layer. Stays non-native so it does not punch a hole in the transparent card."""

    def __init__(self, owner: "CardWindow") -> None:
        super().__init__(owner)
        self._owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._owner._burning:
            event.accept()
            return
        if self._forward_button(event):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.begin_drag(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._owner._burning:
            event.accept()
            return
        if self._owner._press_global is None and self._forward_button(event):
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._owner.drag_to(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._owner._burning:
            event.accept()
            return
        if self._owner._press_global is None and self._forward_button(event):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.end_drag(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _forward_button(self, event: QMouseEvent) -> bool:
        target = _interactive_at(self, event.position().toPoint())
        if target is None:
            return False
        if isinstance(target, _SpellGrid):
            target.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return True
        if isinstance(target, QPushButton) and not target.isEnabled():
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

    def wheelEvent(self, event) -> None:  # noqa: N802
        pixels = event.pixelDelta().y()
        if pixels == 0:
            pixels = event.angleDelta().y() // 3
        self._owner.scroll_by(-pixels)
        event.accept()


class CardWindow(QWidget):
    recognized = pyqtSignal()
    unknown = pyqtSignal()
    reveal_toggled = pyqtSignal()
    slay_requested = pyqtSignal()
    burn_finished = pyqtSignal()
    moved = pyqtSignal(int, int)
    move_finished = pyqtSignal(int, int)
    layer_requested = pyqtSignal()
    invite_start = pyqtSignal()
    invite_later = pyqtSignal()
    invite_mute = pyqtSignal()
    spell_end = pyqtSignal()
    spell_submitted = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._face = Face.FRONT
        self._origin = (0, 0)
        self._press_global: QPoint | None = None
        self._press_origin = (0, 0)
        self._scroll_offset = 0
        self._palette = LIGHT
        self._fade = 1.0
        self._sink = 0
        self._burning = False
        self._burn_pending = False
        self._accept_focus = False
        self._spell_word = ""
        self._burn_clock = QElapsedTimer()
        self._burn_timer = QTimer(self)
        self._burn_timer.setInterval(16)
        self._burn_timer.timeout.connect(self._on_burn_tick)
        self.apply_layer(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(CARD_WIDTH)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._body = _Body(self)
        layout = QVBoxLayout(self._body)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        layout.setSpacing(8)

        self._done = QLabel(FINISHED_TEXT)
        self._done.setWordWrap(True)
        self._done.setFont(_px_font("Microsoft YaHei", 16))

        self._invite = QLabel(INVITE_TEXT)
        self._invite.setWordWrap(True)
        self._invite.setFont(_px_font("Microsoft YaHei", 16))

        self._word = QLabel()
        self._word.setWordWrap(True)
        self._word.setFont(_px_font("Segoe UI", 22, bold=True))

        self._phonetic = QLabel()
        self._phonetic.setWordWrap(True)
        self._phonetic.setFont(_px_font("Segoe UI", 13))

        self._stats = QLabel()
        self._stats.setWordWrap(True)
        self._stats.setFont(_px_font("Microsoft YaHei", 12))

        self._translation = QLabel()
        self._translation.setWordWrap(True)
        self._translation.setFont(_px_font("Microsoft YaHei", 14))

        self._example = QLabel()
        self._example.setWordWrap(True)
        self._example.setFont(_px_font("Segoe UI", 14))

        self._spell_grid = _SpellGrid(self)
        self._spell_grid.submitted.connect(self.spell_submitted.emit)

        self._reveal = QPushButton("译文")
        self._reveal.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reveal.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reveal.clicked.connect(self.reveal_toggled.emit)

        self._known = QPushButton("认识")
        self._unknown = QPushButton("不认识")
        self._rose = QPushButton()
        self._rose.setToolTip("斩杀")
        self._rose.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rose.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._rose.setFixedSize(36, 36)
        self._rose.setIconSize(QSize(22, 22))
        self._rose.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._known.setCursor(Qt.CursorShape.PointingHandCursor)
        self._unknown.setCursor(Qt.CursorShape.PointingHandCursor)
        self._known.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._unknown.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._known.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._unknown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._known.clicked.connect(self.recognized.emit)
        self._unknown.clicked.connect(self.unknown.emit)
        self._rose.clicked.connect(self.slay_requested.emit)

        self._invite_start = QPushButton("开始")
        self._invite_later = QPushButton("暂不")
        self._invite_mute = QPushButton("今日不再提示")
        for button in (self._invite_start, self._invite_later, self._invite_mute):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._invite_start.clicked.connect(self.invite_start.emit)
        self._invite_later.clicked.connect(self.invite_later.emit)
        self._invite_mute.clicked.connect(self.invite_mute.emit)
        invite_buttons = QHBoxLayout()
        invite_buttons.setContentsMargins(0, 4, 0, 0)
        invite_buttons.setSpacing(8)
        invite_buttons.addWidget(self._invite_start)
        invite_buttons.addWidget(self._invite_later)
        invite_buttons.addWidget(self._invite_mute)
        self._invite_row = QWidget()
        self._invite_row.setLayout(invite_buttons)
        self._invite_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._invite_row.setCursor(Qt.CursorShape.ArrowCursor)

        self._spell_end = QPushButton("结束拼写")
        self._spell_end.setCursor(Qt.CursorShape.PointingHandCursor)
        self._spell_end.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._spell_end.clicked.connect(self.spell_end.emit)

        self._layer = QPushButton("浮在窗口上")
        self._layer.setCursor(Qt.CursorShape.PointingHandCursor)
        self._layer.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._layer.clicked.connect(self.layer_requested.emit)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 4, 0, 0)
        buttons.setSpacing(8)
        buttons.addWidget(self._known)
        buttons.addWidget(self._unknown)
        buttons.addWidget(self._rose)
        self._button_row = QWidget()
        self._button_row.setLayout(buttons)
        self._button_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._button_row.setCursor(Qt.CursorShape.ArrowCursor)

        for label in (
            self._done,
            self._invite,
            self._word,
            self._phonetic,
            self._stats,
            self._translation,
            self._example,
        ):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._done)
        layout.addWidget(self._invite)
        layout.addWidget(self._word)
        layout.addWidget(self._phonetic)
        layout.addWidget(self._stats)
        layout.addWidget(self._translation)
        layout.addWidget(self._spell_grid)
        layout.addWidget(self._reveal)
        layout.addWidget(self._example)
        layout.addWidget(self._button_row)
        layout.addWidget(self._invite_row)
        layout.addWidget(self._spell_end)
        layout.addWidget(self._layer)
        self._done.hide()
        self._invite.hide()
        self._example.hide()
        self._spell_grid.hide()
        self._invite_row.hide()
        self._spell_end.hide()
        self.apply_palette(LIGHT)

    def apply_layer(self, floating: bool) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if not self._accept_focus:
            flags |= Qt.WindowType.WindowDoesNotAcceptFocus
        if floating:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not self._accept_focus)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFocusPolicy(
            Qt.FocusPolicy.ClickFocus if self._accept_focus else Qt.FocusPolicy.NoFocus
        )

    def apply_palette(self, palette: CardPalette) -> None:
        self._palette = palette
        self._paint_palette()

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
        example: str = "",
    ) -> None:
        self._face = face
        self._scroll_offset = 0
        self._accept_focus = False
        self._hide_special_modes()
        show_back = face is Face.BACK
        self._done.hide()
        self._word.setText(word)
        self._word.show()
        self._phonetic.setText(phonetic)
        self._phonetic.setVisible(bool(phonetic))
        self._stats.setText(stats_text(correct, reviews))
        self._stats.show()
        self._reveal.setText("收起" if show_back else "译文")
        self._reveal.show()
        self._translation.setText(translation)
        self._translation.setVisible(show_back)
        sentence = example.strip()
        self._example.setText(sentence)
        self._example.setVisible(show_back and bool(sentence))
        self._button_row.setVisible(show_back)
        self._layer.show()
        self._position_body()
        self.update()

    def show_finished(self) -> None:
        self._scroll_offset = 0
        self._accept_focus = False
        self._hide_special_modes()
        self._done.show()
        self._word.hide()
        self._phonetic.hide()
        self._stats.hide()
        self._reveal.hide()
        self._translation.hide()
        self._example.hide()
        self._button_row.hide()
        self._layer.show()
        self._position_body()
        self.update()

    def show_invite(self) -> None:
        self._scroll_offset = 0
        self._accept_focus = False
        self._done.hide()
        self._word.hide()
        self._phonetic.hide()
        self._stats.hide()
        self._translation.hide()
        self._example.hide()
        self._spell_grid.hide()
        self._reveal.hide()
        self._button_row.hide()
        self._spell_end.hide()
        self._invite.show()
        self._invite_row.show()
        self._layer.show()
        self._position_body()
        self.update()

    def show_spelling(
        self,
        word: str,
        phonetic: str,
        translation: str,
        example: str = "",
        example_open: bool = False,
        filled: str | None = None,
    ) -> None:
        self._scroll_offset = 0
        self._accept_focus = True
        self._spell_word = word
        self._done.hide()
        self._invite.hide()
        self._invite_row.hide()
        self._word.hide()
        self._stats.hide()
        self._button_row.hide()
        self._translation.setText(translation)
        self._translation.show()
        self._phonetic.setText(phonetic)
        self._phonetic.setVisible(bool(phonetic))
        self._spell_grid.show()
        self._spell_grid.set_word(word, filled)
        self._reveal.setText("收起" if example_open else "译文")
        self._reveal.show()
        sentence = example.strip()
        self._example.setText(sentence)
        self._example.setVisible(example_open and bool(sentence))
        self._spell_end.show()
        self._layer.show()
        self._position_body()
        self.update()
        self._spell_grid.grabKeyboard()
        self._spell_grid.setFocus(Qt.FocusReason.OtherFocusReason)

    def clear_spell_letters(self) -> None:
        if self._spell_word:
            self._spell_grid.set_word(self._spell_word, None)

    def _hide_special_modes(self) -> None:
        self._spell_grid.releaseKeyboard()
        self._invite.hide()
        self._invite_row.hide()
        self._spell_grid.hide()
        self._spell_end.hide()

    def play_burn(self) -> None:
        if self._burning:
            return
        self._burning = True
        self._burn_pending = False
        self._fade = 1.0
        self._sink = 0
        self._set_buttons_enabled(False)
        self._burn_clock.start()
        self._burn_timer.start()

    def cancel_burn(self) -> None:
        self._burn_timer.stop()
        self._burn_pending = False
        self._burning = False

    def finish_burn(self) -> None:
        self.cancel_burn()
        self._fade = 1.0
        self._sink = 0
        self._set_buttons_enabled(True)
        self._paint_palette()
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
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.translate(0, self._sink)
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
        painter.setBrush(QColor(0, 0, 0, _scaled(70, self._fade)))
        painter.drawRoundedRect(self.width() - 8, handle_y, 4, handle, 2, 2)

    def _on_burn_tick(self) -> None:
        if not self._burning:
            return
        elapsed = self._burn_clock.elapsed()
        fraction = min(1.0, elapsed / BURN_MS)
        self._fade = 1.0 - fraction
        self._sink = int(round(SINK_PX * fraction))
        self._paint_palette()
        self._position_body()
        self.update()
        if fraction < 1.0:
            return
        self._burn_timer.stop()
        self._burn_pending = True
        QTimer.singleShot(0, self._emit_burn_finished)

    def _emit_burn_finished(self) -> None:
        if not self._burn_pending:
            return
        self._burn_pending = False
        self.burn_finished.emit()

    def _paint_palette(self) -> None:
        palette = self._palette
        fade = self._fade
        self._done.setStyleSheet(_text_style(palette.word, fade))
        self._invite.setStyleSheet(_text_style(palette.word, fade))
        self._word.setStyleSheet(_text_style(palette.word, fade))
        self._phonetic.setStyleSheet(_text_style(palette.phonetic, fade))
        self._stats.setStyleSheet(_text_style(palette.stats, fade))
        self._translation.setStyleSheet(_text_style(palette.translation, fade))
        self._example.setStyleSheet(_text_style(palette.example, fade))
        known = _button_style(palette.known_bg, palette.button_fg, fade)
        self._reveal.setStyleSheet(known)
        self._known.setStyleSheet(known)
        self._unknown.setStyleSheet(_button_style(palette.unknown_bg, palette.button_fg, fade))
        self._layer.setStyleSheet(known)
        self._spell_end.setStyleSheet(known)
        for button in (self._invite_start, self._invite_later, self._invite_mute):
            button.setStyleSheet(known)
        self._spell_grid.apply_palette(palette, fade)
        self._rose.setStyleSheet(_rose_style())
        self._rose.setIcon(_rose_icon(QColor(palette.button_fg)))
        self.update()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in (
            self._reveal,
            self._known,
            self._unknown,
            self._rose,
            self._layer,
            self._invite_start,
            self._invite_later,
            self._invite_mute,
            self._spell_end,
        ):
            button.setEnabled(enabled)

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
        self._body.setGeometry(
            0,
            -self._scroll_offset + self._sink,
            self.width(),
            max(content, self.height()),
        )


def _px_font(family: str, px: int, bold: bool = False) -> QFont:
    font = QFont(family)
    font.setPixelSize(px)
    if bold:
        font.setWeight(QFont.Weight.DemiBold)
    return font


def _interactive_at(origin: QWidget, pos: QPoint) -> QWidget | None:
    widget = origin.childAt(pos)
    while widget is not None and widget is not origin:
        if isinstance(widget, (QPushButton, _SpellGrid)):
            return widget
        widget = widget.parentWidget()
    return None


class _SpellGrid(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._layout.setSpacing(6)
        self._cells: tuple[SpellCell, ...] = ()
        self._labels: list[QLabel] = []
        self._values: list[str] = []
        self._cursor = 0
        self._ink = "#1C1C1C"
        self._border = "rgba(28, 28, 28, 120)"

    def apply_palette(self, palette: CardPalette, fade: float) -> None:
        self._ink = _hex_rgba(palette.word, fade)
        self._border = _tuple_rgba(palette.known_bg, fade, boost=40)
        self._refresh_labels()

    def set_word(self, word: str, filled: str | None = None) -> None:
        self._cells = cells_for(word)
        self._values = []
        index = 0
        for cell in self._cells:
            if cell.fixed:
                continue
            if filled is not None and index < len(filled):
                self._values.append(filled[index])
            else:
                self._values.append("")
            index += 1
        self._cursor = next((i for i, value in enumerate(self._values) if not value), len(self._values))
        self._rebuild()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        text = event.text()
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            if self._cursor > 0:
                self._cursor -= 1
                self._values[self._cursor] = ""
                self._refresh_labels()
            event.accept()
            return
        if len(text) == 1 and text.isalpha():
            if self._cursor < len(self._values):
                self._values[self._cursor] = text
                self._cursor += 1
                self._refresh_labels()
                if self._cursor >= len(self._values) and all(self._values):
                    self.submitted.emit(self._assembled())
            event.accept()
            return
        super().keyPressEvent(event)

    def _assembled(self) -> str:
        letters = list(self._values)
        out: list[str] = []
        letter_i = 0
        for cell in self._cells:
            if cell.fixed:
                out.append(cell.text)
            else:
                out.append(letters[letter_i] if letter_i < len(letters) else "")
                letter_i += 1
        return "".join(out)

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            row = item.widget()
            if row is not None:
                row.deleteLater()
        self._labels = []
        row_layout: QHBoxLayout | None = None
        row_widget: QWidget | None = None
        used = 0
        max_width = CARD_WIDTH - 2 * PADDING
        letter_i = 0
        for cell in self._cells:
            need = CELL_SIZE + CELL_GAP
            if row_layout is None or used + need > max_width:
                row_widget = QWidget(self)
                row_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(CELL_GAP)
                row_layout.addStretch(1)
                self._layout.addWidget(row_widget)
                used = 0
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedSize(CELL_SIZE, CELL_SIZE)
            label.setFont(_px_font("Segoe UI", 14, bold=True))
            if cell.fixed:
                label.setText(cell.text if cell.text != " " else "·")
            else:
                label.setText(self._values[letter_i])
                letter_i += 1
            self._labels.append(label)
            assert row_layout is not None
            row_layout.insertWidget(row_layout.count() - 1, label)
            used += need
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        letter_i = 0
        for index, cell in enumerate(self._cells):
            if index >= len(self._labels):
                break
            label = self._labels[index]
            if cell.fixed:
                shown = cell.text if cell.text != " " else "·"
                label.setText(shown)
                label.setStyleSheet(
                    f"color: {self._ink}; background: transparent; border: none;"
                )
            else:
                value = self._values[letter_i] if letter_i < len(self._values) else ""
                label.setText(value.upper() if value else "")
                active = letter_i == self._cursor
                border = self._border if not active else self._ink
                label.setStyleSheet(
                    f"color: {self._ink}; background: transparent;"
                    f"border: 1px solid {border}; border-radius: 4px;"
                )
                letter_i += 1


def _scaled(alpha: int, fade: float) -> int:
    return max(0, min(255, int(round(alpha * fade))))


def _hex_rgba(color: str, fade: float) -> str:
    value = QColor(color)
    return f"rgba({value.red()}, {value.green()}, {value.blue()}, {_scaled(255, fade)})"


def _tuple_rgba(color: tuple[int, int, int, int], fade: float, boost: int = 0) -> str:
    red, green, blue, alpha = color
    return f"rgba({red}, {green}, {blue}, {_scaled(min(255, alpha + boost), fade)})"


def _text_style(color: str, fade: float) -> str:
    return f"color: {_hex_rgba(color, fade)}; background: transparent;"


def _button_style(background: tuple[int, int, int, int], foreground: str, fade: float) -> str:
    fill = _tuple_rgba(background, fade)
    hover = _tuple_rgba(background, fade, boost=50)
    ink = _hex_rgba(foreground, fade)
    return f"""
        QPushButton {{
            background: {fill};
            color: {ink};
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
            color: {ink};
        }}
    """


def _rose_style() -> str:
    return """
        QPushButton {
            background: transparent;
            border: none;
            padding: 2px;
        }
        QPushButton:hover {
            background: rgba(128, 128, 128, 40);
            border-radius: 6px;
        }
    """


def _rose_icon(color: QColor) -> QIcon:
    size = 22
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(ROSE_SVG))
    painter = QPainter(image)
    if renderer.isValid():
        renderer.render(painter)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(image.rect(), color)
    painter.end()
    return QIcon(QPixmap.fromImage(image))
