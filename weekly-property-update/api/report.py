"""Vercel function: compile and deliver the weekly report.

Triggered by the scheduled GitHub Action (and manual workflow_dispatch). Auth is
a shared secret in the X-Report-Secret header, so only your Action can run it.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wpu import compile as compile_mod  # noqa: E402
from wpu import config, db, deliver, telegram_api  # noqa: E402


def run_report() -> dict:
    entries = db.get_week_entries()
    if not entries:
        if config.MANAGER_CHAT_ID is not None:
            telegram_api.send_message(
                config.MANAGER_CHAT_ID,
                "🗒️ No notes were logged this week, so I didn't generate a report.",
            )
        return {"status": "empty"}

    report = compile_mod.compile_report(entries)
    deliver.deliver_report(report, entries)
    if config.MANAGER_CHAT_ID is not None:
        telegram_api.send_message(
            config.MANAGER_CHAT_ID,
            f"📝 Draft ready for review.\n{report.subject} — open Gmail to review & send.",
        )
    return {"status": "ok", "subject": report.subject, "entries": report.num_entries}


class handler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        secret = self.headers.get("X-Report-Secret", "")
        return bool(config.REPORT_SECRET) and secret == config.REPORT_SECRET

    def _run(self):
        if not self._authorized():
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"unauthorized")
            return
        try:
            payload = json.dumps(run_report()).encode()
            code = 200
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            payload = json.dumps({"status": "error", "error": str(exc)}).encode()
            code = 500
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):  # noqa: N802
        self._run()

    def do_GET(self):  # noqa: N802 — allow manual trigger via a GET with the secret header too
        self._run()
