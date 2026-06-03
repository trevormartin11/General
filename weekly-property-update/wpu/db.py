"""Storage on Supabase (Postgres) via its PostgREST HTTP API.

We use plain httpx + the service-role key rather than the heavy supabase
client, to keep the serverless bundle small. Entries are returned as dicts:
{id, ts_epoch, ts_utc, raw_text, chat_id}.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from . import config
from .timeutil import week_window

_BASE = f"{config.SUPABASE_URL}/rest/v1/entries"
_HEADERS = {
    "apikey": config.SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}
_TIMEOUT = 10.0


def add_entry(raw_text: str, chat_id: int | None = None) -> dict:
    now = datetime.now(timezone.utc)
    row = {
        "ts_epoch": int(now.timestamp()),
        "ts_utc": now.isoformat(),
        "raw_text": raw_text,
        "chat_id": chat_id,
    }
    r = httpx.post(
        _BASE,
        headers={**_HEADERS, "Prefer": "return=representation"},
        json=row,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()[0]


def get_week_entries() -> list[dict]:
    start, _ = week_window()
    start_epoch = int(start.timestamp())
    r = httpx.get(
        f"{_BASE}?select=*&ts_epoch=gte.{start_epoch}&order=id.asc",
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def undo_last() -> dict | None:
    r = httpx.get(
        f"{_BASE}?select=*&order=id.desc&limit=1", headers=_HEADERS, timeout=_TIMEOUT
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return None
    last = rows[0]
    d = httpx.delete(
        f"{_BASE}?id=eq.{last['id']}", headers=_HEADERS, timeout=_TIMEOUT
    )
    d.raise_for_status()
    return last
