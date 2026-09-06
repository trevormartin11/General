# Paste this into a local Claude Code session

Start a **local** session in the Claude Code desktop app (running on this
computer, not in the cloud), choose the `fantasy-draft` folder (or any
folder, and it will clone the repo), and paste the text below the line as
the first message. Each person does this on their own computer with their
own ESPN login.

---

I'm running my ESPN fantasy football draft today with a helper tool that is already written. Walk me through it one step at a time, in plain language, and wait for me to confirm each step before moving on. Never ask for my ESPN password, and don't ask me to paste cookies into this chat.

1. Find the tool: the fantasy-draft folder (this folder or a subfolder). If it isn't here, clone https://github.com/trevormartin11/General.git into this folder, check out the branch claude/fantasy-football-draft-automation-a5izt6, and use General/fantasy-draft. If cloning fails because I don't have access, stop and tell me; I'll get the folder as a zip instead.

2. In the fantasy-draft folder, read CLAUDE.md and DRAFT_DAY.md and follow them.

3. Run the self-test: python3 draft.py selftest (Windows: py draft.py selftest). Fix anything it flags, for example installing Python 3. It will say the ESPN cookies aren't set yet; that's expected at this point.

4. Copy config.example.json to config.json and open it in a text editor for me. Tell me exactly how to find my two ESPN cookies (espn_s2 and SWID) in my browser after logging in at espn.com, and where to paste them in the file. Wait until I say I've saved it.

5. Run the self-test again. It must show "Family Fantasy Football League", 12 teams, pass TD = 6.0 and reception = 1.0, and my team. If my team isn't detected, show me the team list from python3 draft.py status, ask which one is mine, set team_id in config.json, and re-run the self-test.

6. Run a practice draft so I can see what draft day looks like, in its own terminal window: open start_mock.command on Mac or start_mock.bat on Windows (or run python3 draft.py mock). Explain that Enter takes the #1 recommendation and typing a name picks someone else, and that python3 draft.py mock --auto --pace 0.5 runs a fast one where the tool picks for me.

7. When I say the draft room is open, start the real co-pilot in its own terminal window (start_live.command on Mac, start_live.bat on Windows) and confirm it shows the league name and is waiting for picks. Explain the routine: when that window says ON THE CLOCK, I click its #1 recommendation in ESPN, and I keep its top 2-3 players in my ESPN queue in case the clock runs out.

8. During the draft, if I ask "who should I take?", run python3 draft.py recommend and give me the top 3 in one line each. If the co-pilot window stops showing new picks for more than a minute, show me how to record picks by hand with python3 draft.py mark.
