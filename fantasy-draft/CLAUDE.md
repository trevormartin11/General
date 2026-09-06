# Claude Code instructions for the fantasy-draft folder

You are helping the person at this computer run their ESPN fantasy football
draft with the co-pilot in this folder. Read README.md and DRAFT_DAY.md first.

## Ground rules

* The tool is stdlib-only Python 3. If `python3` is missing, install it
  (`brew install python` on macOS, `winget install Python.Python.3.12` on
  Windows) - do not rewrite the tool in another language.
* Never ask the person for their ESPN password and never type into ESPN's
  login form. The only credentials involved are the `espn_s2` and `SWID`
  cookies in `config.json`, which they paste themselves (README "Cookies").
  Do not print those cookies back into the chat, and never commit
  `config.json`, `cache/`, `drafted.txt` or `screenshots/`.
* Two people in the same league use this on two computers with separate
  accounts. This copy serves only the person logged in here; do not try to
  coordinate picks with the other computer.

## What to do when asked to "run my draft"

1. `python3 draft.py selftest` - checks Python, the offline tests, ESPN
   access, the cookies in `config.json`, the league (must show
   `pass TD = 6.0, reception = 1.0`, 12 teams), their team + slot, the
   player pool, a simulated draft, and a fast offline mock. Fix whatever it
   flags. If team detection fails, `python3 draft.py status` lists the
   teams; set `team_id` (or `slot`) in `config.json`.
2. `python3 draft.py mock` in its own terminal window (`start_mock.command`
   / `start_mock.bat`) is the practice draft that looks exactly like draft
   day; `--auto --pace 0.5` runs a quick automatic one. `board` and
   `simulate` show the strategy.
3. When the draft room opens, start the co-pilot **in its own terminal
   window**, not through your Bash tool (it runs for 2-3 hours and would hit
   the tool timeout):
   * macOS: `open -a Terminal ./start_live.command`
   * Windows: `start "" start_live.bat`
   * Linux: `x-terminal-emulator -e ./start_live.command` (or tell them to
     run `python3 draft.py live` in a terminal themselves)
   Confirm the new window shows the league name and "Waiting for the draft"
   or the current pick. Tell them the routine: when the panel says ON THE
   CLOCK, click the #1 recommendation in ESPN; keep the top 2-3 in the ESPN
   queue as timeout insurance.
4. Stay available. If they ask "who should I take" or "QB now or later?",
   run `python3 draft.py recommend` for the fresh panel and explain the Gain
   / Now+ / Avail@nxt columns in one sentence each. They make the final call.
5. If the live feed stops updating (no new picks for a minute while the
   draft room shows picks), keep `live` running and record picks with
   `python3 draft.py mark "Name"` / `mark --mine "Name"` as they happen; the
   panel keeps working from the manual list.

## Do not

* Do not enable `--auto` unless the person explicitly asks for it and has
  tested it in an ESPN mock draft with `--dry-run`. It is experimental.
* Do not "improve" the value model minutes before the draft. If you must
  change code, run `python3 -m unittest discover -s tests` first.

## Automation mode (the tool clicks the picks)

Only when the person explicitly asks for it. Follow **AUTO_MODE.md**: install
the `playwright` package, start a separate debug Chrome, rehearse in an ESPN
mock draft with `probe_draft_room.py` and `auto_click_test.py` (dry run,
then one real `--click` in the mock), adjust the selectors at the top of
`auto_click.py` if ESPN's page differs, and only then run
`python3 draft.py live --auto` for the real draft, in its own terminal
window. You can inspect the live page through Playwright (see
`probe_draft_room.py`) to fix selectors; never type into ESPN's login form.
