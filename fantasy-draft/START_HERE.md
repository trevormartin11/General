# Start here (fantasy draft co-pilot)

This folder is a helper for our ESPN fantasy football draft. It watches the
live draft and tells you the best available pick for **your** team, scored
under our league's rules. You still click the pick in ESPN; it just tells
you who.

## What you need on your computer

1. **Python 3** (free, no extra packages needed).
   * Mac: open Terminal, type `python3 --version`. If it offers to install
     "command line developer tools", click Install and wait.
   * Windows: install "Python 3.12" from the Microsoft Store (search
     "Python" in the Store). In commands below use `py` instead of `python3`.
2. **The Claude Code desktop app**, signed in with your own account.
3. A browser logged in to **espn.com** with your own ESPN account.

That's it. Nothing else to download.

## Steps (about 15 minutes; do this at least 45 minutes before the draft)

1. Unzip this. Put the `fantasy-draft` folder somewhere easy, like the Desktop.
2. Open Claude Code. Start a **new session that runs locally on this
   computer** (not in the cloud) and choose the `fantasy-draft` folder.
3. Open `SETUP_PROMPT.md`, copy everything below the line, and paste it as
   your first message. Claude will run a self-test, help you put your two
   ESPN cookies into `config.json`, test again, and run a practice draft so
   you can see what draft day looks like.
4. At draft time: open the ESPN draft room in your browser, tell Claude
   "the draft room is open", and follow the window it opens. When it says
   ON THE CLOCK, click its #1 player in ESPN. Keep its top 2-3 in your ESPN
   queue in case the clock runs out.

## Without Claude Code (optional)

Open a terminal in this folder and run `python3 draft.py selftest`; it tells
you what to fix. Then double-click `start_mock.command` (Mac) or
`start_mock.bat` (Windows) to practice, and `start_live.command` /
`start_live.bat` at draft time. `README.md` has every command.

## Privacy

The only credentials involved are two ESPN browser cookies you paste into
`config.json` yourself. They are used only to read your league from ESPN
and never leave your computer. Never share your ESPN password with anyone,
including Claude.
