from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def default_db_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    folder = Path(appdata) / "NothingHere"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "study.db"


@dataclass(frozen=True)
class AppState:
    hidden: bool
    active_source: str
    slots: tuple[Optional[str], Optional[str], Optional[str]]
    origins: tuple[
        Optional[tuple[int, int]],
        Optional[tuple[int, int]],
        Optional[tuple[int, int]],
    ] = (None, None, None)
    floating: bool = False


class Store:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create()

    def close(self) -> None:
        self._conn.close()

    def _create(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS progress (
                word TEXT PRIMARY KEY,
                correct INTEGER NOT NULL,
                reviews INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_state (
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
            );
            """
        )
        self._ensure_origin_columns()
        self._conn.commit()

    def _ensure_origin_columns(self) -> None:
        existing = {str(row[1]) for row in self._conn.execute("PRAGMA table_info(app_state)")}
        for name in ("x1", "y1", "x2", "y2", "x3", "y3"):
            if name not in existing:
                self._conn.execute(f"ALTER TABLE app_state ADD COLUMN {name} INTEGER")
        if "floating" not in existing:
            self._conn.execute(
                "ALTER TABLE app_state ADD COLUMN floating INTEGER NOT NULL DEFAULT 0"
            )

    def get_progress(self, word: str) -> tuple[int, int]:
        row = self._conn.execute(
            "SELECT correct, reviews FROM progress WHERE word = ?",
            (word.casefold(),),
        ).fetchone()
        if row is None:
            return 0, 0
        return int(row[0]), int(row[1])

    def all_progress(self) -> dict[str, tuple[int, int]]:
        rows = self._conn.execute("SELECT word, correct, reviews FROM progress")
        return {str(word): (int(correct), int(reviews)) for word, correct, reviews in rows}

    def record(self, word: str, known: bool) -> tuple[int, int]:
        key = word.casefold()
        correct, reviews = self.get_progress(key)
        reviews += 1
        if known:
            correct += 1
        self._conn.execute(
            """
            INSERT INTO progress(word, correct, reviews)
            VALUES (?, ?, ?)
            ON CONFLICT(word) DO UPDATE SET
                correct = excluded.correct,
                reviews = excluded.reviews
            """,
            (key, correct, reviews),
        )
        self._conn.commit()
        return correct, reviews

    def load_state(self) -> AppState:
        row = self._conn.execute(
            """
            SELECT hidden, active_source, slot1, slot2, slot3, x1, y1, x2, y2, x3, y3, floating
            FROM app_state WHERE id = 1
            """
        ).fetchone()
        if row is None:
            return AppState(hidden=False, active_source="ielts", slots=(None, None, None))
        hidden, active_source, slot1, slot2, slot3, x1, y1, x2, y2, x3, y3, floating = row
        return AppState(
            hidden=bool(hidden),
            active_source=str(active_source),
            slots=(
                _slot(slot1),
                _slot(slot2),
                _slot(slot3),
            ),
            origins=(_origin(x1, y1), _origin(x2, y2), _origin(x3, y3)),
            floating=bool(floating),
        )

    def save_state(self, state: AppState) -> None:
        self._conn.execute(
            """
            INSERT INTO app_state(
                id, hidden, active_source, slot1, slot2, slot3,
                x1, y1, x2, y2, x3, y3, floating
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                hidden = excluded.hidden,
                active_source = excluded.active_source,
                slot1 = excluded.slot1,
                slot2 = excluded.slot2,
                slot3 = excluded.slot3,
                x1 = excluded.x1,
                y1 = excluded.y1,
                x2 = excluded.x2,
                y2 = excluded.y2,
                x3 = excluded.x3,
                y3 = excluded.y3,
                floating = excluded.floating
            """,
            (
                1 if state.hidden else 0,
                state.active_source,
                state.slots[0],
                state.slots[1],
                state.slots[2],
                *_pair(state.origins[0]),
                *_pair(state.origins[1]),
                *_pair(state.origins[2]),
                1 if state.floating else 0,
            ),
        )
        self._conn.commit()


def _slot(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _origin(x: object, y: object) -> Optional[tuple[int, int]]:
    if x is None or y is None:
        return None
    return (int(x), int(y))


def _pair(origin: Optional[tuple[int, int]]) -> tuple[Optional[int], Optional[int]]:
    if origin is None:
        return (None, None)
    return (origin[0], origin[1])
