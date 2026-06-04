"""Deliver a finished report as a Gmail draft (with photo attachments) or
via Telegram.
"""

from __future__ import annotations

from . import config, telegram_api
from .compile import Report


def _collect_attachments(entries) -> list[tuple[str, bytes]]:
    """Download this week's photos from Supabase Storage for attaching."""
    from . import storage

    attachments: list[tuple[str, bytes]] = []
    for e in entries or []:
        path = e.get("photo_path")
        if not path:
            continue
        try:
            attachments.append((path.split("/")[-1], storage.download(path)))
        except Exception:  # noqa: BLE001 — skip a photo that won't download
            pass
    return attachments


def deliver_report(report: Report, entries=None) -> str:
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

    attachments = _collect_attachments(entries)
    result = gmail.create_draft(
        config.OWNER_EMAILS, report.subject, report.markdown, report.html, attachments
    )
    recipients = ", ".join(config.OWNER_EMAILS)
    photo_note = (
        f" (+{len(attachments)} photo{'s' if len(attachments) != 1 else ''})"
        if attachments
        else ""
    )
    return (
        f"✅ Gmail draft created — {report.subject}{photo_note}\n"
        f"To: {recipients}\n"
        f"Open your drafts to review & send: {result.link}"
    )
