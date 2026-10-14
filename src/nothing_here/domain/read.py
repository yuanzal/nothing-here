"""阅读面的章起点与翻页、翻章。不读文件，不排版。"""

from __future__ import annotations

import re
from typing import Optional, Sequence

_HASH_HEADING = re.compile(r"^#+\s*\S")
_CHAPTER_MARK = re.compile(r"第.+[章回节]")


def is_chapter_heading(line: str) -> bool:
    """去掉首尾空白后，这一行是不是章起点。

    - `第` + 至少一字符 + `章` / `回` / `节`，行内其余字符允许
    - 以一个或多个 `#` 开头，后面至少还有一个非空白字符
    """
    stripped = line.strip()
    if not stripped:
        return False
    if _HASH_HEADING.match(stripped):
        return True
    return _CHAPTER_MARK.search(stripped) is not None


def chapter_starts(text: str) -> tuple[int, ...]:
    """每个章起点在正文里的下标（该行第一个字符）。没有章起点时全书算一章，返回 `(0,)`。"""
    starts: list[int] = []
    for start, _end, content in _source_lines(text):
        if is_chapter_heading(content):
            starts.append(start)
    if not starts:
        return (0,)
    return tuple(starts)


def page_of(page_starts: Sequence[int], offset: int) -> int:
    """包含该字符偏移的页下标。重排后用新的页起点再选一次。"""
    if not page_starts:
        return 0
    if offset < 0:
        offset = 0
    chosen = 0
    for index, start in enumerate(page_starts):
        if start <= offset:
            chosen = index
        else:
            break
    return chosen


def turn_page(page_starts: Sequence[int], offset: int, step: int) -> int:
    """上一页 / 下一页的新偏移：落到相邻页的起点。首页、末页不改偏移。"""
    if not page_starts or step == 0:
        return offset
    if offset < 0:
        offset = 0
    index = page_of(page_starts, offset)
    target = index + (1 if step > 0 else -1)
    if target < 0 or target >= len(page_starts):
        return offset
    return int(page_starts[target])


def turn_chapter(
    chapter_marks: Sequence[int],
    page_starts: Sequence[int],
    offset: int,
    step: int,
) -> int:
    """上一章 / 下一章的新偏移，落到目标章的起点。

    已经在本章第一页时，上一章不改偏移；已经在本章最后一页时，下一章不改偏移。
    没有上一章或下一章时也不改。全书只有一章时两个方向都不动。
    """
    if step == 0:
        return offset
    chapters = tuple(chapter_marks) if chapter_marks else (0,)
    pages = tuple(page_starts) if page_starts else (0,)
    if offset < 0:
        offset = 0
    index = _index_at_or_before(chapters, offset)
    if index < 0:
        if step > 0:
            return int(chapters[0])
        return offset
    page_index = page_of(pages, offset)
    first_page = page_of(pages, int(chapters[index]))
    if index + 1 < len(chapters):
        last_page = page_of(pages, int(chapters[index + 1]) - 1)
    else:
        last_page = len(pages) - 1
    if step < 0:
        if page_index <= first_page or index == 0:
            return offset
        return int(chapters[index - 1])
    if page_index >= last_page or index + 1 >= len(chapters):
        return offset
    return int(chapters[index + 1])


def decode_book_bytes(data: bytes) -> Optional[str]:
    """UTF-8（含 BOM）失败再试 GB18030。仍失败，或去掉空白后没有字符，则返回 None。"""
    text: Optional[str] = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None or not text.strip():
        return None
    return text


def disambiguate_title(existing: Sequence[str], stem: str) -> str:
    """同名再导入时加序号，避免托盘列表分不清。"""
    taken = set(existing)
    if stem not in taken:
        return stem
    number = 2
    while f"{stem} {number}" in taken:
        number += 1
    return f"{stem} {number}"


def _source_lines(text: str):
    start = 0
    length = len(text)
    while start <= length:
        newline = text.find("\n", start)
        if newline == -1:
            raw = text[start:]
            content = raw[:-1] if raw.endswith("\r") else raw
            yield start, length, content
            return
        raw = text[start:newline]
        content = raw[:-1] if raw.endswith("\r") else raw
        yield start, newline, content
        start = newline + 1
        if start == length:
            return


def _index_at_or_before(marks: Sequence[int], offset: int) -> int:
    chosen = -1
    for index, mark in enumerate(marks):
        if mark <= offset:
            chosen = index
        else:
            break
    return chosen
