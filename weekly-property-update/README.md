# Weekly Property Update

A tiny tool for a family-office property manager: **capture what you did during
the week with zero effort, and produce a polished weekly report** for the
owners — delivered as a **Gmail draft** for you to review and send. One family,
multiple properties → one consolidated report.

> **Design principle: "dumb capture, smart compile."**
> Logging a note must take zero effort in the moment. All the intelligence
> happens later, at report time.

---

## How it works

```
  You (Telegram)            SQLite                 Claude API            Gmail
 ───────────────       ───────────────        ──────────────────     ────────────
 "fixed burst pipe   →  stored verbatim   →   grouped by property,  →  draft to
  at the Lakehouse,      with a timestamp      expenses totaled,        the owners
  $480 to Trident"       (id, ts, text)        follow-ups surfaced      (you review
                                                                        & send)
        ▲                                            ▲                      │
        └──────────  /report  ──or──  Friday 4pm scheduler  ───────────────┘
                                                                     │
                                              "📝 Draft ready for review."  → you
```

1. **Capture** — a Telegram bot. Send free-text messages any time; each is
   stored verbatim with a timestamp. No structure required.
2. **Storage** — SQLite (`id`, `timestamp`, `raw_text`).
3. **Compile** — on `/report` or automatically each Friday, the week's notes go
   to the Anthropic Claude API, which organizes them into a clean, owner-facing
   report grouped by property: per-property work, total expenses, open
   follow-ups.
4. **Deliver** — a Gmail draft addressed to the owners, subject
   `Property Update — Week of <dates>`, plus a Telegram nudge: *"Draft ready
   for review."*
5. **Schedule** — the Friday compile runs via an in-process scheduler, in your
   timezone.

### Telegram commands

| Command | What it does |
|---|---|
| *(any message)* | Logs the text verbatim with a timestamp |
| `/report` | Compile this week's notes into a report **now** |
| `/list` | Show this week's logged notes |
| `/undo` | Remove the last note |
| `/help` | Show help |
| `/start` | Show help **and your chat id** (needed for setup) |

---

## Project layout

```
weekly-property-update/
├── app/
│   ├── main.py          # entry point: starts the bot + scheduler
│   ├── config.py        # all config from .env (nothing personal hard-coded)
│   ├── db.py            # SQLite capture (id, timestamp, raw_text)
│   ├── bot.py           # Telegram handlers (capture, /report, /list, /undo)
│   ├── compile.py       # the single Claude call → report (cached system prompt)
│   ├── gmail_client.py  # Gmail OAuth + draft creation (drafts only)
│   ├── deliver.py       # gmail-draft or telegram-paste delivery
│   ├── pipeline.py      # gather → compile → deliver orchestration
│   ├── scheduler.py     # weekly cron job, in your timezone
│   └── util.py          # week windows, date formatting, markdown→html
├── scripts/gmail_auth.py  # one-time local Google sign-in → token.json
├── samples/             # sample notes + the report they produce
├── requirements.txt
├── Procfile             # worker: python -m app.main
├── .env.example
├── README.md
└── DEPLOY.md            # click-by-click hosting on Railway or Render
```

---

## Run it locally

Requires **Python 3.11+**.

```bash
cd weekly-property-update
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env with your values
```

At minimum set `TELEGRAM_BOT_TOKEN` and `ANTHROPIC_API_KEY`. For Gmail
delivery, also set `OWNER_EMAILS` and authorize Gmail once:

```bash
python scripts/gmail_auth.py path/to/client_secret.json   # opens a browser
```

(See [DEPLOY.md](DEPLOY.md) for how to get each token and the Google client
file.) Then start it:

```bash
python -m app.main
```

Message your bot on Telegram, send `/start` to grab your chat id, paste it into
`MANAGER_CHAT_ID`, restart, and try `/report`.

> Prefer **zero Google setup**? Set `DELIVERY_METHOD=telegram` and the bot will
> send you the finished report in Telegram to paste into an email yourself.

---

## Configuration

Everything is set via `.env` (see [`.env.example`](.env.example) for the
annotated list). The essentials:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | From @BotFather |
| `ANTHROPIC_API_KEY` | ✅ | — | From console.anthropic.com |
| `MANAGER_CHAT_ID` | ★ | — | Locks the bot to you + enables nudges. Get it via `/start` |
| `OWNER_EMAILS` | gmail | — | Comma-separated recipients for the draft |
| `MANAGER_NAME` | | `Your Name` | Signs the report |
| `OWNERS_GREETING` | | — | e.g. `Hartwell family` |
| `PROPERTIES` | | — | Comma-separated nicknames; helps grouping |
| `TIMEZONE` | | `America/Phoenix` | IANA name |
| `REPORT_DAY` / `REPORT_HOUR` / `REPORT_MINUTE` | | `fri` / `16` / `0` | Weekly compile time |
| `DELIVERY_METHOD` | | `gmail` | `gmail` (draft) or `telegram` (paste) |
| `GMAIL_TOKEN_JSON` | gmail | — | Contents of `token.json` (best for hosting) |
| `ANTHROPIC_MODEL` | | `claude-opus-4-8` | |
| `DB_PATH` | | `data/entries.db` | **Point at a persistent volume on a host** |

★ Strongly recommended — without it the bot is open to anyone who finds it and
can't send you nudges.

---

## Notes

- **Data persistence.** SQLite lives at `DB_PATH`. Cloud hosts have *ephemeral*
  filesystems — without a persistent volume your week's notes are wiped on every
  redeploy/restart. DEPLOY.md shows how to attach one.
- **Cost.** One Claude call per report (a handful per month). Negligible.
- **Privacy / security.** The bot only responds to `MANAGER_CHAT_ID`. Gmail
  scope is `gmail.compose` — it can create drafts but **cannot send**. Secrets
  live only in `.env` / host env vars and are git-ignored.

## Roadmap (not built yet)

- **v2:** at compile time, scan Gmail/Calendar for property items you forgot to
  log and suggest them for inclusion.

See [DEPLOY.md](DEPLOY.md) to host it on an always-on cloud box.
