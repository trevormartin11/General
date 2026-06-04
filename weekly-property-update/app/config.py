"""Configuration, loaded once from the environment / .env file.

Nothing personal is hard-coded — every owner email, name, property
nickname and secret comes from the environment so this repo stays clean.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env from the project root (one level up from this file) if present,
# then fall back to the process environment (how Railway / Render inject vars).
load_dotenv()


def _split(value: str | None) -> list[str]:
    """Parse a comma-separated env var into a clean list of strings."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _int_or_none(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


@dataclass
class Config:
    # --- Secrets / tokens ---
    telegram_bot_token: str
    anthropic_api_key: str

    # --- Claude ---
    anthropic_model: str = "claude-opus-4-8"
    # "adaptive" enables adaptive thinking (recommended on Opus 4.x);
    # set to "off" to disable.
    thinking: str = "adaptive"
    max_tokens: int = 16000

    # --- Who the report is from / to ---
    manager_name: str = "Your Name"
    owners_greeting: str = ""  # e.g. "Hartwell family" -> "the Hartwell family"
    owner_emails: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)

    # --- Telegram ---
    # The chat the bot trusts (also where nudges are sent). Find yours with /start.
    manager_chat_id: int | None = None

    # --- Scheduling (in your timezone) ---
    timezone: str = "America/Phoenix"
    report_day: str = "fri"      # mon, tue, wed, thu, fri, sat, sun
    report_hour: int = 16        # 24h clock
    report_minute: int = 0

    # --- Delivery ---
    delivery_method: str = "gmail"  # "gmail" (draft) or "telegram" (paste)
    gmail_token_json: str | None = None  # contents of token.json (preferred on hosts)
    gmail_token_file: str = "token.json"  # local fallback path
    gmail_sender: str = "me"  # "me" = the authenticated account

    # --- Storage ---
    db_path: str = "data/entries.db"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8").strip(),
            thinking=os.getenv("ANTHROPIC_THINKING", "adaptive").strip().lower(),
            max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "16000")),
            manager_name=os.getenv("MANAGER_NAME", "Your Name").strip(),
            owners_greeting=os.getenv("OWNERS_GREETING", "").strip(),
            owner_emails=_split(os.getenv("OWNER_EMAILS")),
            properties=_split(os.getenv("PROPERTIES")),
            manager_chat_id=_int_or_none(os.getenv("MANAGER_CHAT_ID")),
            timezone=os.getenv("TIMEZONE", "America/Phoenix").strip(),
            report_day=os.getenv("REPORT_DAY", "fri").strip().lower(),
            report_hour=int(os.getenv("REPORT_HOUR", "16")),
            report_minute=int(os.getenv("REPORT_MINUTE", "0")),
            delivery_method=os.getenv("DELIVERY_METHOD", "gmail").strip().lower(),
            gmail_token_json=os.getenv("GMAIL_TOKEN_JSON") or None,
            gmail_token_file=os.getenv("GMAIL_TOKEN_FILE", "token.json").strip(),
            gmail_sender=os.getenv("GMAIL_SENDER", "me").strip(),
            db_path=os.getenv("DB_PATH", "data/entries.db").strip(),
        )

    def validate(self) -> list[str]:
        """Fatal problems that prevent the bot from starting at all.

        Only what *capture* needs. Report-time requirements (Anthropic key,
        Gmail auth, recipients) are surfaced as warnings instead, and enforced
        with a clear message when a report is actually generated — so you can
        start logging notes before finishing the rest of the setup.
        """
        problems: list[str] = []
        if not self.telegram_bot_token:
            problems.append("TELEGRAM_BOT_TOKEN is missing (create one via @BotFather).")
        if self.delivery_method not in ("gmail", "telegram"):
            problems.append("DELIVERY_METHOD must be 'gmail' or 'telegram'.")
        return problems

    def warnings(self) -> list[str]:
        """Non-fatal: capture works, but these block /report until fixed."""
        warns: list[str] = []
        if not self.anthropic_api_key:
            warns.append(
                "ANTHROPIC_API_KEY is not set — capture works, but /report and the "
                "weekly compile will fail until you add it."
            )
        if self.delivery_method == "gmail":
            if not self.owner_emails:
                warns.append("OWNER_EMAILS is empty — the Gmail draft would have no recipients.")
            if not (self.gmail_token_json or os.path.exists(self.gmail_token_file)):
                warns.append(
                    "Gmail is not authorized yet — run scripts/gmail_auth.py (or set "
                    "GMAIL_TOKEN_JSON) before using /report. Capture still works."
                )
        if self.manager_chat_id is None:
            warns.append(
                "MANAGER_CHAT_ID is not set — the bot will respond to anyone until you "
                "set it. Send the bot /start to get your chat id."
            )
        return warns

    @property
    def owners_label(self) -> str:
        """How to address the owners in the report greeting."""
        return f"the {self.owners_greeting}" if self.owners_greeting else "the owners"


CONFIG = Config.from_env()
