#!/usr/bin/env python3
"""Point your Telegram bot at the Vercel webhook (run once, locally).

Usage (env vars or positional args):
    TELEGRAM_BOT_TOKEN=... \\
    WEBHOOK_URL=https://<your-project>.vercel.app/api/telegram \\
    TELEGRAM_WEBHOOK_SECRET=... \\
    python scripts/set_webhook.py

The secret must match the TELEGRAM_WEBHOOK_SECRET you set in Vercel — Telegram
sends it back in a header on every call so the function can verify it.

Note: webhook mode and the Mac polling bot are mutually exclusive. Setting a
webhook here will make the polling bot fail with a 409; conversely, restarting
the polling bot deletes the webhook. Use one or the other.
"""

import json
import os
import sys
import urllib.parse
import urllib.request


def _arg(n: int) -> str:
    return sys.argv[n] if len(sys.argv) > n else ""


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or _arg(1)
    url = os.environ.get("WEBHOOK_URL") or _arg(2)
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET") or _arg(3)

    if not token or not url:
        print(__doc__)
        sys.exit(1)

    data = {"url": url, "allowed_updates": json.dumps(["message"])}
    if secret:
        data["secret_token"] = secret

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/setWebhook",
        data=urllib.parse.urlencode(data).encode(),
    )
    with urllib.request.urlopen(req) as resp:
        print(resp.read().decode())
    print("\nDone. Verify with:")
    print(f"  curl https://api.telegram.org/bot<token>/getWebhookInfo")


if __name__ == "__main__":
    main()
