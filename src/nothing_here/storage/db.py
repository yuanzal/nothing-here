from __future__ import annotations

import json
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
    word: Optional[str]
    origin: Optional[tuple[int, int]] = None
    floating: bool = False
    daily_goal: int = 10


@dataclass(frozen=True)
class DailyRecord:
    day: str
    collected: tuple[str, ...]
    queue: tuple[str, ...]
    phase: int


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
                floating INTEGER NOT NULL DEFAULT 0,
                daily_goal INTEGER NOT NULL DEFAULT 10
            );

            CREATE TABLE IF NOT EXISTS daily_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                day TEXT NOT NULL,
                collected TEXT NOT NULL,
                queue TEXT NOT NULL,
                phase INTEGER NOT NULL
            );
            """
        )
        self._ensure_columns()
        self._conn.commit()

    def _ensure_columns(self) -> None:
        existing = {str(row[1]) for row in self._conn.execute("PRAGMA table_info(app_state)")}
        for name in ("x1", "y1", "x2", "y2", "x3", "y3"):
            if name not in existing:
                self._conn.execute(f"ALTER TABLE app_state ADD COLUMN {name} INTEGER")
        if "floating" not in existing:
            self._conn.execute(
                "ALTER TABLE app_state ADD COLUMN floating INTEGER NOT NULL DEFAULT 0"
            )
        if "daily_goal" not in existing:
            self._conn.execute(
                "ALTER TABLE app_state ADD COLUMN daily_goal INTEGER NOT NULL DEFAULT 10"
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
            SELECT hidden, active_source, slot1, slot2, slot3,
                   x1, y1, x2, y2, x3, y3, floating, daily_goal
            FROM app_state WHERE id = 1
            """
        ).fetchone()
        if row is None:
            return AppState(hidden=False, active_source="ielts", word=None)
        (
            hidden,
            active_source,
            slot1,
            slot2,
            slot3,
            x1,
            y1,
            x2,
            y2,
            x3,
            y3,
            floating,
            daily_goal,
        ) = row
        word, origin = _migrate_current(
            slot1,
            slot2,
            slot3,
            _origin(x1, y1),
            _origin(x2, y2),
            _origin(x3, y3),
        )
        return AppState(
            hidden=bool(hidden),
            active_source=str(active_source),
            word=word,
            origin=origin,
            floating=bool(floating),
            daily_goal=int(daily_goal),
        )

    def save_state(self, state: AppState) -> None:
        x, y = _pair(state.origin)
        self._conn.execute(
            """
            INSERT INTO app_state(
                id, hidden, active_source, slot1, slot2, slot3,
                x1, y1, x2, y2, x3, y3, floating, daily_goal
            )
            VALUES (1, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                hidden = excluded.hidden,
                active_source = excluded.active_source,
                slot1 = excluded.slot1,
                slot2 = NULL,
                slot3 = NULL,
                x1 = excluded.x1,
                y1 = excluded.y1,
                x2 = NULL,
                y2 = NULL,
                x3 = NULL,
                y3 = NULL,
                floating = excluded.floating,
                daily_goal = excluded.daily_goal
            """,
            (
                1 if state.hidden else 0,
                state.active_source,
                state.word,
                x,
                y,
                1 if state.floating else 0,
                state.daily_goal,
            ),
        )
        self._conn.commit()

    def load_daily(self) -> Optional[DailyRecord]:
        row = self._conn.execute(
            "SELECT day, collected, queue, phase FROM daily_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        day, collected, queue, phase = row
        return DailyRecord(
            day=str(day),
            collected=_words(collected),
            queue=_words(queue),
            phase=max(0, min(2, int(phase))),
        )

    def save_daily(self, record: DailyRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO daily_state(id, day, collected, queue, phase)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                day = excluded.day,
                collected = excluded.collected,
                queue = excluded.queue,
                phase = excluded.phase
            """,
            (
                record.day,
                json.dumps(list(record.collected), ensure_ascii=False),
                json.dumps(list(record.queue), ensure_ascii=False),
                record.phase,
            ),
        )
        self._conn.commit()


def _migrate_current(
    slot1: object,
    slot2: object,
    slot3: object,
    origin1: Optional[tuple[int, int]],
    origin2: Optional[tuple[int, int]],
    origin3: Optional[tuple[int, int]],
) -> tuple[Optional[str], Optional[tuple[int, int]]]:
    for slot, origin in ((_slot(slot1), origin1), (_slot(slot2), origin2), (_slot(slot3), origin3)):
        if slot:
            return slot, origin
    return None, None


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


def _words(value: object) -> tuple[str, ...]:
    if not value:
        return ()
    data = json.loads(str(value))
    return tuple(str(item).casefold() for item in data if str(item))
