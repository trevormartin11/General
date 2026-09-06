#!/usr/bin/env python3
"""
Rehearse the auto-clicker on the draft room that is open in the debug Chrome
(see auto_click.py header), without the live loop:

    python3 auto_click_test.py "Puka Nacua"            # dry run: search, find the row, find the Draft button
    python3 auto_click_test.py "Puka Nacua" --click    # really drafts him: only in an ESPN MOCK draft, on your turn

Use it inside an ESPN mock draft to prove the clicks work before the real draft.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from auto_click import AutoClicker  # noqa: E402


class _Rec:
    def __init__(self, name: str):
        from brain import Player
        self.player = Player(id=0, name=name, pos="?")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="player name exactly as ESPN shows it")
    ap.add_argument("--click", action="store_true", help="actually click Draft (mock drafts only!)")
    ap.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = ap.parse_args()
    ac = AutoClicker(dry_run=not args.click, cdp_url=args.cdp_url)
    print(f"Attaching: {ac.describe()}")
    ok = ac.pick([_Rec(args.name)])
    print("RESULT:", "OK" if ok else "FAILED (see screenshots/ and run probe_draft_room.py)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
