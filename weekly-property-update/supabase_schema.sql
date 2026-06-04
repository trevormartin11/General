-- Weekly Property Update — Supabase schema (dedicated, schema-per-app).
-- Run once in your project: Dashboard → SQL Editor → New query → paste → Run.
--
-- This keeps the bot's table in its OWN Postgres schema (`property_update`),
-- isolated from the other apps sharing the project. After running this, you
-- must also expose the schema to the API:
--   Dashboard → Settings → API → "Exposed schemas" → add `property_update` → Save.
-- and set the env var  SUPABASE_SCHEMA=property_update  in Vercel.
--
-- The app connects with the service-role key (bypasses RLS), so no RLS policies
-- are needed — just the grants below. Never expose the service-role key to a browser.

create schema if not exists property_update;
grant usage on schema property_update to service_role;

create table if not exists property_update.entries (
    id        bigint generated always as identity primary key,
    ts_epoch  bigint not null,   -- UTC seconds (used for the weekly window)
    ts_utc    text   not null,   -- ISO-8601 UTC timestamp (human/debug)
    raw_text  text   not null,   -- the verbatim note
    chat_id   bigint             -- Telegram chat the note came from
);

create index if not exists entries_ts_epoch_idx
    on property_update.entries (ts_epoch);

-- Privileges for the role the REST API uses.
grant all privileges on all tables in schema property_update to service_role;
grant all privileges on all sequences in schema property_update to service_role;
alter default privileges in schema property_update
    grant all on tables to service_role;
alter default privileges in schema property_update
    grant all on sequences to service_role;
