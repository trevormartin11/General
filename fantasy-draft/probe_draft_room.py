#!/usr/bin/env python3
"""
Print what the auto-clicker can see in the ESPN draft room, so the selectors
in auto_click.py can be adjusted quickly. Run with the debug Chrome open on
the draft room (see auto_click.py header):

    python3 probe_draft_room.py [--cdp-url http://127.0.0.1:9222] [--name "Puka Nacua"]

Saves screenshots/probe.png and a text dump screenshots/probe.txt.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from auto_click import SHOTS, AutoClicker  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    ap.add_argument("--name", help="type this player into the search box and report what appears")
    args = ap.parse_args()
    ac = AutoClicker(dry_run=True, cdp_url=args.cdp_url)
    page = ac.page()
    print(f"Draft room tab: {page.url}")
    print(f"Title: {page.title()}")
    lines = []
    box = ac.find_search_box(page)
    print(f"Search box found: {'yes' if box else 'NO'}")
    inputs = page.locator("input")
    print(f"Inputs on page: {inputs.count()}")
    for i in range(min(inputs.count(), 15)):
        el = inputs.nth(i)
        try:
            desc = (f"  input[{i}] type={el.get_attribute('type')!r} placeholder={el.get_attribute('placeholder')!r} "
                    f"aria-label={el.get_attribute('aria-label')!r} visible={el.is_visible()}")
        except Exception as e:  # noqa: BLE001
            desc = f"  input[{i}] (error: {e})"
        print(desc)
        lines.append(desc)
    buttons = page.get_by_role("button")
    n = buttons.count()
    print(f"Buttons on page: {n} (showing visible ones with text)")
    shown = 0
    for i in range(min(n, 400)):
        b = buttons.nth(i)
        try:
            if not b.is_visible():
                continue
            txt = re.sub(r"\s+", " ", b.inner_text(timeout=200) or "").strip()
        except Exception:  # noqa: BLE001
            continue
        if txt:
            desc = f"  button[{i}] {txt[:60]!r} enabled={b.is_enabled()}"
            print(desc)
            lines.append(desc)
            shown += 1
        if shown >= 60:
            break
    if args.name:
        if box is None:
            print("Cannot test the search: no search box found.")
        else:
            box.click()
            box.fill("")
            box.type(args.name.replace(" D/ST", ""), delay=20)
            page.wait_for_timeout(900)
            hits = page.get_by_text(args.name, exact=False)
            print(f"After typing {args.name!r}: {hits.count()} element(s) contain that text")
            for i in range(min(hits.count(), 5)):
                try:
                    print(f"  hit[{i}] visible={hits.nth(i).is_visible()} text={hits.nth(i).inner_text(timeout=300)[:80]!r}")
                except Exception as e:  # noqa: BLE001
                    print(f"  hit[{i}] error: {e}")
    os.makedirs(SHOTS, exist_ok=True)
    page.screenshot(path=os.path.join(SHOTS, "probe.png"), full_page=False)
    with open(os.path.join(SHOTS, "probe.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved {os.path.join(SHOTS, 'probe.png')} and probe.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
