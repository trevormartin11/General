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

1. `python3 draft.py status` - confirm league name, 12 teams, scoring line
   `pass TD = 6.0, reception = 1.0`, and that `<== you` marks their team with
   a draft slot. If detection fails, ask which team is theirs and pass
   `--team-id` / `--slot`, or set it in `config.json`.
2. Optionally `python3 draft.py board` and `python3 draft.py simulate` so they
   can see the strategy.
3. When the draft room opens: run `python3 draft.py live` in a terminal they
   can see and leave it running. Tell them the routine: when the panel says
   ON THE CLOCK, click the #1 recommendation in ESPN; keep the top 2-3 in the
   ESPN queue as timeout insurance.
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
