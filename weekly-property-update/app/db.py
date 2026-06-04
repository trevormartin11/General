"""SQLite storage for raw capture.

The whole design principle is "dumb capture": every Telegram message is
stored verbatim with a timestamp and nothing else is required.
"""

from __future__ import annotations

import os
import sqlite3
from collections import namedtuple
from contextlib import closing
from datetime import datetime, timezone

from .config import CONFIG
from .util import week_window

Entry = namedtuple("Entry", "id ts_epoch ts_utc raw_text chat_id")


def _connect() -> sqlite3.Connection:
    parent = os.path.dirname(CONFIG.db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(CONFIG.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_epoch  INTEGER NOT NULL,
                ts_utc    TEXT    NOT NULL,
                raw_text  TEXT    NOT NULL,
                chat_id   INTEGER
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_ts ON entries(ts_epoch)")


def _row_to_entry(row: sqlite3.Row) -> Entry:
    return Entry(row["id"], row["ts_epoch"], row["ts_utc"], row["raw_text"], row["chat_id"])


def add_entry(raw_text: str, chat_id: int | None = None) -> Entry:
    now = datetime.now(timezone.utc)
    ts_epoch = int(now.timestamp())
    ts_utc = now.isoformat()
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO entries (ts_epoch, ts_utc, raw_text, chat_id) VALUES (?, ?, ?, ?)",
            (ts_epoch, ts_utc, raw_text, chat_id),
        )
        return Entry(cur.lastrowid, ts_epoch, ts_utc, raw_text, chat_id)


def get_week_entries(reference: datetime | None = None) -> list[Entry]:
    """All entries logged since the start of the current week (Mon 00:00 local)."""
    start, _ = week_window(reference)
    start_epoch = int(start.timestamp())
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM entries WHERE ts_epoch >= ? ORDER BY id ASC",
            (start_epoch,),
        ).fetchall()
    return [_row_to_entry(r) for r in rows]


def undo_last() -> Entry | None:
    """Remove and return the most recently added entry, or None if empty."""
    with closing(_connect()) as conn, conn:
        row = conn.execute("SELECT * FROM entries ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM entries WHERE id = ?", (row["id"],))
        return _row_to_entry(row)
