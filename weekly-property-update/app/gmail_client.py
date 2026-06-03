"""Gmail: load OAuth credentials and create a draft addressed to the owners.

The bot only ever creates DRAFTS — it never sends. You review each draft in
Gmail and hit send yourself. Scope is limited to gmail.compose accordingly.

Credentials resolution order:
  1. GMAIL_TOKEN_JSON env var (the contents of token.json) — best for hosting.
  2. The token file on disk (GMAIL_TOKEN_FILE, default token.json) — local dev.
A refresh token is included by scripts/gmail_auth.py, so expired access tokens
are refreshed automatically.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import CONFIG

# Creating drafts only — no send permission is requested.
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


@dataclass
class DraftResult:
    draft_id: str
    link: str


def _load_credentials() -> Credentials:
    if CONFIG.gmail_token_json:
        info = json.loads(CONFIG.gmail_token_json)
        creds = Credentials.from_authorized_user_info(info, SCOPES)
    elif os.path.exists(CONFIG.gmail_token_file):
        creds = Credentials.from_authorized_user_file(CONFIG.gmail_token_file, SCOPES)
    else:
        raise RuntimeError(
            "No Gmail credentials found. Set GMAIL_TOKEN_JSON or run "
            "scripts/gmail_auth.py to create token.json."
        )

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "Gmail credentials are invalid and cannot be refreshed. "
                "Re-run scripts/gmail_auth.py to re-authorize."
            )
    return creds


def _build_mime(to_addresses: list[str], subject: str, text_body: str, html_body: str) -> str:
    msg = EmailMessage()
    msg["To"] = ", ".join(to_addresses)
    if CONFIG.gmail_sender and CONFIG.gmail_sender != "me":
        msg["From"] = CONFIG.gmail_sender
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def create_draft(to_addresses: list[str], subject: str, text_body: str, html_body: str) -> DraftResult:
    """Create a Gmail draft and return its id + a link to open it. Blocking."""
    creds = _load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    raw = _build_mime(to_addresses, subject, text_body, html_body)
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw}})
        .execute()
    )
    draft_id = draft.get("id", "")
    return DraftResult(
        draft_id=draft_id,
        link="https://mail.google.com/mail/u/0/#drafts",
    )
