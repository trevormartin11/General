"""Telegram bot: dumb capture + the /report, /list, /undo, /help commands."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import db
from .config import CONFIG
from .pipeline import generate_and_deliver
from .util import fmt_local, parse_utc

log = logging.getLogger(__name__)

HELP_TEXT = (
    "Weekly Property Update — quick capture, smart compile.\n\n"
    "Just send me a message any time describing what you did, e.g.:\n"
    '"fixed burst pipe at the Lakehouse, $480 to Trident Plumbing"\n'
    "I store it verbatim with a timestamp — no format needed.\n\n"
    "Commands:\n"
    "/report — compile this week's notes into a report now\n"
    "/list — show this week's logged notes\n"
    "/undo — remove the last note\n"
    "/help — show this message"
)


def _authorized(update: Update) -> bool:
    """Only the configured manager chat may use the bot (once it's set)."""
    if CONFIG.manager_chat_id is None:
        return True  # setup mode: not locked down until you set MANAGER_CHAT_ID
    chat = update.effective_chat
    return chat is not None and chat.id == CONFIG.manager_chat_id


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    intro = (
        "👋 I'm your Weekly Property Update assistant.\n\n"
        f"Your Telegram chat id is: {chat_id}\n"
        "Add it as MANAGER_CHAT_ID in the config so only you can use me "
        "(and so I can nudge you when a draft is ready).\n\n"
    )
    await update.message.reply_text(intro + HELP_TEXT)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(HELP_TEXT)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await update.message.reply_text("Sorry, this bot is private.")
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    entry = await asyncio.to_thread(db.add_entry, text, update.effective_chat.id)
    week = await asyncio.to_thread(db.get_week_entries)
    await update.message.reply_text(
        f"✅ Logged (#{entry.id}). {len(week)} note(s) this week. /report when ready."
    )


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    entries = await asyncio.to_thread(db.get_week_entries)
    if not entries:
        await update.message.reply_text("No notes logged yet this week.")
        return
    lines = ["This week's notes:\n"]
    for i, e in enumerate(entries, start=1):
        lines.append(f"{i}. [{fmt_local(parse_utc(e.ts_utc))}] {e.raw_text}")
    await update.message.reply_text("\n".join(lines))


async def undo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    removed = await asyncio.to_thread(db.undo_last)
    if removed is None:
        await update.message.reply_text("Nothing to undo — no notes stored.")
    else:
        await update.message.reply_text(f"🗑️ Removed: {removed.raw_text}")


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text("🛠️ Compiling this week's report… (a few seconds)")
    try:
        result = await generate_and_deliver(context.application)
    except Exception as exc:  # noqa: BLE001 — surface a friendly error to the user
        log.exception("Manual /report failed.")
        await update.message.reply_text(f"⚠️ Sorry, something went wrong: {exc}")
        return

    if result.empty:
        await update.message.reply_text(
            "🗒️ No notes logged this week yet. Send me a few and try /report again."
        )
        return
    await update.message.reply_text(result.delivery.summary)


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("undo", undo_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
