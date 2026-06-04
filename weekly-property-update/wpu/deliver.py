"""Deliver a finished report as a Gmail draft or a Telegram message."""

from __future__ import annotations

from . import config, telegram_api
from .compile import Report


def deliver_report(report: Report) -> str:
    """Returns a short human-readable status string."""
    if config.DELIVERY_METHOD == "telegram":
        if config.MANAGER_CHAT_ID is None:
            return "MANAGER_CHAT_ID is not set; cannot send the report on Telegram."
        telegram_api.send_message(
            config.MANAGER_CHAT_ID, f"📋 {report.subject}\n\n{report.markdown}"
        )
        return "Report sent on Telegram."

    # Gmail draft (imported lazily so the webhook path doesn't load Google libs).
    from . import gmail

    result = gmail.create_draft(
        config.OWNER_EMAILS, report.subject, report.markdown, report.html
    )
    recipients = ", ".join(config.OWNER_EMAILS)
    return (
        f"✅ Gmail draft created — {report.subject}\n"
        f"To: {recipients}\n"
        f"Open your drafts to review & send: {result.link}"
    )
