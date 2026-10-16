"""把导入的字节抽成纯文本。不读路径，不排版，不联网。"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
import zlib
from html.parser import HTMLParser
from typing import Iterable, Optional
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from nothing_here.domain.read import decode_book_bytes

SUPPORTED_SUFFIXES: tuple[str, ...] = (
    ".txt",
    ".md",
    ".markdown",
    ".html",
    ".htm",
    ".xhtml",
    ".epub",
    ".docx",
    ".odt",
    ".fb2",
)

_MAX_MEMBER = 20 * 1024 * 1024
_MAX_TOTAL = 80 * 1024 * 1024

_SKIP_TAGS = {"script", "style", "noscript", "svg", "head", "template", "iframe", "rt", "rp"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = _HEADING_TAGS | {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "caption",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "form",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}
_HTML_MEDIA = {"application/xhtml+xml", "text/html"}
_HTML_EXT = {".xhtml", ".html", ".htm", ".xml"}


def dialog_filter() -> str:
    patterns = " ".join(f"*{suffix}" for suffix in SUPPORTED_SUFFIXES)
    return f"书籍 ({patterns})"


def extract_book_text(suffix: str, data: bytes) -> Optional[str]:
    """按扩展名抽出正文。失败、加密、或去掉空白后没有字符时返回 None。"""
    kind = suffix.lower()
    if kind not in SUPPORTED_SUFFIXES:
        return None
    try:
        if kind in (".txt", ".md", ".markdown"):
            return decode_book_bytes(data)
        if kind in (".html", ".htm", ".xhtml"):
            return _from_html_bytes(data)
        if kind == ".epub":
            return _from_epub(data)
        if kind == ".docx":
            return _from_docx(data)
        if kind == ".odt":
            return _from_odt(data)
        if kind == ".fb2":
            return _from_fb2(data)
    except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile, zlib.error):
        return None
    return None


def _from_html_bytes(data: bytes) -> Optional[str]:
    text = _decode_markup(data)
    if text is None:
        return None
    return _html_to_text(text)


def _html_to_text(text: str) -> Optional[str]:
    parser = _HtmlText()
    parser.feed(text)
    parser.close()
    return _join(parser.parts)


def _from_epub(data: bytes) -> Optional[str]:
    bag = _open_zip(data)
    if bag is None:
        return None
    try:
        opf_name = _opf_name(bag)
        if not opf_name:
            return None
        root = _read_xml(bag, opf_name)
        if root is None:
            return None
        base = posixpath.dirname(opf_name)
        hrefs: dict[str, str] = {}
        for item in _iter_local(root, "item"):
            item_id = _attr(item, "id")
            href = _attr(item, "href")
            if not item_id or not href:
                continue
            if "nav" in _attr(item, "properties").split():
                continue
            if not _is_html_media(_attr(item, "media-type"), href):
                continue
            hrefs[item_id] = href
        spine = [
            item_id
            for ref in _iter_local(root, "itemref")
            if _attr(ref, "linear").lower() != "no"
            for item_id in [_attr(ref, "idref")]
            if item_id
        ]
        if not spine:
            spine = list(hrefs)
        parts: list[str] = []
        for item_id in spine:
            href = hrefs.get(item_id)
            if not href:
                continue
            full = _resolve(base, href)
            blob = bag.read(full) if full else None
            if not blob:
                continue
            chapter = _from_html_bytes(blob)
            if chapter:
                parts.append(chapter)
        return _join(parts)
    finally:
        bag.close()


def _from_docx(data: bytes) -> Optional[str]:
    bag = _open_zip(data)
    if bag is None:
        return None
    try:
        root = _read_xml(bag, "word/document.xml")
        if root is None:
            return None
        styles = _read_xml(bag, "word/styles.xml")
        heading_ids = _docx_heading_styles(styles) if styles is not None else set()
        parts: list[str] = []
        for paragraph in _iter_paragraphs(root):
            heading = _docx_paragraph_is_heading(paragraph, heading_ids)
            text = _docx_paragraph_text(paragraph)
            block = _as_block(text, heading)
            if block:
                parts.append(block)
        return _join(parts)
    finally:
        bag.close()


def _from_odt(data: bytes) -> Optional[str]:
    bag = _open_zip(data)
    if bag is None:
        return None
    try:
        root = _read_xml(bag, "content.xml")
        if root is None:
            return None
        parts: list[str] = []

        def walk(node: ET.Element) -> None:
            for child in list(node):
                name = _local(child.tag)
                if name in ("h", "p"):
                    block = _as_block(_odt_inline(child), name == "h")
                    if block:
                        parts.append(block)
                    continue
                walk(child)

        walk(root)
        return _join(parts)
    finally:
        bag.close()


def _from_fb2(data: bytes) -> Optional[str]:
    root = _parse_xml(data)
    if root is None:
        return None
    parts: list[str] = []
    for child in list(root):
        if _local(child.tag) == "body":
            _walk_fb2(child, "fictionbook", parts)
    return _join(parts)


class _HtmlText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._buf: list[str] = []
        self._heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        self._open(_tag_name(tag))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        name = _tag_name(tag)
        self._open(name)
        self._close(name)

    def handle_endtag(self, tag: str) -> None:
        self._close(_tag_name(tag))

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        self._buf.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _open(self, name: str) -> None:
        if name in _SKIP_TAGS:
            self._skip += 1
            return
        if self._skip or name not in _BLOCK_TAGS:
            return
        self._flush()
        self._heading = name in _HEADING_TAGS

    def _close(self, name: str) -> None:
        if name in _SKIP_TAGS:
            if self._skip:
                self._skip -= 1
            return
        if self._skip or name not in _BLOCK_TAGS:
            return
        self._flush()

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        self._buf.clear()
        heading = self._heading
        self._heading = False
        if not text:
            return
        if heading and not text.startswith("#"):
            text = "# " + text
        self.parts.append(text)


class _ZipBag:
    def __init__(self, data: bytes) -> None:
        self._zf = zipfile.ZipFile(io.BytesIO(data))
        self._left = _MAX_TOTAL
        self._index: dict[str, zipfile.ZipInfo] = {}
        self._names: list[str] = []
        for info in self._zf.infolist():
            name = _norm(info.filename)
            if not name:
                continue
            if name not in self._index:
                self._names.append(name)
            self._index.setdefault(name, info)
            self._index.setdefault(name.lower(), info)

    def names(self) -> tuple[str, ...]:
        return tuple(self._names)

    def read(self, name: str) -> Optional[bytes]:
        key = _norm(name)
        info = self._index.get(key) or self._index.get(key.lower())
        if info is None or self._left <= 0 or info.file_size > _MAX_MEMBER:
            return None
        try:
            with self._zf.open(info, "r") as handle:
                blob = handle.read(min(_MAX_MEMBER, self._left) + 1)
        except (RuntimeError, zipfile.BadZipFile, zlib.error, OSError, ValueError):
            return None
        if len(blob) > _MAX_MEMBER or len(blob) > self._left:
            return None
        self._left -= len(blob)
        return blob

    def close(self) -> None:
        self._zf.close()


def _open_zip(data: bytes) -> Optional[_ZipBag]:
    try:
        return _ZipBag(data)
    except zipfile.BadZipFile:
        return None


def _opf_name(bag: _ZipBag) -> str:
    raw = bag.read("META-INF/container.xml")
    if raw:
        root = _parse_xml(raw)
        if root is not None:
            for el in _iter_local(root, "rootfile"):
                full = _norm(_attr(el, "full-path"))
                if full:
                    return full
    for name in bag.names():
        if name.lower().endswith(".opf"):
            return name
    return ""


def _is_html_media(media: str, href: str) -> bool:
    kind = media.lower().split(";")[0].strip()
    if kind in _HTML_MEDIA:
        return True
    if kind and kind not in ("text/xml", "application/xml"):
        return False
    ext = posixpath.splitext(unquote(href.split("#", 1)[0]))[1].lower()
    return ext in _HTML_EXT


def _docx_heading_styles(root: ET.Element) -> set[str]:
    found: set[str] = set()
    for style in _iter_local(root, "style"):
        style_id = _attr(style, "styleId")
        if not style_id:
            continue
        for child in list(style):
            if _local(child.tag) != "name":
                continue
            if _style_name_is_heading(_attr(child, "val")):
                found.add(style_id)
    return found


def _docx_paragraph_is_heading(paragraph: ET.Element, heading_ids: set[str]) -> bool:
    for child in list(paragraph):
        if _local(child.tag) != "pPr":
            continue
        for prop in list(child):
            name = _local(prop.tag)
            if name == "pStyle":
                val = _attr(prop, "val")
                if val in heading_ids or _style_name_is_heading(val):
                    return True
            if name == "outlineLvl":
                raw = _attr(prop, "val")
                if raw.isdigit() and int(raw) <= 8:
                    return True
    return False


def _style_name_is_heading(value: str) -> bool:
    folded = value.lower()
    return folded.startswith("heading") or folded in ("title", "subtitle") or "标题" in value


def _iter_paragraphs(root: ET.Element) -> Iterable[ET.Element]:
    def walk(node: ET.Element) -> Iterable[ET.Element]:
        for child in list(node):
            if _local(child.tag) == "p":
                yield child
            yield from walk(child)

    return walk(root)


def _docx_paragraph_text(paragraph: ET.Element) -> str:
    chunks: list[str] = []

    def walk(node: ET.Element) -> None:
        for child in list(node):
            name = _local(child.tag)
            if name in ("p", "del"):
                continue
            if name == "t" and child.text:
                chunks.append(child.text)
            elif name == "tab":
                chunks.append(" ")
            elif name in ("br", "cr"):
                chunks.append("\n")
            else:
                walk(child)

    walk(paragraph)
    return "".join(chunks)


def _odt_inline(node: ET.Element) -> str:
    chunks: list[str] = []

    def walk(current: ET.Element) -> None:
        if current.text:
            chunks.append(current.text)
        for child in list(current):
            name = _local(child.tag)
            if name == "s":
                count = _attr(child, "c")
                width = int(count) if count.isdigit() else 1
                chunks.append(" " * min(width, 40))
            elif name == "tab":
                chunks.append(" ")
            elif name == "line-break":
                chunks.append("\n")
            elif name not in ("h", "p"):
                walk(child)
            if child.tail:
                chunks.append(child.tail)

    walk(node)
    return "".join(chunks)


def _walk_fb2(node: ET.Element, parent: str, parts: list[str]) -> None:
    name = _local(node.tag)
    if name in ("binary", "image"):
        return
    if name == "title" and parent == "section":
        block = _as_block(_flat_text(node), True)
        if block:
            parts.append(block)
        return
    if name == "subtitle":
        block = _as_block(_flat_text(node), False)
        if block:
            parts.append(block)
        return
    if name in ("p", "v", "text-author"):
        block = _as_block(_flat_text(node), False)
        if block:
            parts.append(block)
        return
    for child in list(node):
        _walk_fb2(child, name, parts)


def _flat_text(node: ET.Element) -> str:
    return "".join(node.itertext())


def _as_block(text: str, heading: bool) -> str:
    lines: list[str] = []
    for raw in text.splitlines() or [text]:
        line = raw.replace("\xa0", " ").replace("\t", " ").strip()
        if not line:
            continue
        if heading and not line.startswith("#"):
            line = "# " + line
        lines.append(line)
    return "\n".join(lines)


def _join(parts: Iterable[str]) -> Optional[str]:
    text = "\n".join(part for part in parts if part.strip())
    if not text.strip():
        return None
    return text


def _decode_markup(data: bytes) -> Optional[str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            text = data.decode("utf-16")
        except UnicodeError:
            return None
        return text if text.strip() else None
    return decode_book_bytes(data)


def _read_xml(bag: _ZipBag, name: str) -> Optional[ET.Element]:
    blob = bag.read(name)
    if not blob:
        return None
    return _parse_xml(blob)


def _parse_xml(data: bytes) -> Optional[ET.Element]:
    try:
        return ET.fromstring(data)
    except (ET.ParseError, ValueError):
        pass
    text = _decode_markup(data)
    if text is None:
        return None
    try:
        return ET.fromstring(text)
    except (ET.ParseError, ValueError):
        return None


def _resolve(base: str, href: str) -> str:
    href = unquote(href.split("#", 1)[0]).replace("\\", "/")
    if href.startswith("/"):
        return _norm(href)
    return _norm(posixpath.join(base, href)) if href else ""


def _norm(path: str) -> str:
    path = unquote(path.split("#", 1)[0]).replace("\\", "/").strip()
    while path.startswith("./"):
        path = path[2:]
    path = path.lstrip("/")
    path = posixpath.normpath(path) if path else ""
    if path in ("", "."):
        return ""
    if path == ".." or path.startswith("../"):
        return ""
    return path


def _iter_local(root: ET.Element, name: str) -> Iterable[ET.Element]:
    for el in root.iter():
        if _local(el.tag) == name:
            yield el


def _local(tag: str) -> str:
    if tag.startswith("{"):
        return tag.partition("}")[2]
    return tag.rsplit(":", 1)[-1]


def _attr(el: ET.Element, name: str) -> str:
    for key, value in el.attrib.items():
        if _local(key) == name:
            return value
    return ""


def _tag_name(tag: str) -> str:
    return tag.rsplit(":", 1)[-1].lower()
