# DEPLOY.md — click-by-click

Get the Weekly Property Update bot running on an always-on cloud host. Plan for
~30 minutes the first time. Order:

1. [Create the Telegram bot token](#1-telegram-bot-token)
2. [Create the Anthropic API key](#2-anthropic-api-key)
3. [Authorize Gmail (one-time Google sign-in)](#3-authorize-gmail-one-time) — skip if using Telegram delivery
4. [Deploy on Railway](#4a-deploy-on-railway-recommended) **or** [Render](#4b-deploy-on-render)
5. [First run & test](#5-first-run--test)

> **Don't want any Google setup?** Set `DELIVERY_METHOD=telegram`, skip step 3,
> and the bot sends you the finished report in Telegram to paste into an email
> yourself. Everything else is identical.

---

## 1. Telegram bot token

1. Open Telegram and message **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot`.
3. Give it a **name** (e.g. *Property Update*) and a **username** ending in
   `bot` (e.g. `hartwell_property_bot`).
4. BotFather replies with a token like `123456789:AAH...`. **Copy it** — this is
   your `TELEGRAM_BOT_TOKEN`.
5. Open a chat with your new bot and press **Start** (you'll grab your chat id
   in step 5).

---

## 2. Anthropic API key

1. Go to **[console.anthropic.com](https://console.anthropic.com)** and sign in.
2. Make sure you have billing/credits set up (**Settings → Billing**).
3. Go to **Settings → API keys → Create key**.
4. Copy the key (`sk-ant-...`). This is your `ANTHROPIC_API_KEY`.

---

## 3. Authorize Gmail (one-time)

This lets the bot create drafts **in your Gmail**. It only ever creates drafts —
it cannot send. You do this **once on your own computer** (it needs a browser),
then ship the resulting token to the host.

### 3a. Create a Google Cloud project + OAuth client

1. Go to **[console.cloud.google.com](https://console.cloud.google.com)**.
2. Top bar → project dropdown → **New Project** → name it (e.g.
   *property-update*) → **Create**, then select it.
3. **APIs & Services → Library** → search **Gmail API** → **Enable**.
4. **APIs & Services → OAuth consent screen**:
   - User type: **External** → **Create**.
   - App name (e.g. *Property Update*), your email for support + developer
     contact → **Save and Continue**.
   - **Scopes:** skip (Save and Continue).
   - **Test users:** **Add users** → add the Gmail address that will hold the
     drafts → **Save and Continue**. (Test mode is fine; no app verification
     needed for your own account.)
5. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app** → name it → **Create**.
   - **Download JSON** → save it as `client_secret.json`.

### 3b. Generate the token locally

On your computer, in the project folder:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/gmail_auth.py path/to/client_secret.json
```

A browser opens → sign in with the test-user Gmail → allow access. (If you see
a "Google hasn't verified this app" screen, click **Advanced → Go to … (unsafe)**
— that's expected for your own test app.) The script writes **`token.json`**.

`token.json` contains a refresh token, so the bot keeps working without you
signing in again. You'll paste its contents into the host as `GMAIL_TOKEN_JSON`
in step 4. **Keep it secret** (it's git-ignored).

---

## 4a. Deploy on Railway (recommended)

1. Push this repo to GitHub (the `weekly-property-update/` folder).
2. Go to **[railway.app](https://railway.app)** → **New Project → Deploy from
   GitHub repo** → pick your repo.
3. If the app isn't at the repo root, open the service → **Settings → Root
   Directory** → set it to `weekly-property-update`.
4. **Settings → Deploy → Start Command:** `python -m app.main`
   (Railway auto-detects Python and installs `requirements.txt`.)
5. **Variables → add** the following (Raw editor makes this fast):
   ```
   TELEGRAM_BOT_TOKEN=123456789:AAH...
   ANTHROPIC_API_KEY=sk-ant-...
   MANAGER_NAME=Jordan Rivera
   OWNERS_GREETING=Hartwell family
   OWNER_EMAILS=owner1@example.com, owner2@example.com
   PROPERTIES=Lakehouse, Downtown Duplex, Mountain Cabin
   TIMEZONE=America/Phoenix
   REPORT_DAY=fri
   REPORT_HOUR=16
   REPORT_MINUTE=0
   DELIVERY_METHOD=gmail
   DB_PATH=/data/entries.db
   GMAIL_TOKEN_JSON={"token": "...paste the FULL contents of token.json on one line..."}
   ```
   (Leave `MANAGER_CHAT_ID` blank for now — you'll add it in step 5.)
6. **Add a persistent volume** so your notes survive restarts: service →
   **Settings → Volumes → New Volume**, mount path **`/data`**. (This matches
   `DB_PATH=/data/entries.db` above.) **Without this, a redeploy wipes the
   week's notes.**
7. Deploy. Open **Deploy Logs** — you should see
   `Bot started; delivery method = gmail` and the scheduled-report line.

---

## 4b. Deploy on Render

1. Push this repo to GitHub.
2. Go to **[render.com](https://render.com) → New → Background Worker**
   (not a Web Service — this bot polls Telegram, it doesn't serve HTTP).
3. Connect the repo. **Root Directory:** `weekly-property-update`.
4. **Build Command:** `pip install -r requirements.txt`
   **Start Command:** `python -m app.main`
5. **Environment → add** the same variables as the Railway list above, but set:
   ```
   DB_PATH=/var/data/entries.db
   ```
6. **Add a disk** for persistence: service → **Disks → Add Disk**, mount path
   **`/var/data`**, size 1 GB. (Matches `DB_PATH` above.)
7. **Create Background Worker.** Watch the logs for `Bot started`.

> Render's free tier sleeps inactive services; for an always-on bot + Friday
> scheduler use a paid instance (or Railway).

---

## 5. First run & test

1. In Telegram, send your bot **`/start`**. It replies with **your chat id**.
2. Add it to the host variables as `MANAGER_CHAT_ID=<that number>` and redeploy.
   (This locks the bot to you and enables the "draft ready" nudge.)
3. Send a couple of test notes, e.g.
   *"replaced two smoke detectors at the Lakehouse, $60 from Home Depot"*.
4. Send **`/list`** to confirm they're stored, then **`/report`**.
5. For Gmail delivery: open **Gmail → Drafts** — your report is waiting,
   addressed to the owners, subject `Property Update — Week of …`. Review and
   send. You'll also get a *"Draft ready for review."* nudge.
6. The automatic compile runs every **Friday 4:00 PM America/Phoenix** (or
   whatever you configured).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Bot doesn't respond | Check Start Command is `python -m app.main`; check logs for missing-config errors. |
| `Configuration problems found` in logs | The log lists exactly which env var is missing/invalid. |
| Notes disappear after a redeploy | You didn't attach a persistent volume/disk, or `DB_PATH` doesn't point at its mount path. |
| Gmail draft not created | Re-check `GMAIL_TOKEN_JSON` is the full one-line token, `OWNER_EMAILS` is set, and the Gmail API is enabled. Re-run `scripts/gmail_auth.py` if the token was revoked. |
| `invalid_grant` / token errors | The refresh token expired or was revoked — re-run `scripts/gmail_auth.py` and update `GMAIL_TOKEN_JSON`. |
| Bot replies "this bot is private" | The chat id doesn't match `MANAGER_CHAT_ID`. Send `/start` to confirm yours. |
| Wrong report time | `TIMEZONE` must be an IANA name (e.g. `America/Phoenix`); restart after changing schedule vars. |
