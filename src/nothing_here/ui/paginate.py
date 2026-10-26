"""按当前字号、行距和正文区域把一本书切成页。章规则来自 domain。"""

from __future__ import annotations

from PyQt6.QtGui import QFont, QTextLayout, QTextOption

from nothing_here.domain.read import is_chapter_heading


def page_starts(
    text: str,
    width: int,
    height: int,
    pixel_size: int,
    line_ratio: float,
) -> tuple[int, ...]:
    """每一页第一个字符在正文中的下标。空文本只有第 0 页。"""
    if not text:
        return (0,)
    capacity = _line_capacity(height, pixel_size, line_ratio)
    width = max(1, width)
    regular = _font(pixel_size, bold=False)
    bold = _font(pixel_size, bold=True)
    starts = [0]
    cursor = 0
    length = len(text)
    while cursor < length:
        nxt = _fit_end(text, cursor, length, width, capacity, regular, bold)
        if nxt <= cursor:
            nxt = min(length, cursor + 1)
        if nxt >= length:
            break
        starts.append(nxt)
        cursor = nxt
    return tuple(starts)


def page_lines(
    text: str,
    start: int,
    end: int,
    width: int,
    pixel_size: int,
) -> list[tuple[str, bool]]:
    """当前页要画的行：(文字, 是否章标题)。空行是 `("", False)`。"""
    if start < 0:
        start = 0
    end = min(len(text), end)
    if start >= end:
        return []
    width = max(1, width)
    regular = _font(pixel_size, bold=False)
    bold = _font(pixel_size, bold=True)
    lines: list[tuple[str, bool]] = []
    cursor = start
    while cursor < end:
        newline = text.find("\n", cursor)
        if newline == -1 or newline > end:
            raw_end = end
            has_newline = False
        else:
            raw_end = newline
            has_newline = True
        raw = text[cursor:raw_end]
        content = raw[:-1] if raw.endswith("\r") else raw
        heading = _heading_at(text, cursor)
        font = bold if heading else regular
        if content == "":
            lines.append(("", False))
        else:
            for rel_start, rel_end in _layout_paragraph(content, width, font):
                lines.append((content[rel_start:rel_end], heading))
        if not has_newline:
            break
        cursor = raw_end + 1
    return lines


def _line_capacity(height: int, pixel_size: int, line_ratio: float) -> int:
    line_h = max(1, int(round(pixel_size * line_ratio)))
    if height <= 0:
        return 1
    return max(1, height // line_h)


def _fit_end(
    text: str,
    start: int,
    limit: int,
    width: int,
    capacity: int,
    regular: QFont,
    bold: QFont,
) -> int:
    lines_left = capacity
    cursor = start
    while cursor < limit and lines_left > 0:
        if cursor > start and _heading_at(text, cursor):
            return cursor
        newline = text.find("\n", cursor)
        if newline == -1 or newline >= limit:
            raw_end = limit
            has_newline = False
        else:
            raw_end = newline
            has_newline = True
        raw = text[cursor:raw_end]
        content = raw[:-1] if raw.endswith("\r") else raw
        font = bold if _heading_at(text, cursor) else regular
        if content == "":
            lines_left -= 1
            if not has_newline:
                return limit
            cursor = raw_end + 1
            continue
        consumed = 0
        for _rel_start, rel_end in _layout_paragraph(content, width, font):
            if lines_left <= 0:
                break
            consumed = rel_end
            lines_left -= 1
        if consumed < len(content):
            return cursor + consumed
        if not has_newline:
            return limit
        cursor = raw_end + 1
    return cursor


def _heading_at(text: str, index: int) -> bool:
    line_start = text.rfind("\n", 0, index)
    line_start = 0 if line_start == -1 else line_start + 1
    newline = text.find("\n", line_start)
    raw = text[line_start:] if newline == -1 else text[line_start:newline]
    if raw.endswith("\r"):
        raw = raw[:-1]
    return is_chapter_heading(raw)


def _layout_paragraph(paragraph: str, width: int, font: QFont) -> list[tuple[int, int]]:
    layout = QTextLayout(paragraph, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    lines: list[tuple[int, int]] = []
    try:
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            start = line.textStart()
            length = line.textLength()
            if length <= 0:
                length = 1
            end = min(len(paragraph), start + length)
            if lines and end <= lines[-1][1]:
                end = min(len(paragraph), lines[-1][1] + 1)
            lines.append((start, end))
            if end >= len(paragraph):
                break
    finally:
        layout.endLayout()
    if not lines:
        return [(0, len(paragraph))]
    return lines


def _font(pixel_size: int, bold: bool) -> QFont:
    font = QFont("Microsoft YaHei")
    font.setPixelSize(max(1, pixel_size))
    if bold:
        font.setWeight(QFont.Weight.Bold)
    return font
