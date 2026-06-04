"""Orchestration shared by the /report command and the Friday scheduler:
gather the week's entries -> compile -> deliver.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from telegram.ext import Application

from . import db
from .compile import Report, compile_report
from .config import CONFIG
from .deliver import DeliveryResult, deliver_report

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    empty: bool
    num_entries: int = 0
    report: Report | None = None
    delivery: DeliveryResult | None = None


async def generate_and_deliver(app: Application) -> PipelineResult:
    entries = await asyncio.to_thread(db.get_week_entries)
    if not entries:
        return PipelineResult(empty=True)

    report = await compile_report(entries)
    delivery = await deliver_report(app, report)
    return PipelineResult(
        empty=False,
        num_entries=len(entries),
        report=report,
        delivery=delivery,
    )


async def run_scheduled(app: Application) -> None:
    """Friday job: compile, deliver, and nudge the manager on Telegram."""
    log.info("Scheduled weekly compile starting.")
    try:
        result = await generate_and_deliver(app)
    except Exception:  # noqa: BLE001 — never let the scheduler thread die silently
        log.exception("Scheduled compile failed.")
        await _notify_manager(app, "⚠️ The weekly report failed to compile. Check the logs.")
        return

    if CONFIG.manager_chat_id is None:
        log.warning("MANAGER_CHAT_ID not set; cannot send the weekly nudge.")
        return

    if result.empty:
        await _notify_manager(
            app, "🗒️ No notes were logged this week, so I didn't generate a report."
        )
        return

    if result.delivery and result.delivery.method == "gmail":
        await _notify_manager(
            app,
            "📝 Draft ready for review.\n"
            f"{result.report.subject} — open Gmail to review & send.",
        )
    # For the Telegram delivery method the report text was already sent.


async def _notify_manager(app: Application, text: str) -> None:
    if CONFIG.manager_chat_id is None:
        return
    try:
        await app.bot.send_message(chat_id=CONFIG.manager_chat_id, text=text)
    except Exception:  # noqa: BLE001
        log.exception("Failed to send Telegram notification.")
