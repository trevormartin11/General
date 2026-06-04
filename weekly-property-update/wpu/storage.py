"""Supabase Storage helpers (photos), via the Storage REST API + service key.

The service-role key bypasses RLS, so no bucket policies are needed — just keep
the key server-side. Objects are stored under the configured bucket.
"""

from __future__ import annotations

import httpx

from . import config

_AUTH = {
    "apikey": config.SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
}
_OBJECT = f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}"


def upload(path: str, data: bytes, content_type: str = "image/jpeg") -> None:
    r = httpx.post(
        f"{_OBJECT}/{path}",
        headers={**_AUTH, "Content-Type": content_type, "x-upsert": "true"},
        content=data,
        timeout=30.0,
    )
    r.raise_for_status()


def download(path: str) -> bytes:
    r = httpx.get(f"{_OBJECT}/{path}", headers=_AUTH, timeout=30.0)
    r.raise_for_status()
    return r.content


def delete(path: str) -> None:
    httpx.request("DELETE", f"{_OBJECT}/{path}", headers=_AUTH, timeout=15.0)
