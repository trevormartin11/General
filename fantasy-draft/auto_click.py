"""
EXPERIMENTAL auto-clicker for the ESPN draft room (used by: draft.py live --auto).

How it attaches: Playwright connects to a Chrome you started with remote
debugging enabled, so it reuses YOUR logged-in session and the draft-room
tab you already have open. Nothing is typed into ESPN's login form.

  1. pip install playwright        (the browser itself is NOT needed; we attach to Chrome)
  2. Start Chrome with a separate profile + debugging port, e.g.
       mac:  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
                 --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-draft"
       win:  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^
                 --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\\chrome-draft"
  3. In that Chrome, log in to ESPN and open the draft room.
  4. python3 probe_draft_room.py          (prints what this code can see: search box, buttons, rows)
     python3 draft.py live --auto --dry-run   (finds/highlights the player, never clicks Draft)
     python3 draft.py live --auto             (real)

The draft room's HTML is not documented and changes; the selectors below are
best-effort and MUST be verified in an ESPN mock draft before the real
thing (see AUTO_MODE.md). On any failure it saves a screenshot into
screenshots/ and gives up on that pick so ESPN's own timer/queue takes over.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "screenshots")

# Candidate selectors, tried in order. Adjust after running probe_draft_room.py.
SEARCH_SELECTORS = [
    'input[placeholder*="search" i]',
    'input[type="search"]',
    'input[aria-label*="search" i]',
    'input[name*="search" i]',
]
DRAFT_BUTTON_NAME = re.compile(r"^\s*(draft|draft player|make pick|select|submit pick)\s*$", re.I)
CONFIRM_BUTTON_NAME = re.compile(r"^\s*(confirm|yes|draft|ok|submit)\s*$", re.I)
PICK_BUDGET_SECONDS = 25  # never spend longer than this on one attempt


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
    def page(self):
        from playwright.sync_api import sync_playwright  # imported lazily so the rest works without Playwright
        if self._pw is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
        for ctx in self._browser.contexts:
            for pg in ctx.pages:
                url = pg.url.lower()
                if "espn.com" in url and "draft" in url:
                    return pg
        raise RuntimeError("No ESPN draft-room tab found in the debug Chrome (URL must contain 'espn.com' and 'draft').")

    def shot(self, page, tag: str) -> str:
        path = os.path.join(SHOTS, f"{dt.datetime.now().strftime('%H%M%S')}_{tag}.png")
        try:
            page.screenshot(path=path, full_page=False)
        except Exception:  # noqa: BLE001
            pass
        return path

    def find_search_box(self, page):
        for sel in SEARCH_SELECTORS:
            loc = page.locator(sel)
            try:
                if loc.count() and loc.first.is_visible():
                    return loc.first
            except Exception:  # noqa: BLE001
                continue
        return None

    # --------------------------------------------------------------- action
    def pick(self, recs) -> bool:
        """Try the recommendations in order; return True if a pick was submitted (or dry-run found the player)."""
        for r in recs:
            started = time.time()
            try:
                if self._try_player(r.player.name):
                    return True
            except Exception as e:  # noqa: BLE001
                print(f"[auto] {r.player.name}: {e}")
            if time.time() - started > PICK_BUDGET_SECONDS:
                print("[auto] out of time for this pick; leaving it to ESPN's queue/timer")
                break
        print("[auto] Could not submit a pick; rely on the ESPN queue / timer.")
        return False

    def _try_player(self, name: str) -> bool:
        page = self.page()
        try:
            page.bring_to_front()
        except Exception:  # noqa: BLE001
            pass
        box = self.find_search_box(page)
        if box is None:
            self.shot(page, "no_search_box")
            raise RuntimeError("player search box not found (run probe_draft_room.py and adjust SEARCH_SELECTORS)")
        box.click()
        box.fill("")
        box.type(name.replace(" D/ST", ""), delay=20)
        time.sleep(0.8)
        row = page.get_by_text(name, exact=False).first
        try:
            visible = row.count() > 0 and row.is_visible()
        except Exception:  # noqa: BLE001
            visible = False
        if not visible:
            self.shot(page, "player_not_listed")
            raise RuntimeError("player not visible after search (already drafted, or name differs)")
        row.click()
        time.sleep(0.4)
        draft_btn = page.get_by_role("button", name=DRAFT_BUTTON_NAME)
        try:
            if draft_btn.count() == 0 or not draft_btn.first.is_visible():
                raise RuntimeError("no visible Draft button (is it your turn? run probe_draft_room.py)")
            if not draft_btn.first.is_enabled():
                raise RuntimeError("Draft button is disabled (is it your turn?)")
        except RuntimeError:
            self.shot(page, "no_draft_button")
            raise
        if self.dry_run:
            self.shot(page, "dry_run_" + re.sub(r"\W+", "_", name))
            print(f"[auto] DRY RUN: found {name} and an enabled Draft button; not clicking (screenshot saved)")
            return True
        draft_btn.first.click()
        time.sleep(0.6)
        confirm = page.get_by_role("button", name=CONFIRM_BUTTON_NAME)
        try:
            if confirm.count() and confirm.first.is_visible():
                confirm.first.click()
        except Exception:  # noqa: BLE001
            pass
        self.shot(page, "picked_" + re.sub(r"\W+", "_", name))
        print(f"[auto] Submitted pick: {name}")
        return True
