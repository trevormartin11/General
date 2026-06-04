"""Deliver a finished report, either as a Gmail draft or via Telegram."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from telegram.ext import Application

from .config import CONFIG
from .compile import Report


@dataclass
class DeliveryResult:
    method: str          # "gmail" or "telegram"
    summary: str         # short human-readable status for the /report reply
    draft_link: str = ""


def _chunk(text: str, size: int = 3500) -> list[str]:
    """Split a long message into Telegram-sized chunks on line boundaries."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > size:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks or [text]


async def deliver_report(app: Application, report: Report) -> DeliveryResult:
    if CONFIG.delivery_method == "telegram":
        return await _deliver_telegram(app, report)
    return await _deliver_gmail(app, report)


async def _deliver_gmail(app: Application, report: Report) -> DeliveryResult:
    # The google client is blocking, so run it off the event loop.
    from .gmail_client import create_draft

    result = await asyncio.to_thread(
        create_draft,
        CONFIG.owner_emails,
        report.subject,
        report.markdown,
        report.html,
    )
    recipients = ", ".join(CONFIG.owner_emails)
    summary = (
        f"✅ Gmail draft created — {report.subject}\n"
        f"To: {recipients}\n"
        f"Open your drafts to review & send: {result.link}"
    )
    return DeliveryResult(method="gmail", summary=summary, draft_link=result.link)


async def _deliver_telegram(app: Application, report: Report) -> DeliveryResult:
    if CONFIG.manager_chat_id is None:
        return DeliveryResult(
            method="telegram",
            summary="⚠️ MANAGER_CHAT_ID is not set, so I can't send the report. "
            "Send /start to get your chat id and add it to the config.",
        )
    header = f"📋 {report.subject}\n\n"
    body = header + report.markdown
    for part in _chunk(body):
        await app.bot.send_message(chat_id=CONFIG.manager_chat_id, text=part)
    return DeliveryResult(
        method="telegram",
        summary="✅ Report sent above — copy it into an email to the owners.",
    )
