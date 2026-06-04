#!/usr/bin/env python3
"""One-time Gmail authorization — run this on your LOCAL machine.

It opens a browser, asks you to sign in to the Google account that should
hold the drafts, and writes token.json (which includes a refresh token).

Usage:
    python scripts/gmail_auth.py [path/to/client_secret.json]

Then either:
  - keep token.json next to the app for local runs, or
  - copy its contents into the GMAIL_TOKEN_JSON env var on your host.

This needs a browser, so it will NOT work on a headless cloud host — that's
why you run it locally and ship the resulting token. See DEPLOY.md.
"""

from __future__ import annotations

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

# Must match the scope used by the app (create drafts only — no send).
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def main() -> None:
    client_secret = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
    print(f"Using OAuth client file: {client_secret}")

    flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    with open("token.json", "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())

    print("\n✅ Saved token.json")
    print("   • Local use: leave token.json next to the app.")
    print("   • Cloud use: copy its FULL contents into the GMAIL_TOKEN_JSON env var.")
    print("   Keep this file secret — it can create drafts in your Gmail.")


if __name__ == "__main__":
    main()
