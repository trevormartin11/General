# Fantasy Draft Co-Pilot (ESPN)

A small, dependency-free Python tool that watches your live ESPN fantasy
football draft and tells you the best available pick for **your** roster,
scored under **your** league's rules (12-team, full PPR, 6-point passing TDs,
1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / 1 D/ST / 1 K, 6 bench, snake, 60 seconds
per pick).

Two people in the same draft can each run it on their own computer with their
own ESPN login; each copy only sees its own roster and the shared board, so
there is nothing to coordinate.

> Draft-day checklist: see **[DRAFT_DAY.md](DRAFT_DAY.md)**.
> Running it through Claude Code on your machine: it reads **[CLAUDE.md](CLAUDE.md)**.

## What it does

* Pulls the live draft from ESPN's API every few seconds (who is on the clock,
  every pick so far) and the player pool with ESPN's season projections
  **already rescored with this league's settings**, plus ADP and injury status.
* Recommends picks for your team:
  * value = 65% projection + 35% market consensus (ADP), so one odd projection
    can't hijack a pick;
  * **gain** = how many more points a player gives you than what would fill
    that slot if you waited until your last pick (so needed starters keep
    priority all draft long);
  * **urgency** = what waiting one more round would cost at that position,
    from ADP survival odds up to your next pick (tier cliffs, positional runs);
  * roster rules: never a 3rd QB / 2nd kicker / 2nd defense, K and D/ST only in
    the last three picks, and a guard that fills every starting slot before
    the draft ends.
* Optional per-person `targets.txt` (small nudge) and `avoid.txt` (never).
* `simulate` runs a full mock draft against ADP-following bots so you can see
  how the strategy plays from your slot before the real thing.

## Modes

| Mode | Command | Risk |
|------|---------|------|
| **Co-pilot (recommended)** | `python3 draft.py live` (or double-click `start_live.command` / `start_live.bat`) | none: it prints, you click in the ESPN draft room |
| Auto-click (experimental) | `python3 draft.py live --auto` | brittle: drives your Chrome via Playwright; test in a mock draft first |

The co-pilot prints every pick as it happens, beeps when you are on the clock,
and shows a ranked panel like this:

```
====================================================================================================
YOU ARE ON THE CLOCK  -  Round 3, pick #31
====================================================================================================
Your roster: QB 0/1  RB 1/2  WR 1/2  TE 0/1  FLEX 0/1  DST 0/1  K 0/1  BN 0/6
After this, your following pick is #42 (11 picks later)

 # Player                     Pos Tm  Bye   Proj   Gain  Now+    ADP Avail@nxt  Fills          Notes
 1 Trey McBride               TE  ARI  14  241.7   88.0  30.1   23.2        4%  TE1 starter    likely gone by your next pick; cliff at position after him
 2 Breece Hall                RB  NYJ  13  274.5   70.4  12.0   36.0       62%  RB2 starter
 ...
  Best QB  left: Lamar Jackson (322), Drake Maye (320), ...
Timeout insurance: put Trey McBride / Breece Hall / Drake London at the top of your ESPN queue.
```

## Setup (both computers)

1. Python 3.9+ (`python3 --version`; on Windows use `py` instead of `python3`).
2. Copy this `fantasy-draft` folder to the computer (git clone, zip, AirDrop).
3. `cp config.example.json config.json` and paste **your own** ESPN cookies
   (see below). Each of you uses your own cookies on your own machine; the tool
   finds your team from them. Never commit `config.json` (it is git-ignored).
4. `python3 draft.py status` - should print the league name, the 12 teams with
   owners, the draft order once the league manager has set it, and
   `scoring: pass TD = 6.0, reception = 1.0`. That line proves the cookies hit
   the right league.
5. `python3 draft.py board` - the cheat sheet. `python3 draft.py simulate` -
   mock draft from your slot.

### Cookies (`espn_s2` and `SWID`)

The league is private, so ESPN needs to know you are a member. Log in at
espn.com in your browser, then:

* **Chrome / Edge**: F12 -> *Application* tab -> *Storage* -> *Cookies* ->
  `https://www.espn.com` -> copy the *Value* of `espn_s2` (long) and `SWID`
  (looks like `{1234ABCD-....}`, keep the braces).
* **Firefox**: F12 -> *Storage* -> *Cookies*.
* **Safari**: Preferences -> Advanced -> "Show Develop menu", then Develop ->
  Show Web Inspector -> *Storage* -> *Cookies*.

Paste them into `config.json`. They usually stay valid for a long time, but if
`status` starts returning 401/403, grab fresh ones.

## Commands

```
python3 draft.py status                       league, teams, draft order, cookie check
python3 draft.py board [--csv board.csv]      cheat sheet under your scoring (+ CSV)
python3 draft.py board --queue-file queue.txt names in draft order (for ESPN's queue / rankings)
python3 draft.py live                         the co-pilot (Ctrl-C to stop)
python3 draft.py live --warn 3 --top 10       show the panel 3 picks early, 10 names
python3 draft.py recommend                    one-shot panel for the current state
python3 draft.py simulate [--slot 7] [--all]  mock draft(s) against ADP bots
python3 draft.py mark "Player Name"           manual fallback, see below
python3 draft.py mark --mine "Player Name"    ... a pick YOU made
python3 draft.py unmark                       remove the last manual entry
```

Global options: `--slot N` / `--team-id ID` (if auto-detection can't tell
which team is yours), `--kdst-picks N` (consider K/D/ST in the last N picks,
default 3), `--refresh` (re-download the player pool), `--public` (ESPN's
default PPR league, for testing without cookies).

## If the live feed doesn't update

ESPN's league endpoint normally shows picks within a few seconds. If it
doesn't, keep the co-pilot running and record picks by hand from the draft
room; the panel stays correct:

```
python3 draft.py mark "Jahmyr Gibbs" "Bijan Robinson"
python3 draft.py mark --mine "Puka Nacua"
```

## Safety net (do this regardless of mode)

In the ESPN draft room, keep 2-3 players in your **queue** at all times (the
panel tells you who). If you run out of clock, ESPN autopicks from your queue
first, then from its rankings.

## Notes

* Read-only API access uses your own session cookies and behaves like the
  ESPN app; the auto-click mode automates your browser, which ESPN's terms
  frown upon. That, plus its brittleness, is why co-pilot mode is the default.
* Nothing here sends your cookies anywhere except to ESPN.
* Tests: `python3 -m unittest discover -s tests -v` (offline, synthetic data).
