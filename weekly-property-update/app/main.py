"""Entry point: start the Telegram bot (polling) and the weekly scheduler
in one always-on process. Run with:  python -m app.main
"""

from __future__ import annotations

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

    db.init_db()

    app = (
        ApplicationBuilder()
        .token(CONFIG.telegram_bot_token)
        .post_init(_on_startup)
        .post_shutdown(_on_shutdown)
        .build()
    )
    register_handlers(app)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
