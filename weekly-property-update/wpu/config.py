"""Configuration from environment variables (set in the Vercel dashboard).

Serverless: no .env loading at runtime — Vercel injects these. For local
testing you can still export them or use `vercel env pull`.
"""

from __future__ import annotations

import os


def _split(value: str | None) -> list[str]:
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


# --- Secrets / auth ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
# Shared secret Telegram echoes back in a header on every webhook call.
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
# Shared secret the GitHub Action sends to authorize the /api/report endpoint.
REPORT_SECRET = os.environ.get("REPORT_SECRET", "").strip()

# --- Claude ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8").strip()
# Default "off" so report generation stays comfortably under Vercel's 60s cap;
# set to "adaptive" if your plan allows longer function durations.
ANTHROPIC_THINKING = os.environ.get("ANTHROPIC_THINKING", "off").strip().lower()
ANTHROPIC_MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4000"))

# --- Supabase (storage) ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

# --- Who the report is from / to ---
MANAGER_CHAT_ID = _int_or_none(os.environ.get("MANAGER_CHAT_ID"))
MANAGER_NAME = os.environ.get("MANAGER_NAME", "Your Name").strip()
OWNERS_GREETING = os.environ.get("OWNERS_GREETING", "").strip()
OWNER_EMAILS = _split(os.environ.get("OWNER_EMAILS"))
PROPERTIES = _split(os.environ.get("PROPERTIES"))

# --- Formatting / delivery ---
TIMEZONE = os.environ.get("TIMEZONE", "America/Phoenix").strip()
DELIVERY_METHOD = os.environ.get("DELIVERY_METHOD", "gmail").strip().lower()
GMAIL_TOKEN_JSON = os.environ.get("GMAIL_TOKEN_JSON") or ""
GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "me").strip()


def owners_label() -> str:
    return f"the {OWNERS_GREETING}" if OWNERS_GREETING else "the owners"
