# Draft day runbook - Sunday 2:00 PM, 12-team snake, 60 s per pick

Do steps 1-5 on **each** computer (yours and your wife's), each with your own
ESPN login. Budget 15 minutes per machine. Start at least 45 minutes early.

## 1. Get the folder onto the machine

Either `git pull` this repo, or copy the `fantasy-draft` folder over (zip,
AirDrop, USB). On the second machine, use Claude Code or a terminal in that
folder.

## 2. Cookies -> config.json

```
cp config.example.json config.json      # Windows: copy config.example.json config.json
```

Log in to espn.com in Chrome, press F12, *Application* -> *Cookies* ->
`https://www.espn.com`, copy `espn_s2` and `SWID` into `config.json`.
Each person uses their **own** cookies on their **own** machine.

## 3. Verify

```
python3 draft.py status
```

You want to see:

* `Name: Family Fantasy Football League`
* `Format: 12 teams | starters: QBx1, RBx2, WRx2, TEx1, DSTx1, Kx1, FLEXx1 | bench 6 | 15 rounds`
* `scoring: pass TD = 6.0, reception = 1.0, pass yd = 0.04`
* the 12 teams, and `<== you` next to yours with your draft slot (the slot
  appears once the league manager sets the order; until then the co-pilot
  still runs and picks it up automatically).

If it says it can't tell which team is yours, add `"team_id": <id from the
list>` to `config.json`, or pass `--slot N` on every command.

## 4. Prep (optional, 5 minutes)

```
python3 draft.py board            # cheat sheet under our scoring
python3 draft.py simulate         # mock draft from your slot
python3 draft.py simulate --slot 3 --slot 9    # both of you in one mock (use your real slots)
```

Add a few names to `targets.txt` / `avoid.txt` if you have strong opinions
(copy the `.example` files). Keep them short; they are nudges.

## 5. Draft time

1. Open the ESPN draft room in your browser and log in.
2. Start the co-pilot in its own window: double-click `start_live.command`
   (Mac; if macOS blocks it, right-click -> Open) or `start_live.bat`
   (Windows). Or, in a terminal in this folder:

   ```
   python3 draft.py live
   ```

   It prints every pick, says how many picks until you're up, shows the
   recommendation panel 2 picks early and again (with a beep) when you are on
   the clock.
3. When you're up: click the top recommendation in ESPN (or the second if you
   just hate the first). Before your clock runs low, keep the panel's top 2-3
   in your ESPN **queue** as timeout insurance.
4. Between your picks, glance at "Best ... left" to see the runs coming.

Ctrl-C stops it; restarting is safe (it re-reads the whole draft).

## If something breaks

| Symptom | Fix |
|---------|-----|
| `HTTP 401/403` | cookies wrong or expired: re-copy them into config.json |
| picks aren't showing up after a minute | keep `live` running and record picks by hand: `python3 draft.py mark "Name"`, `python3 draft.py mark --mine "Name"` |
| wrong team detected | `--team-id ID` or `--slot N` (from `status`) |
| slot shows `?` | the league manager hasn't set the order; it appears automatically once set, or pass `--slot N` |
| terminal is too narrow | widen it; the panel is ~110 characters |

## Auto-click mode (only if you tested it in a mock draft)

See the header of `auto_click.py`. Start Chrome with a separate profile and
`--remote-debugging-port=9222`, log in to ESPN there, open the draft room,
`pip install playwright`, then `python3 draft.py live --auto --dry-run` in an
ESPN mock draft. Only if the dry run finds the player and the Draft button
every time, drop `--dry-run` for the real draft - and still sit next to it.
