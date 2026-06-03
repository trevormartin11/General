"""Minimal Telegram Bot API client (just what the webhook needs)."""

from __future__ import annotations

import httpx

from . import config

_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
_LIMIT = 3900  # stay under Telegram's 4096-char message cap


def _chunks(text: str) -> list[str]:
    if len(text) <= _LIMIT:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > _LIMIT and current:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


def send_message(chat_id: int, text: str) -> None:
    for chunk in _chunks(text):
        httpx.post(
            f"{_API}/sendMessage",
            json={"chat_id": chat_id, "text": chunk},
            timeout=15.0,
        )
