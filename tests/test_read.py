from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nothing_here.domain.read import (
    chapter_starts,
    decode_book_bytes,
    disambiguate_title,
    is_chapter_heading,
    page_of,
    turn_chapter,
    turn_page,
)
from nothing_here.storage.db import AppState, Store


class ChapterStartTests(unittest.TestCase):
    def test_marks_zhang_hui_jie_and_hash_headings(self) -> None:
        text = "前言\n第一章\n正文\n第2回\n乙\n第3节 完\n# 尾声\n完"
        # 第一章=3，第2回=10，第3节 完=16，# 尾声=22
        self.assertEqual(chapter_starts(text), (3, 10, 16, 22))

    def test_hash_heading_with_leading_space_uses_the_line_start(self) -> None:
        text = "前言\n  # 标题\n正文"
        self.assertEqual(chapter_starts(text), (3,))

    def test_crlf_line_start(self) -> None:
        text = "前言\r\n第一章\r\n"
        self.assertEqual(chapter_starts(text), (4,))

    def test_book_without_a_heading_is_one_chapter(self) -> None:
        self.assertEqual(chapter_starts("hello\nworld"), (0,))
        self.assertEqual(chapter_starts("第章\n没有间隔"), (0,))
        self.assertFalse(is_chapter_heading("#"))
        self.assertFalse(is_chapter_heading("#   "))
        self.assertTrue(is_chapter_heading("#title"))
        self.assertTrue(is_chapter_heading("## 二级"))
        self.assertTrue(is_chapter_heading("第1章 标题"))

    def test_marker_inside_the_line_counts(self) -> None:
        self.assertEqual(chapter_starts("序言第1章\n后"), (0,))


class PageTurnTests(unittest.TestCase):
    def test_page_turns_land_on_neighbor_starts_and_stop_at_the_ends(self) -> None:
        pages = (0, 10, 20)
        self.assertEqual(turn_page(pages, 15, 1), 20)
        self.assertEqual(turn_page(pages, 15, -1), 0)
        self.assertEqual(turn_page(pages, 0, -1), 0)
        self.assertEqual(turn_page(pages, 20, 1), 20)
        self.assertEqual(turn_page(pages, 10, 1), 20)
        self.assertEqual(turn_page(pages, 10, -1), 0)

    def test_reflow_keeps_the_page_that_contains_the_offset(self) -> None:
        pages = (0, 12, 24)
        self.assertEqual(page_of(pages, 15), 1)
        self.assertEqual(pages[page_of(pages, 15)], 12)
        self.assertEqual(page_of(pages, 11), 0)
        self.assertEqual(page_of(pages, 24), 2)
        self.assertEqual(page_of(pages, 100), 2)


class ChapterTurnTests(unittest.TestCase):
    def test_chapter_turns_stop_on_the_first_and_last_page_of_the_chapter(self) -> None:
        chapters = (0, 100, 200)
        pages = tuple(range(0, 310, 10))
        self.assertEqual(turn_chapter(chapters, pages, 150, -1), 0)
        self.assertEqual(turn_chapter(chapters, pages, 150, 1), 200)
        self.assertEqual(turn_chapter(chapters, pages, 100, -1), 100)
        self.assertEqual(turn_chapter(chapters, pages, 100, 1), 200)
        self.assertEqual(turn_chapter(chapters, pages, 190, 1), 190)
        self.assertEqual(turn_chapter(chapters, pages, 190, -1), 0)
        self.assertEqual(turn_chapter(chapters, pages, 90, 1), 90)
        self.assertEqual(turn_chapter(chapters, pages, 90, -1), 90)
        self.assertEqual(turn_chapter(chapters, pages, 0, -1), 0)
        self.assertEqual(turn_chapter(chapters, pages, 0, 1), 100)

    def test_a_single_chapter_does_not_move(self) -> None:
        pages = (0, 10, 20)
        self.assertEqual(turn_chapter((0,), pages, 15, -1), 15)
        self.assertEqual(turn_chapter((0,), pages, 15, 1), 15)

    def test_text_before_the_first_heading_steps_forward_only(self) -> None:
        chapters = (40, 80)
        pages = (0, 20, 40, 60, 80)
        self.assertEqual(turn_chapter(chapters, pages, 10, 1), 40)
        self.assertEqual(turn_chapter(chapters, pages, 10, -1), 10)


class DecodeTests(unittest.TestCase):
    def test_utf8_gb18030_and_blank(self) -> None:
        self.assertEqual(decode_book_bytes("你好".encode("utf-8")), "你好")
        self.assertEqual(decode_book_bytes("\ufeff你好".encode("utf-8")), "你好")
        self.assertEqual(decode_book_bytes("你好".encode("gb18030")), "你好")
        self.assertIsNone(decode_book_bytes(b" \n\t"))
        self.assertIsNone(decode_book_bytes(b""))
        self.assertIsNone(decode_book_bytes(b"\x80"))

    def test_duplicate_titles_gain_a_number(self) -> None:
        self.assertEqual(disambiguate_title(["笔记"], "别的"), "别的")
        self.assertEqual(disambiguate_title(["笔记"], "笔记"), "笔记 2")
        self.assertEqual(disambiguate_title(["笔记", "笔记 2"], "笔记"), "笔记 3")


class BookStoreTests(unittest.TestCase):
    def test_import_offset_and_remove_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "study.db"
            store = Store(path)
            first = store.add_book("笔记", "第一章\n甲")
            second = store.add_book("笔记", "正文")
            store.set_book_offset(first.book_id, 4)
            store.set_current_book(second.book_id)
            store.save_state(
                AppState(
                    hidden=False,
                    active_source="ielts",
                    word="alpha",
                    origin=(3, 4),
                    surface_id="read",
                    read_origin=(30, 40),
                    read_card="large",
                    read_font="small",
                    read_leading="loose",
                    current_book=second.book_id,
                )
            )
            store.close()

            again = Store(path)
            books = again.list_books()
            state = again.load_state()
            self.assertEqual([book.title for book in books], ["笔记", "笔记 2"])
            self.assertEqual(books[0].offset, 4)
            self.assertEqual(again.read_book_text(first.book_id), "第一章\n甲")
            self.assertNotEqual(books[0].path, books[1].path)
            self.assertTrue(Path(books[0].path).is_file())
            self.assertEqual(state.surface_id, "read")
            self.assertEqual(state.origin, (3, 4))
            self.assertEqual(state.read_origin, (30, 40))
            self.assertEqual(state.read_card, "large")
            self.assertEqual(state.read_font, "small")
            self.assertEqual(state.read_leading, "loose")
            self.assertEqual(state.current_book, second.book_id)
            self.assertEqual(state.word, "alpha")

            again.remove_book(first.book_id)
            self.assertFalse(Path(books[0].path).exists())
            self.assertEqual([book.book_id for book in again.list_books()], [second.book_id])
            again.close()
