"""Vercel function: Telegram webhook (capture + commands).

Telegram POSTs each update here. We verify the secret-token header, restrict to
the manager's chat, then dispatch. Always returns 200 quickly so Telegram does
not retry (errors are logged to stderr).
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

# Make the shared wpu/ package importable (it sits at the project root).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wpu import config, db, telegram_api  # noqa: E402
from wpu.timeutil import fmt_local, parse_utc  # noqa: E402

HELP_TEXT = (
    "Weekly Property Update — quick capture, smart compile.\n\n"
    "Just send me a message describing what you did, e.g.:\n"
    '"fixed burst pipe at the Lakehouse, $480 to Trident Plumbing"\n'
    "I store it verbatim with a timestamp — no format needed.\n\n"
    "Commands:\n"
    "/report — compile this week's notes into a report now\n"
    "/list — show this week's notes (tap 🗑 to delete any)\n"
    "/undo — remove the last note\n"
    "/help — show this message"
)


def _handle_report(chat_id: int) -> None:
    telegram_api.send_message(chat_id, "🛠️ Compiling this week's report… (a few seconds)")
    from wpu import compile as compile_mod
    from wpu import deliver

    entries = db.get_week_entries()
    if not entries:
        telegram_api.send_message(chat_id, "🗒️ No notes logged this week yet.")
        return
    report = compile_mod.compile_report(entries)
    summary = deliver.deliver_report(report)
    telegram_api.send_message(chat_id, summary)


def handle_callback(callback: dict) -> None:
    """Handle an inline-button tap (the 🗑 Delete buttons from /list)."""
    cb_id = callback.get("id")
    message = callback.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    data = callback.get("data", "")

    if config.MANAGER_CHAT_ID is not None and chat_id != config.MANAGER_CHAT_ID:
        if cb_id:
            telegram_api.answer_callback_query(cb_id, "Not authorized")
        return

    if data.startswith("del:"):
        try:
            db.delete_entry(data.split(":", 1)[1])
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            if cb_id:
                telegram_api.answer_callback_query(cb_id, "Couldn't delete — try again")
            return
        if cb_id:
            telegram_api.answer_callback_query(cb_id, "Removed ✅")
        if chat_id is not None and message_id is not None:
            telegram_api.edit_message_text(
                chat_id,
                message_id,
                f"🗑 Removed — {message.get('text', '')}",
                reply_markup={"inline_keyboard": []},
            )
    elif cb_id:
        telegram_api.answer_callback_query(cb_id)


def handle_update(update: dict) -> None:
    callback = update.get("callback_query")
    if callback:
        handle_callback(callback)
        return

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat_id = msg.get("chat", {}).get("id")
    if chat_id is None:
        return

    # Lock to the manager once MANAGER_CHAT_ID is set; until then, reply with the id.
    if config.MANAGER_CHAT_ID is not None and chat_id != config.MANAGER_CHAT_ID:
        telegram_api.send_message(chat_id, "Sorry, this bot is private.")
        return

    text = (msg.get("text") or "").strip()
    if not text:
        return

    if text.startswith("/start"):
        telegram_api.send_message(
            chat_id,
            "👋 I'm your Weekly Property Update assistant.\n\n"
            f"Your Telegram chat id is: {chat_id}\n"
            "Set it as MANAGER_CHAT_ID so only you can use me.\n\n" + HELP_TEXT,
        )
    elif text.startswith("/help"):
        telegram_api.send_message(chat_id, HELP_TEXT)
    elif text.startswith("/report"):
        _handle_report(chat_id)
    elif text.startswith("/list"):
        entries = db.get_week_entries()
        if not entries:
            telegram_api.send_message(chat_id, "No notes logged yet this week.")
        else:
            telegram_api.send_message(
                chat_id, f"🗒️ This week's notes ({len(entries)}) — tap 🗑 to remove one:"
            )
            for e in entries:
                body = f"[{fmt_local(parse_utc(e['ts_utc']))}] {e['raw_text']}"
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "🗑 Delete", "callback_data": f"del:{e['id']}"}]
                    ]
                }
                telegram_api.send_message(chat_id, body[:3500], reply_markup=keyboard)
    elif text.startswith("/undo"):
        removed = db.undo_last()
        if removed is None:
            telegram_api.send_message(chat_id, "Nothing to undo — no notes stored.")
        else:
            telegram_api.send_message(chat_id, f"🗑️ Removed: {removed['raw_text']}")
    elif text.startswith("/"):
        telegram_api.send_message(chat_id, "Unknown command. Try /help.")
    else:
        entry = db.add_entry(text, chat_id)
        week = db.get_week_entries()
        telegram_api.send_message(
            chat_id,
            f"✅ Logged (#{entry['id']}). {len(week)} note(s) this week. /report when ready.",
        )


class handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (Vercel/BaseHTTPRequestHandler naming)
        secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if config.TELEGRAM_WEBHOOK_SECRET and secret != config.TELEGRAM_WEBHOOK_SECRET:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"unauthorized")
            return

        length = int(self.headers.get("content-length", 0) or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            handle_update(json.loads(body or b"{}"))
        except Exception:  # noqa: BLE001 — log, but still ack so Telegram won't retry-storm
            traceback.print_exc()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):  # noqa: N802 — health check
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Telegram webhook is up.")
