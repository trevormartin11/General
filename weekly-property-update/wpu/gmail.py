"""Create a Gmail draft via IMAP APPEND using an App Password.

This deliberately avoids the Gmail API: no OAuth, no Google Cloud project, no
app verification, and no 7-day token expiry. It needs 2-Step Verification on the
account plus a generated App Password (treated like a password). The draft is
APPENDed to the Drafts mailbox, exactly like one you'd compose yourself.
"""

from __future__ import annotations

import imaplib
import mimetypes
import time
from dataclasses import dataclass
from email.message import EmailMessage

from . import config

_DRAFTS_LINK = "https://mail.google.com/mail/u/0/#drafts"


@dataclass
class DraftResult:
    draft_id: str
    link: str


def _build_message(
    to_addresses: list[str],
    subject: str,
    text_body: str,
    html_body: str,
    attachments: list[tuple[str, bytes]] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = config.GMAIL_ADDRESS
    msg["To"] = ", ".join(to_addresses)
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    for filename, data in attachments or []:
        ctype, _ = mimetypes.guess_type(filename)
        maintype, subtype = ctype.split("/", 1) if ctype else ("application", "octet-stream")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return msg


def _drafts_mailbox(imap: imaplib.IMAP4_SSL) -> str:
    """Find the special-use \\Drafts mailbox; fall back to [Gmail]/Drafts."""
    try:
        typ, data = imap.list()
        if typ == "OK":
            for raw in data:
                line = raw.decode() if isinstance(raw, bytes) else str(raw)
                if "\\Drafts" in line:
                    # The mailbox name is the final quoted token on the line.
                    if '"' in line:
                        return line.split('"')[-2]
                    return line.split()[-1]
    except Exception:  # noqa: BLE001 — fall back to the standard name
        pass
    return "[Gmail]/Drafts"


def create_draft(
    to_addresses: list[str],
    subject: str,
    text_body: str,
    html_body: str,
    attachments: list[tuple[str, bytes]] | None = None,
) -> DraftResult:
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        raise RuntimeError(
            "GMAIL_ADDRESS / GMAIL_APP_PASSWORD are not set. Turn on 2-Step "
            "Verification, generate a Google App Password, and set both env vars."
        )
    msg = _build_message(to_addresses, subject, text_body, html_body, attachments)
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        imap.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        mailbox = _drafts_mailbox(imap)
        typ, _ = imap.append(
            mailbox, "\\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes()
        )
        if typ != "OK":
            raise RuntimeError(f"IMAP APPEND to {mailbox} failed: {typ}")
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass
    return DraftResult(draft_id="", link=_DRAFTS_LINK)
