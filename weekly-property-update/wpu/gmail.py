"""Gmail draft creation (drafts only — never sends).

Serverless: credentials come solely from the GMAIL_TOKEN_JSON env var (the
contents of token.json produced by scripts/gmail_auth.py). The included refresh
token lets expired access tokens refresh automatically.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from . import config

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


@dataclass
class DraftResult:
    draft_id: str
    link: str


def _load_credentials() -> Credentials:
    if not config.GMAIL_TOKEN_JSON:
        raise RuntimeError(
            "GMAIL_TOKEN_JSON is not set. Run scripts/gmail_auth.py locally and "
            "paste the contents of token.json into the GMAIL_TOKEN_JSON env var."
        )
    creds = Credentials.from_authorized_user_info(
        json.loads(config.GMAIL_TOKEN_JSON), SCOPES
    )
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "Gmail credentials are invalid and cannot be refreshed. "
                "Re-run scripts/gmail_auth.py and update GMAIL_TOKEN_JSON."
            )
    return creds


def _build_mime(to_addresses: list[str], subject: str, text_body: str, html_body: str) -> str:
    msg = EmailMessage()
    msg["To"] = ", ".join(to_addresses)
    if config.GMAIL_SENDER and config.GMAIL_SENDER != "me":
        msg["From"] = config.GMAIL_SENDER
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def create_draft(to_addresses: list[str], subject: str, text_body: str, html_body: str) -> DraftResult:
    creds = _load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    raw = _build_mime(to_addresses, subject, text_body, html_body)
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw}})
        .execute()
    )
    return DraftResult(
        draft_id=draft.get("id", ""),
        link="https://mail.google.com/mail/u/0/#drafts",
    )
