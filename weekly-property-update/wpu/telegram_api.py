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


def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    chunks = _chunks(text)
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk}
        # Attach an inline keyboard only to the final chunk.
        if reply_markup is not None and i == len(chunks) - 1:
            payload["reply_markup"] = reply_markup
        httpx.post(f"{_API}/sendMessage", json=payload, timeout=15.0)


def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    httpx.post(
        f"{_API}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id, "text": text},
        timeout=10.0,
    )


def edit_message_text(
    chat_id: int, message_id: int, text: str, reply_markup: dict | None = None
) -> None:
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup  # pass {"inline_keyboard": []} to clear
    httpx.post(f"{_API}/editMessageText", json=payload, timeout=15.0)
