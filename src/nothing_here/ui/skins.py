"""卡片和薪条共用的外观。

现在只有「极简无痕」：底透明、无边框，下面再选浅色、深色或自定义文字色。
以后要加可爱、清新这类风格，在本文件写一个类并 register_skin：

- label：托盘里的名字
- color_modes：这一风格自己的颜色项；custom=True 会打开取色器
- palette：给出文字和按钮的颜色
- paint_backdrop：画窗口底。极简无痕只清成全透明。
  要底色就铺圆角矩形，要边框就沿同一矩形描边。画完后合成模式留在 SourceOver。
- strip_metrics：薪条的字号和可拖区域

本模块在导入时注册内置风格。新风格写在这里，或在自己的模块里 register_skin 后由这里导入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

from nothing_here.ui.style import LIGHT, CardPalette, palette_for


@dataclass(frozen=True)
class ColorMode:
    mode_id: str
    label: str
    custom: bool = False


@dataclass(frozen=True)
class StripMetrics:
    font_px: int
    pad_x: int
    pad_y: int
    min_width: int
    min_height: int


class Skin(Protocol):
    skin_id: str
    label: str
    color_modes: tuple[ColorMode, ...]
    strip_metrics: StripMetrics

    def palette(
        self,
        preset: str,
        text_color: Optional[str],
        fill_color: Optional[str],
        fill_alpha: Optional[int],
        button_preset: str,
    ) -> CardPalette: ...

    def paint_backdrop(self, painter: QPainter, rect: QRect, palette: CardPalette) -> None: ...


_SKINS: dict[str, Skin] = {}


def register_skin(skin: Skin) -> None:
    _SKINS[skin.skin_id] = skin


def skins() -> tuple[Skin, ...]:
    return tuple(_SKINS.values())


def skin_for(skin_id: str) -> Skin:
    return _SKINS.get(skin_id) or _SKINS["plain"]


class PlainSkin:
    """极简无痕。不铺底、不描边，只靠文字颜色区分浅色和深色。"""

    skin_id = "plain"
    label = "极简无痕"
    color_modes = (
        ColorMode("light", "浅色"),
        ColorMode("dark", "深色"),
        ColorMode("custom", "自定义…", custom=True),
    )
    strip_metrics = StripMetrics(
        font_px=16,
        pad_x=10,
        pad_y=8,
        min_width=1,
        min_height=1,
    )

    def palette(
        self,
        preset: str,
        text_color: Optional[str],
        fill_color: Optional[str],
        fill_alpha: Optional[int],
        button_preset: str,
    ) -> CardPalette:
        return palette_for(preset, text_color, fill_color, fill_alpha, button_preset)

    def paint_backdrop(self, painter: QPainter, rect: QRect, palette: CardPalette) -> None:
        del palette
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(rect, QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)


def paint_chrome(
    painter: QPainter,
    rect: QRect,
    fill: QColor,
    border: QColor,
    border_width: int,
    radius: float,
) -> None:
    """以后的风格用来铺底和描边。极简无痕不用它。"""
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.fillRect(rect, QColor(0, 0, 0, 0))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    box = QRectF(rect).adjusted(1, 1, -1, -1)
    painter.setPen(Qt.PenStyle.NoPen if border_width <= 0 else QPen(border, border_width))
    painter.setBrush(fill)
    painter.drawRoundedRect(box, radius, radius)


register_skin(PlainSkin())
