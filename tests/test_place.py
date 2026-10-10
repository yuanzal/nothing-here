from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from nothing_here.desktop.host import clamp_origin
from nothing_here.storage.db import AppState, DailyRecord, Store


class ClampOriginTests(unittest.TestCase):
    def test_keeps_a_point_inside_the_work_area(self) -> None:
        self.assertEqual(clamp_origin(10, 20, 300, 100, 0, 0, 1536, 824), (10, 20))

    def test_pulls_a_card_back_onto_the_work_area(self) -> None:
        self.assertEqual(clamp_origin(2000, 900, 300, 100, 0, 0, 1536, 824), (1236, 724))
        self.assertEqual(clamp_origin(-40, -10, 300, 100, 0, 0, 1536, 824), (0, 0))


class OriginStoreTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "study.db"
            store = Store(path)
            store.save_state(
                AppState(
                    hidden=False,
                    active_source="ielts",
                    word="alpha",
                    origin=(12, 34),
                    floating=True,
                    daily_goal=8,
                )
            )
            store.close()

            again = Store(path)
            state = again.load_state()
            again.close()
            self.assertEqual(state.word, "alpha")
            self.assertEqual(state.origin, (12, 34))
            self.assertTrue(state.floating)
            self.assertEqual(state.daily_goal, 8)

    def test_upgrades_a_database_that_has_no_origin_columns(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "study.db"
            conn = sqlite3.connect(path)
            conn.execute(
                """
                CREATE TABLE app_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    hidden INTEGER NOT NULL,
                    active_source TEXT NOT NULL,
                    slot1 TEXT,
                    slot2 TEXT,
                    slot3 TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO app_state(id, hidden, active_source, slot1, slot2, slot3) VALUES (1, 0, 'ielts', 'one', NULL, NULL)"
            )
            conn.commit()
            conn.close()

            store = Store(path)
            state = store.load_state()
            store.close()
            self.assertEqual(state.word, "one")
            self.assertIsNone(state.origin)
            self.assertFalse(state.floating)
            self.assertEqual(state.daily_goal, 10)

    def test_migrates_the_first_nonempty_slot(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "study.db"
            conn = sqlite3.connect(path)
            conn.execute(
                """
                CREATE TABLE app_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    hidden INTEGER NOT NULL,
                    active_source TEXT NOT NULL,
                    slot1 TEXT,
                    slot2 TEXT,
                    slot3 TEXT,
                    x1 INTEGER,
                    y1 INTEGER,
                    x2 INTEGER,
                    y2 INTEGER,
                    x3 INTEGER,
                    y3 INTEGER,
                    floating INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                INSERT INTO app_state(
                    id, hidden, active_source, slot1, slot2, slot3, x1, y1, x2, y2, x3, y3, floating
                ) VALUES (1, 0, 'ielts', NULL, 'two', 'three', NULL, NULL, 40, 50, 60, 70, 0)
                """
            )
            conn.commit()
            conn.close()

            store = Store(path)
            state = store.load_state()
            store.close()
            self.assertEqual(state.word, "two")
            self.assertEqual(state.origin, (40, 50))
            self.assertEqual(state.daily_goal, 10)

    def test_daily_record_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "study.db"
            store = Store(path)
            store.save_daily(
                DailyRecord(
                    day="2026-10-10",
                    collected=("apple", "book"),
                    queue=("book", "apple"),
                    phase=1,
                )
            )
            store.close()
            again = Store(path)
            record = again.load_daily()
            again.close()
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.day, "2026-10-10")
            self.assertEqual(record.collected, ("apple", "book"))
            self.assertEqual(record.queue, ("book", "apple"))
            self.assertEqual(record.phase, 1)
