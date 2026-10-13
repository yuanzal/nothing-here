from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from nothing_here.domain.spell import MISS_LIMIT


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
    style_preset: str = "light"
    text_color: Optional[str] = None
    fill_color: Optional[str] = None
    fill_alpha: Optional[int] = None
    surface_id: str = "word"
    # 自定义时按钮底色仍跟最近一次浅色或黑底走。没选过黑底则为 light。
    button_preset: str = "light"


@dataclass(frozen=True)
class DailyRecord:
    day: str
    collected: tuple[str, ...]
    queue: tuple[str, ...]
    phase: int
    spell_mode: str = "normal"
    spell_cooldown: int = 0
    spell_mute: bool = False
    spell_tray: bool = False
    spell_misses: int = 0
    spell_example_open: bool = False


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
                daily_goal INTEGER NOT NULL DEFAULT 10,
                style_preset TEXT NOT NULL DEFAULT 'light',
                text_color TEXT,
                fill_color TEXT,
                fill_alpha INTEGER,
                surface_id TEXT NOT NULL DEFAULT 'word',
                button_preset TEXT NOT NULL DEFAULT 'light'
            );

            CREATE TABLE IF NOT EXISTS slain (
                word TEXT PRIMARY KEY,
                slain_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                day TEXT NOT NULL,
                collected TEXT NOT NULL,
                queue TEXT NOT NULL,
                phase INTEGER NOT NULL,
                spell_mode TEXT NOT NULL DEFAULT 'normal',
                spell_cooldown INTEGER NOT NULL DEFAULT 0,
                spell_mute INTEGER NOT NULL DEFAULT 0,
                spell_tray INTEGER NOT NULL DEFAULT 0,
                spell_misses INTEGER NOT NULL DEFAULT 0,
                spell_example_open INTEGER NOT NULL DEFAULT 0
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
        if "style_preset" not in existing:
            self._conn.execute(
                "ALTER TABLE app_state ADD COLUMN style_preset TEXT NOT NULL DEFAULT 'light'"
            )
        if "text_color" not in existing:
            self._conn.execute("ALTER TABLE app_state ADD COLUMN text_color TEXT")
        if "fill_color" not in existing:
            self._conn.execute("ALTER TABLE app_state ADD COLUMN fill_color TEXT")
        if "fill_alpha" not in existing:
            self._conn.execute("ALTER TABLE app_state ADD COLUMN fill_alpha INTEGER")
        if "surface_id" not in existing:
            self._conn.execute(
                "ALTER TABLE app_state ADD COLUMN surface_id TEXT NOT NULL DEFAULT 'word'"
            )
        if "button_preset" not in existing:
            self._conn.execute(
                "ALTER TABLE app_state ADD COLUMN button_preset TEXT NOT NULL DEFAULT 'light'"
            )
        daily_cols = {str(row[1]) for row in self._conn.execute("PRAGMA table_info(daily_state)")}
        daily_defaults = (
            ("spell_mode", "TEXT NOT NULL DEFAULT 'normal'"),
            ("spell_cooldown", "INTEGER NOT NULL DEFAULT 0"),
            ("spell_mute", "INTEGER NOT NULL DEFAULT 0"),
            ("spell_tray", "INTEGER NOT NULL DEFAULT 0"),
            ("spell_misses", "INTEGER NOT NULL DEFAULT 0"),
            ("spell_example_open", "INTEGER NOT NULL DEFAULT 0"),
        )
        for name, decl in daily_defaults:
            if name not in daily_cols:
                self._conn.execute(f"ALTER TABLE daily_state ADD COLUMN {name} {decl}")

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

    def slay_word(self, word: str) -> None:
        key = word.casefold()
        nxt = self._conn.execute("SELECT COALESCE(MAX(slain_at), 0) + 1 FROM slain").fetchone()
        slain_at = int(nxt[0]) if nxt else 1
        self._conn.execute(
            """
            INSERT INTO slain(word, slain_at) VALUES (?, ?)
            ON CONFLICT(word) DO UPDATE SET slain_at = excluded.slain_at
            """,
            (key, slain_at),
        )
        self._conn.commit()

    def restore_word(self, word: str) -> None:
        self._conn.execute("DELETE FROM slain WHERE word = ?", (word.casefold(),))
        self._conn.commit()

    def list_slain(self) -> tuple[tuple[str, int], ...]:
        rows = self._conn.execute(
            "SELECT word, slain_at FROM slain ORDER BY slain_at DESC"
        ).fetchall()
        return tuple((str(word), int(slain_at)) for word, slain_at in rows)

    def slain_words(self) -> tuple[str, ...]:
        return tuple(word for word, _slain_at in self.list_slain())

    def load_state(self) -> AppState:
        row = self._conn.execute(
            """
            SELECT hidden, active_source, slot1, slot2, slot3,
                   x1, y1, x2, y2, x3, y3, floating, daily_goal,
                   style_preset, text_color, fill_color, fill_alpha,
                   surface_id, button_preset
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
            style_preset,
            text_color,
            fill_color,
            fill_alpha,
            surface_id,
            button_preset,
        ) = row
        word, origin = _migrate_current(
            slot1,
            slot2,
            slot3,
            _origin(x1, y1),
            _origin(x2, y2),
            _origin(x3, y3),
        )
        preset, text, fill, alpha, surface, buttons = _style_fields(
            style_preset,
            text_color,
            fill_color,
            fill_alpha,
            surface_id,
            button_preset,
        )
        return AppState(
            hidden=bool(hidden),
            active_source=str(active_source),
            word=word,
            origin=origin,
            floating=bool(floating),
            daily_goal=int(daily_goal),
            style_preset=preset,
            text_color=text,
            fill_color=fill,
            fill_alpha=alpha,
            surface_id=surface,
            button_preset=buttons,
        )

    def save_state(self, state: AppState) -> None:
        x, y = _pair(state.origin)
        self._conn.execute(
            """
            INSERT INTO app_state(
                id, hidden, active_source, slot1, slot2, slot3,
                x1, y1, x2, y2, x3, y3, floating, daily_goal,
                style_preset, text_color, fill_color, fill_alpha,
                surface_id, button_preset
            )
            VALUES (
                1, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, NULL, NULL, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
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
                daily_goal = excluded.daily_goal,
                style_preset = excluded.style_preset,
                text_color = excluded.text_color,
                fill_color = excluded.fill_color,
                fill_alpha = excluded.fill_alpha,
                surface_id = excluded.surface_id,
                button_preset = excluded.button_preset
            """,
            (
                1 if state.hidden else 0,
                state.active_source,
                state.word,
                x,
                y,
                1 if state.floating else 0,
                state.daily_goal,
                *_stored_style(state),
            ),
        )
        self._conn.commit()

    def load_daily(self) -> Optional[DailyRecord]:
        row = self._conn.execute(
            """
            SELECT day, collected, queue, phase,
                   spell_mode, spell_cooldown, spell_mute, spell_tray,
                   spell_misses, spell_example_open
            FROM daily_state WHERE id = 1
            """
        ).fetchone()
        if row is None:
            return None
        (
            day,
            collected,
            queue,
            phase,
            spell_mode,
            spell_cooldown,
            spell_mute,
            spell_tray,
            spell_misses,
            spell_example_open,
        ) = row
        mode = str(spell_mode or "normal")
        if mode not in ("normal", "invite", "spelling"):
            mode = "normal"
        # 邀请不因上次挂着而恢复
        if mode == "invite":
            mode = "normal"
        return DailyRecord(
            day=str(day),
            collected=_words(collected),
            queue=_words(queue),
            phase=max(0, min(2, int(phase))),
            spell_mode=mode,
            spell_cooldown=max(0, min(2, int(spell_cooldown or 0))),
            spell_mute=bool(spell_mute),
            spell_tray=bool(spell_tray),
            spell_misses=max(0, min(MISS_LIMIT, int(spell_misses or 0))),
            spell_example_open=bool(spell_example_open),
        )

    def save_daily(self, record: DailyRecord) -> None:
        mode = record.spell_mode if record.spell_mode in ("normal", "invite", "spelling") else "normal"
        self._conn.execute(
            """
            INSERT INTO daily_state(
                id, day, collected, queue, phase,
                spell_mode, spell_cooldown, spell_mute, spell_tray,
                spell_misses, spell_example_open
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                day = excluded.day,
                collected = excluded.collected,
                queue = excluded.queue,
                phase = excluded.phase,
                spell_mode = excluded.spell_mode,
                spell_cooldown = excluded.spell_cooldown,
                spell_mute = excluded.spell_mute,
                spell_tray = excluded.spell_tray,
                spell_misses = excluded.spell_misses,
                spell_example_open = excluded.spell_example_open
            """,
            (
                record.day,
                json.dumps(list(record.collected), ensure_ascii=False),
                json.dumps(list(record.queue), ensure_ascii=False),
                record.phase,
                mode,
                max(0, min(2, int(record.spell_cooldown))),
                1 if record.spell_mute else 0,
                1 if record.spell_tray else 0,
                max(0, min(MISS_LIMIT, int(record.spell_misses))),
                1 if record.spell_example_open else 0,
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


def _stored_style(
    state: AppState,
) -> tuple[str, Optional[str], Optional[str], Optional[int], str, str]:
    preset = state.style_preset if state.style_preset in ("light", "dark", "custom") else "light"
    if preset in ("light", "dark"):
        return preset, None, None, None, "word", preset
    text = _hex_or_none(state.text_color)
    fill = _hex_or_none(state.fill_color)
    alpha = state.fill_alpha
    button = state.button_preset if state.button_preset in ("light", "dark") else "light"
    if text is None or fill is None or alpha is None:
        return "light", None, None, None, "word", "light"
    return "custom", text, fill, max(20, min(230, int(alpha))), "word", button


def _style_fields(
    style_preset: object,
    text_color: object,
    fill_color: object,
    fill_alpha: object,
    surface_id: object,
    button_preset: object,
) -> tuple[str, Optional[str], Optional[str], Optional[int], str, str]:
    del surface_id
    return _stored_style(
        AppState(
            hidden=False,
            active_source="",
            word=None,
            style_preset=str(style_preset or "light"),
            text_color=_hex_or_none(text_color),
            fill_color=_hex_or_none(fill_color),
            fill_alpha=None if fill_alpha is None else int(fill_alpha),
            surface_id="word",
            button_preset=str(button_preset or "light"),
        )
    )


def _hex_or_none(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) != 7 or not text.startswith("#"):
        return None
    try:
        int(text[1:], 16)
    except ValueError:
        return None
    return text.upper()


def _words(value: object) -> tuple[str, ...]:
    if not value:
        return ()
    data = json.loads(str(value))
    return tuple(str(item).casefold() for item in data if str(item))
