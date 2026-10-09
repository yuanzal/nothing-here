from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from nothing_here.desktop.host import clamp_origin
from nothing_here.storage.db import AppState, Store


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
                    slots=("alpha", None, "beta"),
                    origins=((12, 34), None, (56, 78)),
                    floating=True,
                )
            )
            store.close()

            again = Store(path)
            state = again.load_state()
            again.close()
            self.assertEqual(state.slots, ("alpha", None, "beta"))
            self.assertEqual(state.origins, ((12, 34), None, (56, 78)))
            self.assertTrue(state.floating)

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
            self.assertEqual(state.slots, ("one", None, None))
            self.assertEqual(state.origins, (None, None, None))
            self.assertFalse(state.floating)
