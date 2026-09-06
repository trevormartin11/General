# Paste this into a local Claude Code session on the computer that will run the automated draft

---

I want the ESPN fantasy draft tool in this folder to make my picks for me today (automation mode). Walk me through it step by step and wait for me to confirm each step. Never ask for my ESPN password, and don't ask me to paste cookies into this chat.

1. Find the fantasy-draft folder (this folder or a subfolder). If it isn't here, clone https://github.com/trevormartin11/General.git, check out branch claude/fantasy-football-draft-automation-a5izt6, and use General/fantasy-draft. If cloning fails for lack of access, stop and tell me.

2. Read CLAUDE.md, DRAFT_DAY.md and AUTO_MODE.md in that folder.

3. Run python3 draft.py selftest (Windows: py draft.py selftest) and fix what it flags. When it asks for cookies, copy config.example.json to config.json, open it for me, and tell me exactly where to find espn_s2 and SWID in my browser after logging in at espn.com. Wait until I've saved it, then re-run the self-test until it shows "Family Fantasy Football League", 12 teams, pass TD = 6.0, reception = 1.0, and my team.

4. Follow AUTO_MODE.md section 1: install the playwright package, start the separate debug Chrome with the exact command for my operating system, and tell me to log in to ESPN in that window.

5. Follow AUTO_MODE.md section 2 with me: I'll join an ESPN mock draft in the debug Chrome. Run probe_draft_room.py with a player name and read what it prints; if the search box, the player hit, or the Draft button isn't found, inspect the page through Playwright and adjust the selectors at the top of auto_click.py until auto_click_test.py returns RESULT: OK on my turn, then do one real --click in the mock and confirm the pick showed up. Do this for a normal player and for a D/ST.

6. When I say my real draft room is open in the debug Chrome, start python3 draft.py live --auto in its own terminal window that I can watch, confirm it shows my league and is waiting for picks, and remind me to keep the top 2-3 recommendations in my ESPN queue as a backup.

7. During the draft, watch the co-pilot window with me. If a pick fails to confirm, tell me immediately so I can click it myself. If I ask "who should I take?", run python3 draft.py recommend and give me the top 3 in one line each.
