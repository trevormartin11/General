"""
EXPERIMENTAL auto-clicker for the ESPN draft room (used by: draft.py live --auto).

How it attaches: Playwright connects to a Chrome you started with remote
debugging enabled, so it reuses YOUR logged-in session and the draft room tab
you already have open. Nothing is typed into ESPN's login form by this code.

  1. pip install playwright        (the browser itself is NOT needed; we attach to Chrome)
  2. Start Chrome with a separate profile + debugging port, e.g.
       mac:  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
                 --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-draft"
       win:  "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
                 --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome-draft"
  3. In that Chrome, log in to ESPN and open the draft room.
  4. python3 draft.py live --auto --dry-run   (test: finds/highlights the player, never clicks Draft)
     python3 draft.py live --auto             (real)

The draft room's HTML is not documented and changes; the selectors below are
best-effort guesses and MUST be verified in an ESPN mock draft before the real
thing. On any failure it saves a screenshot into screenshots/ and gives up on
that pick so ESPN's own timer/queue takes over. Prefer the co-pilot mode.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "screenshots")

SEARCH_SELECTORS = [
    'input[placeholder*="search" i]',
    'input[type="search"]',
    'input[aria-label*="search" i]',
    'input[name*="search" i]',
]
DRAFT_BUTTON_PATTERN = re.compile(r"^\s*(draft|draft player|make pick|select)\s*$", re.I)
CONFIRM_PATTERN = re.compile(r"^\s*(confirm|yes|draft|ok)\s*$", re.I)


class AutoClicker:
    def __init__(self, dry_run: bool = True, cdp_url: str = "http://127.0.0.1:9222"):
        self.dry_run = dry_run
        self.cdp_url = cdp_url
        self._pw = None
        self._browser = None
        os.makedirs(SHOTS, exist_ok=True)

    def describe(self) -> str:
        return f"attach to Chrome at {self.cdp_url}; dry_run={self.dry_run}"

    # ------------------------------------------------------------- plumbing
    def _page(self):
        from playwright.sync_api import sync_playwright  # imported lazily so the rest works without Playwright
        if self._pw is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
        for ctx in self._browser.contexts:
            for page in ctx.pages:
                url = page.url.lower()
                if "espn.com" in url and "draft" in url:
                    return page
        raise RuntimeError("No ESPN draft-room tab found in the debug Chrome (URL must contain 'espn.com' and 'draft').")

    def _shot(self, page, tag: str) -> str:
        path = os.path.join(SHOTS, f"{dt.datetime.now().strftime('%H%M%S')}_{tag}.png")
        try:
            page.screenshot(path=path, full_page=False)
        except Exception:  # noqa: BLE001
            pass
        return path

    # --------------------------------------------------------------- action
    def pick(self, recs) -> bool:
        """Try the recommendations in order; return True if a pick was submitted."""
        for r in recs:
            try:
                if self._try_player(r.player.name):
                    return True
            except Exception as e:  # noqa: BLE001
                print(f"[auto] {r.player.name}: {e}")
        print("[auto] Could not submit a pick; rely on the ESPN queue / timer.")
        return False

    def _try_player(self, name: str) -> bool:
        page = self._page()
        page.bring_to_front()
        box = None
        for sel in SEARCH_SELECTORS:
            loc = page.locator(sel)
            if loc.count():
                box = loc.first
                break
        if box is None:
            self._shot(page, "no_search_box")
            raise RuntimeError("player search box not found")
        box.click()
        box.fill("")
        box.type(name, delay=25)
        time.sleep(0.9)
        row = page.get_by_text(name, exact=False).first
        if not row.count():
            self._shot(page, "player_not_listed")
            raise RuntimeError("player not visible after search (already drafted, or name differs)")
        row.click()
        time.sleep(0.4)
        buttons = page.get_by_role("button")
        draft_btn = None
        for i in range(min(buttons.count(), 200)):
            b = buttons.nth(i)
            try:
                txt = (b.inner_text(timeout=300) or "").strip()
            except Exception:  # noqa: BLE001
                continue
            if DRAFT_BUTTON_PATTERN.match(txt) and b.is_visible() and b.is_enabled():
                draft_btn = b
                break
        if draft_btn is None:
            self._shot(page, "no_draft_button")
            raise RuntimeError("no enabled Draft button found (is it your turn?)")
        if self.dry_run:
            self._shot(page, "dry_run_" + re.sub(r"\W+", "_", name))
            print(f"[auto] DRY RUN: would click Draft for {name} (screenshot saved)")
            return True
        draft_btn.click()
        time.sleep(0.6)
        for i in range(min(page.get_by_role("button").count(), 200)):
            b = page.get_by_role("button").nth(i)
            try:
                txt = (b.inner_text(timeout=300) or "").strip()
            except Exception:  # noqa: BLE001
                continue
            if CONFIRM_PATTERN.match(txt) and b.is_visible():
                b.click()
                break
        self._shot(page, "picked_" + re.sub(r"\W+", "_", name))
        print(f"[auto] Submitted pick: {name}")
        return True
