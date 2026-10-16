from __future__ import annotations

import io
import unittest
import zipfile
from xml.sax.saxutils import escape

from nothing_here.domain.formats import SUPPORTED_SUFFIXES, dialog_filter, extract_book_text
from nothing_here.domain.read import chapter_starts


def _zip(members: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, payload in members.items():
            data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
            archive.writestr(name, data)
    return buf.getvalue()


def _epub(chapters: list[tuple[str, str]], *, linear_no: str = "", nav: str = "") -> bytes:
    manifest = []
    spine = []
    files = {
        "META-INF/container.xml": (
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>'
        )
    }
    for name, html in chapters:
        item_id = name.replace(".", "_")
        files[f"OEBPS/{name}"] = html
        props = ' properties="nav"' if name == nav else ""
        manifest.append(
            f'<item id="{item_id}" href="{name}" media-type="application/xhtml+xml"{props}/>'
        )
        linear = ' linear="no"' if name == linear_no else ""
        spine.append(f'<itemref idref="{item_id}"{linear}/>')
    files["OEBPS/content.opf"] = (
        '<package xmlns="http://www.idpf.org/2007/opf">'
        f"<manifest>{''.join(manifest)}</manifest>"
        f"<spine>{''.join(spine)}</spine></package>"
    )
    return _zip(files)


class ExtractTests(unittest.TestCase):
    def test_dialog_lists_every_supported_suffix(self) -> None:
        shown = dialog_filter()
        for suffix in SUPPORTED_SUFFIXES:
            self.assertIn(f"*{suffix}", shown)
        self.assertIsNone(extract_book_text(".pdf", b"hello"))

    def test_plain_text_and_markdown_keep_the_source(self) -> None:
        self.assertEqual(extract_book_text(".txt", "你好".encode("gb18030")), "你好")
        self.assertEqual(extract_book_text(".MD", b"# \xe7\xac\xac\xe4\xb8\x80\xe7\xab\xa0\n\xe7\x94\xb2"), "# 第一章\n甲")
        self.assertIsNone(extract_book_text(".txt", b" \n\t"))
        self.assertIsNone(extract_book_text(".markdown", b"\x80"))

    def test_html_drops_script_and_marks_headings(self) -> None:
        html = """
        <html><head><title>不要标题</title><style>body{}</style></head>
        <body>
          <h1>第一章</h1>
          <p>甲 <b>乙</b></p>
          <script>alert(1)</script>
          <p>第2节 完</p>
        </body></html>
        """
        text = extract_book_text(".html", html.encode("utf-8"))
        self.assertEqual(text, "# 第一章\n甲 乙\n第2节 完")
        assert text is not None
        self.assertEqual(chapter_starts(text), (0, text.index("第2节")))
        self.assertIsNone(extract_book_text(".htm", "<p>  </p><script>x</script>".encode("utf-8")))

    def test_html_gb18030_and_utf16(self) -> None:
        self.assertEqual(
            extract_book_text(".xhtml", "<p>你好</p>".encode("gb18030")),
            "你好",
        )
        self.assertEqual(
            extract_book_text(".html", "<h2>第二章</h2>".encode("utf-16")),
            "# 第二章",
        )

    def test_epub_follows_spine_and_skips_nav_and_nonlinear(self) -> None:
        blob = _epub(
            [
                ("nav.xhtml", "<html><body><nav><p>目录</p></nav></body></html>"),
                ("cover.xhtml", "<html><body><p>封面</p></body></html>"),
                ("c1.xhtml", "<html><body><h1>第一章</h1><p>甲</p><script>no</script></body></html>"),
                ("c2.xhtml", "<html><body><p>第二章 乙</p></body></html>"),
            ],
            linear_no="cover.xhtml",
            nav="nav.xhtml",
        )
        text = extract_book_text(".epub", blob)
        self.assertEqual(text, "# 第一章\n甲\n第二章 乙")
        assert text is not None
        self.assertEqual(chapter_starts(text), (0, text.index("第二章")))
        self.assertNotIn("目录", text)
        self.assertNotIn("封面", text)

    def test_epub_decodes_href_and_rejects_junk(self) -> None:
        files = {
            "META-INF/container.xml": (
                '<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>'
            ),
            "book.opf": (
                '<package><manifest>'
                '<item id="a" href="text/chap%201.xhtml" media-type="application/xhtml+xml"/>'
                '</manifest><spine><itemref idref="a"/></spine></package>'
            ),
            "text/chap 1.xhtml": "<p>正文</p>",
        }
        self.assertEqual(extract_book_text(".epub", _zip(files)), "正文")
        self.assertIsNone(extract_book_text(".epub", b"not a zip"))
        self.assertIsNone(extract_book_text(".epub", _zip({"META-INF/container.xml": "<x/>"})))

    def test_docx_heading_style_and_skipped_deletion(self) -> None:
        document = """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p>
              <w:pPr><w:pStyle w:val="a1"/></w:pPr>
              <w:r><w:t>第一章</w:t></w:r>
            </w:p>
            <w:p>
              <w:r><w:t>甲</w:t></w:r><w:r><w:t>乙</w:t></w:r>
              <w:del><w:r><w:t>删</w:t></w:r></w:del>
            </w:p>
          </w:body>
        </w:document>
        """
        styles = """<?xml version="1.0" encoding="UTF-8"?>
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:styleId="a1"><w:name w:val="heading 1"/></w:style>
        </w:styles>
        """
        text = extract_book_text(".docx", _zip({"word/document.xml": document, "word/styles.xml": styles}))
        self.assertEqual(text, "# 第一章\n甲乙")
        assert text is not None
        self.assertEqual(chapter_starts(text), (0,))
        self.assertIsNone(extract_book_text(".docx", _zip({"word/styles.xml": styles})))

    def test_docx_outline_level(self) -> None:
        document = """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:r><w:t>序</w:t></w:r></w:p>
            <w:p><w:r><w:t>正文</w:t></w:r></w:p>
          </w:body>
        </w:document>
        """
        text = extract_book_text(".docx", _zip({"word/document.xml": document}))
        self.assertEqual(text, "# 序\n正文")

    def test_odt_headings(self) -> None:
        content = """<?xml version="1.0" encoding="UTF-8"?>
        <office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
            xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
          <office:body><office:text>
            <text:h>第一章</text:h>
            <text:p>甲<text:s text:c="2"/>乙</text:p>
          </office:text></office:body>
        </office:document-content>
        """
        text = extract_book_text(".odt", _zip({"content.xml": content}))
        self.assertEqual(text, "# 第一章\n甲  乙")

    def test_fb2_uses_section_titles_and_skips_description(self) -> None:
        book = f"""<?xml version="1.0" encoding="UTF-8"?>
        <FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
          <description><title-info><book-title>{escape("不要这个书名")}</book-title></title-info></description>
          <body>
            <section>
              <title><p>第一章</p></title>
              <p>甲</p>
              <section><title><p>第二节</p></title><p>乙</p></section>
            </section>
          </body>
          <binary id="img">AAAA</binary>
        </FictionBook>
        """
        text = extract_book_text(".fb2", book.encode("utf-8"))
        self.assertEqual(text, "# 第一章\n甲\n# 第二节\n乙")
        self.assertNotIn("不要这个书名", text or "")
        self.assertIsNone(extract_book_text(".fb2", b"<not-xml"))


if __name__ == "__main__":
    unittest.main()
