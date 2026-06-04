# DEPLOY-vercel.md — Vercel + Supabase + GitHub (serverless, free)

The "set-and-forget" deployment: a Telegram **webhook** on Vercel, notes stored
in **Supabase**, and the Friday report fired by a scheduled **GitHub Action**.
No server to maintain, $0 on free tiers.

> Already running the Mac version? Leave it for now — but **don't run both at
> once**. Telegram allows *either* polling (the Mac bot) *or* a webhook (Vercel),
> not both. When Vercel is live, stop the Mac bot (`Ctrl-C`). If you ever restart
> the Mac bot, it deletes the webhook — re-run `set_webhook.py` to restore it.

Architecture:

```
 Telegram  ──webhook POST──▶  Vercel /api/telegram  ──▶  Supabase (entries)
                                                            ▲
 GitHub Action (Fri 23:00 UTC) ──POST /api/report──▶  Vercel /api/report
                                          │                 │
                                   Claude (compile)   reads the week
                                          │
                                    Gmail draft  +  Telegram "Draft ready"
```

---

## 0. Things to have ready

- **Telegram bot token** (@BotFather) — you have this.
- **Anthropic API key** (console.anthropic.com).
- **Gmail App Password** (for the draft delivery) — turn on 2-Step Verification
  on the account, then create one at **myaccount.google.com/apppasswords**. No
  Google Cloud project or OAuth needed; the bot drops drafts in via IMAP. You'll
  set `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD`. (Or skip Gmail and use
  `DELIVERY_METHOD=telegram`.)
- **Two random secrets** — make them with:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"   # run twice
  ```
  One is `TELEGRAM_WEBHOOK_SECRET`, the other `REPORT_SECRET`.

---

## 1. Supabase (database)

Sharing one project across apps (schema-per-app)? We won't create a project —
we'll add a dedicated `property_update` schema to your existing one.

1. Open your project (e.g. `trevor-apps`) → **SQL Editor → New query**, paste the
   contents of [`supabase_schema.sql`](supabase_schema.sql), and **Run**. That
   creates the `property_update` schema + `entries` table, isolated from your
   other apps.
2. **Settings → API → "Exposed schemas"** → add **`property_update`** → **Save**.
   (Lets the REST API reach the new schema; `SUPABASE_SCHEMA` must match it.)
3. **Settings → API**, copy two values for Step 2:
   - **Project URL** → `SUPABASE_URL`
   - **`service_role` secret key** → `SUPABASE_SERVICE_KEY`
     (server-side only — never put this in a browser/client.)

> Brand-new dedicated project instead? Same steps — just create it first
> (New project → name → region → DB password).

---

## 2. Vercel (the functions)

1. Push this repo to GitHub (you already have it there).
2. **[vercel.com](https://vercel.com) → Add New → Project → Import** your repo.
3. **Root Directory:** set it to **`weekly-property-update`** (the folder with
   `api/` and `vercel.json`). Framework preset: **Other**. Leave build/output
   empty — Vercel auto-detects the Python functions.
4. **Environment Variables** — add all of these (see
   [`.env.vercel.example`](.env.vercel.example) for the annotated list):
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `MANAGER_CHAT_ID` (leave
   blank for now), `REPORT_SECRET`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`,
   `ANTHROPIC_THINKING`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_SCHEMA`,
   `MANAGER_NAME`, `OWNERS_GREETING`, `OWNER_EMAILS`, `PROPERTIES`, `TIMEZONE`,
   `DELIVERY_METHOD`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`.
5. **Deploy.** When it finishes, note your domain, e.g.
   `https://rowley-property-update.vercel.app`. Your endpoints are
   `…/api/telegram` and `…/api/report`.
6. Quick check: open `…/api/telegram` in a browser — it should say
   "Telegram webhook is up."

> Re-deploy after changing any env var (Vercel only applies them on the next
> deploy): **Deployments → ⋯ → Redeploy**.

---

## 3. Point Telegram at the webhook

Locally (any machine with Python), run:

```bash
TELEGRAM_BOT_TOKEN='your-token' \
WEBHOOK_URL='https://rowley-property-update.vercel.app/api/telegram' \
TELEGRAM_WEBHOOK_SECRET='the-same-webhook-secret-you-set-in-vercel' \
python scripts/set_webhook.py
```

You should see `{"ok":true,"result":true,"description":"Webhook was set"}`.

Now message **@RowleyPropertyUpdateBot**:
- `/start` → it replies with your **chat id**. Put that in Vercel as
  `MANAGER_CHAT_ID` and **redeploy** (locks the bot to you).
- Send a test note → **"✅ Logged."** Check the Supabase **Table Editor** →
  `entries` to see it land.
- `/list` → shows the week's notes. `/report` → compiles + drafts now.

---

## 4. The weekly schedule (GitHub Action)

The workflow is already in the repo at `.github/workflows/weekly-report.yml`
(Friday 16:00 America/Phoenix). Give it the two secrets it needs:

1. GitHub repo → **Settings → Secrets and variables → Actions → New repository
   secret**, add:
   - `REPORT_URL` = `https://rowley-property-update.vercel.app/api/report`
   - `REPORT_SECRET` = the same value you set in Vercel
2. Test it now: **Actions tab → Weekly Property Report → Run workflow**
   (`workflow_dispatch`). Within a few seconds you should get the Gmail draft +
   the "Draft ready for review" Telegram nudge.

> GitHub's scheduled runs can be delayed a few minutes under load — fine for a
> weekly report. Phoenix has no DST, so `0 23 * * 5` stays correct year-round.

---

## 5. Done — how it runs

- **Capture:** every message → Vercel webhook → Supabase. Instant, always on.
- **Weekly report:** Friday 4pm Phoenix → GitHub Action → `/api/report` →
  Claude → Gmail draft → Telegram nudge.
- **On demand:** `/report` in Telegram any time.

### Troubleshooting

| Symptom | Fix |
|---|---|
| Bot silent | Check `getWebhookInfo` (`curl …/getWebhookInfo`) shows your URL and no `last_error`. Re-run `set_webhook.py`. |
| `401 unauthorized` on webhook | `TELEGRAM_WEBHOOK_SECRET` in Vercel ≠ the secret passed to `set_webhook.py`. |
| Notes not saving | Verify `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` and that the schema ran. |
| `/report` errors / Action fails | Check Vercel function logs (Deployments → Logs). Usually a missing `ANTHROPIC_API_KEY`, `GMAIL_TOKEN_JSON`, or `OWNER_EMAILS`. |
| Report times out | Keep `ANTHROPIC_THINKING=off` and `ANTHROPIC_MAX_TOKENS` ≤ 4000 (Vercel free caps functions at 60s). |
| Action 401 | `REPORT_SECRET` mismatch between the GitHub secret and Vercel. |
| Bot stopped after restarting the Mac version | The polling bot deleted the webhook — re-run `set_webhook.py`, and don't run both. |
