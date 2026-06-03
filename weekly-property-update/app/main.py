"""Entry point: start the Telegram bot (polling) and the weekly scheduler
in one always-on process. Run with:  python -m app.main
"""

from __future__ import annotations

import asyncio
import logging
import sys

from telegram import Update
from telegram.ext import Application, ApplicationBuilder

from . import db
from .bot import register_handlers
from .config import CONFIG
from .scheduler import build_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("weekly-property-update")


async def _on_startup(app: Application) -> None:
    scheduler = build_scheduler(app)
    scheduler.start()
    app.bot_data["scheduler"] = scheduler
    log.info("Bot started; delivery method = %s", CONFIG.delivery_method)


async def _on_shutdown(app: Application) -> None:
    scheduler = app.bot_data.get("scheduler")
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def main() -> None:
    problems = CONFIG.validate()
    if problems:
        log.error("Configuration problems found:")
        for p in problems:
            log.error("  - %s", p)
        log.error("Fix these in your .env / host environment and restart.")
        sys.exit(1)

    for warning in CONFIG.warnings():
        log.warning(warning)

    db.init_db()

    app = (
        ApplicationBuilder()
        .token(CONFIG.telegram_bot_token)
        .post_init(_on_startup)
        .post_shutdown(_on_shutdown)
        .build()
    )
    register_handlers(app)

    # Python 3.14 no longer auto-creates an event loop for the main thread, but
    # python-telegram-bot v21's run_polling() calls asyncio.get_event_loop().
    # Ensure one exists so the bot runs on 3.12–3.14 as well as 3.11.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
