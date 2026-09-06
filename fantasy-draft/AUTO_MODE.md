# Automation mode (the tool clicks your picks)

Experimental. It drives **your own Chrome** through Chrome's remote-debugging
port (Playwright) and clicks the same search box and Draft button you would.
ESPN's draft-room page is undocumented and changes, so you must rehearse in
an **ESPN mock draft** first. Stay near the computer during the real draft:
if a click fails, the panel still shows the pick and ESPN's queue/timer is
the fallback.

## 1. Setup (15 minutes)

1. Finish the normal setup first: `python3 draft.py selftest` must pass
   (cookies, league, your team). See DRAFT_DAY.md.
2. Install Playwright's Python package (the browser download is NOT needed):
   ```
   pip3 install playwright        # Windows: py -m pip install playwright
   ```
3. Start a **separate** Chrome with remote debugging. Chrome refuses
   debugging on your everyday profile, so this uses a fresh one:
   * Mac (Terminal):
     ```
     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-draft" &
     ```
   * Windows (Command Prompt):
     ```
     "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome-draft"
     ```
4. In THAT Chrome window, log in to espn.com (fresh profile = fresh login).
   Leave it open. This is the window the tool will click in.

## 2. Rehearsal in an ESPN mock draft (required)

1. In the debug Chrome: fantasy.espn.com -> Fantasy Football -> Mock Draft
   Lobby -> join a 12-team snake mock (any clock). Wait in the draft room.
2. See what the tool can see:
   ```
   python3 probe_draft_room.py --name "Puka Nacua"
   ```
   It must report: the draft-room tab found, a search box found, and that
   typing the name shows a visible hit. It also lists the visible buttons; on
   your turn one of them should read "Draft" (or similar). If the words
   differ, edit `SEARCH_SELECTORS`, `DRAFT_BUTTON_NAME` and
   `CONFIRM_BUTTON_NAME` at the top of `auto_click.py`. Screenshots land in
   `screenshots/`.
3. Dry run on your turn in the mock:
   ```
   python3 auto_click_test.py "Puka Nacua"
   ```
   should end with `RESULT: OK` (it finds the player and an enabled Draft
   button, but does not click).
4. Real click, still in the mock, on your turn:
   ```
   python3 auto_click_test.py "Puka Nacua" --click
   ```
   The pick should appear in the mock draft. Repeat once with a defense,
   e.g. `"Texans D/ST"`. If both work, the clicker is trustworthy for today.

## 3. The real draft

1. Open your league's draft room in the debug Chrome (same window).
2. In a terminal in this folder:
   ```
   python3 draft.py live --auto
   ```
   Add `--dry-run` to watch it choose without clicking (co-pilot behaviour).
3. On each of your turns it: computes the pick, types the name in the search
   box, clicks the row, clicks Draft, confirms if a dialog appears, then
   watches ESPN's API for up to 12 s to see the pick register. If the button
   isn't there yet it retries every 2 s; if a submitted pick doesn't
   register it moves to the next candidate; it stops trying 45 s into your
   turn so ESPN's autopick can act. Tune with `--confirm-seconds` and
   `--pick-deadline`.
4. Keep ESPN's queue stocked with the panel's top 2-3 anyway.

## If it misbehaves mid-draft

* Ctrl-C the tool and run `python3 draft.py live` (co-pilot only). Your
  picks are never lost: the loop re-reads the whole draft from ESPN on start.
* `screenshots/` shows what the page looked like at each failure.
