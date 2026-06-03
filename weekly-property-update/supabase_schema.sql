-- Weekly Property Update — Supabase schema.
-- Run once in your Supabase project: Dashboard → SQL Editor → New query → paste → Run.
--
-- The app talks to Supabase from the server using the service-role key, which
-- bypasses Row Level Security, so no RLS policies are required. (Leave RLS at
-- its default; just never expose the service-role key to a browser.)

create table if not exists public.entries (
    id        bigint generated always as identity primary key,
    ts_epoch  bigint not null,   -- UTC seconds (used for the weekly window)
    ts_utc    text   not null,   -- ISO-8601 UTC timestamp (human/debug)
    raw_text  text   not null,   -- the verbatim note
    chat_id   bigint             -- Telegram chat the note came from
);

create index if not exists entries_ts_epoch_idx on public.entries (ts_epoch);
