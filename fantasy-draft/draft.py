#!/usr/bin/env python3
"""
ESPN fantasy football draft co-pilot.

  python3 draft.py status                  league, teams, draft order, cookie check
  python3 draft.py board                   pre-draft cheat sheet under YOUR league's scoring
  python3 draft.py live                    watch the live draft; prints picks when you're up
  python3 draft.py recommend               one-shot recommendation for the current draft state
  python3 draft.py simulate --slot 7       mock a full draft with the engine in slot 7
  python3 draft.py mock                    offline practice draft (Enter = take the #1 pick)
  python3 draft.py selftest                check Python, tests, ESPN access, cookies, team, mock
  python3 draft.py mark "Player Name"      manual fallback: record a pick made in the room
  python3 draft.py mark --mine "Name"      ... a pick that YOU made

Config: config.json next to this file (copy config.example.json), or env vars
ESPN_S2 / ESPN_SWID / LEAGUE_ID / SEASON. Cookies never leave your machine.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import io
import json
import os
import random
import re
import sys
import time
import unittest
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from espn import AuthError, EspnClient, EspnError, find_my_team, norm_name, parse_league  # noqa: E402
from brain import (LeagueConfig, Player, Roster, best_available, compute_values, next_pick_after,  # noqa: E402
                   pick_to_round_slot, picks_for_slot, recommend)
import sim  # noqa: E402

DEFAULT_LEAGUE_ID = 2072791680
DEFAULT_SEASON = 2026
DEFAULT_CONFIG = os.path.join(HERE, "config.json")
DEFAULT_PICKS_FILE = os.path.join(HERE, "drafted.txt")
CACHE_DIR = os.path.join(HERE, "cache")
# ESPN stat ids used for the scoring sanity check
STAT_PASS_TD, STAT_RECEPTION, STAT_PASS_YDS = 4, 53, 3


# ----------------------------------------------------------------- utilities
def ts() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def load_config(path: str) -> dict:
    cfg = {}
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    env = {"espn_s2": os.environ.get("ESPN_S2"), "swid": os.environ.get("ESPN_SWID") or os.environ.get("SWID"),
           "league_id": os.environ.get("LEAGUE_ID"), "season": os.environ.get("SEASON")}
    for k, v in env.items():
        if v:
            cfg[k] = v
    placeholder = re.compile(r"PASTE|HERE", re.I)
    for k in ("espn_s2", "swid"):
        if cfg.get(k) and placeholder.search(str(cfg[k])):
            cfg[k] = None
    return cfg


def load_names(path: str | None) -> set[str]:
    names: set[str] = set()
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if line:
                    names.add(norm_name(line))
    return names


def find_player(pool: list[Player], text: str) -> Player | None:
    q = norm_name(text)
    if not q:
        return None
    idx = {norm_name(p.name): p for p in pool}
    if q in idx:
        return idx[q]
    q_dst = re.sub(r"\b(dst|d st|defense|def|st)\b", "", q).strip()
    for p in pool:
        if p.pos == "DST":
            nick = norm_name(p.name.replace("D/ST", ""))
            if q_dst == nick or q_dst.endswith(" " + nick):
                return p
    match = difflib.get_close_matches(q, list(idx.keys()), n=1, cutoff=0.82)
    if match:
        return idx[match[0]]
    last = [p for p in pool if norm_name(p.name).split(" ")[-1] == q]
    if len(last) == 1:
        return last[0]
    return None


def build_client(args) -> tuple[EspnClient, dict]:
    cfg = load_config(args.config)
    league_id = int(args.league_id or cfg.get("league_id") or DEFAULT_LEAGUE_ID)
    season = int(args.season or cfg.get("season") or DEFAULT_SEASON)
    client = EspnClient(league_id, season, espn_s2=cfg.get("espn_s2"), swid=cfg.get("swid"),
                        cache_dir=CACHE_DIR, public=bool(args.public))
    return client, cfg


def load_league(client: EspnClient) -> dict:
    return parse_league(client.league())


def load_pool(client: EspnClient, refresh: bool = False, ttl: int = 900) -> list[Player]:
    raw = client.player_pool(use_cache=not refresh, cache_ttl=ttl)
    return [Player.from_dict(d) for d in raw if d.get("pos") in ("QB", "RB", "WR", "TE", "K", "DST")]


def league_config(args, league: dict, cfg_json: dict) -> LeagueConfig:
    kd = args.kdst_picks if getattr(args, "kdst_picks", None) else cfg_json.get("kdst_picks", 3)
    return LeagueConfig.from_espn(league, kdst_picks=int(kd))


def resolve_my_team(args, league: dict, client: EspnClient, cfg_json: dict) -> tuple[dict | None, int | None]:
    """Return (team dict or None, slot or None)."""
    team = None
    team_id = args.team_id or cfg_json.get("team_id")
    if team_id:
        team = next((t for t in league["teams"] if t["id"] == int(team_id)), None)
    if team is None and not client.public:
        team = find_my_team(league, client.swid)
    slot = args.slot or cfg_json.get("slot")
    order = league["draft"]["pick_order"]
    if slot is None and team is not None and order and team["id"] in order:
        slot = order.index(team["id"]) + 1
    if team is None and slot and order and 1 <= int(slot) <= len(order):
        team = next((t for t in league["teams"] if t["id"] == order[int(slot) - 1]), None)
    return team, (int(slot) if slot else None)


def scoring_note(league: dict) -> str:
    sc = league.get("scoring") or {}
    if not sc:
        return "scoring: (not available)"
    return (f"scoring: pass TD = {sc.get(STAT_PASS_TD, '?')}, reception = {sc.get(STAT_RECEPTION, '?')}, "
            f"pass yd = {sc.get(STAT_PASS_YDS, '?')}")


# --------------------------------------------------------------- draft state
class DraftState:
    def __init__(self, cfg: LeagueConfig, players: list[Player], my_team_id: int | None, my_slot: int | None,
                 picks_file: str | None):
        self.cfg = cfg
        self.players = players
        self.by_id = {p.id: p for p in players}
        self.my_team_id = my_team_id
        self.my_slot = my_slot
        self.picks_file = picks_file
        self.league: dict = {}
        self.drafted: dict[int, int | None] = {}
        self.api_picks: list[dict] = []
        self.manual: list[tuple[Player, bool]] = []

    def update(self, league: dict) -> None:
        self.league = league
        self.api_picks = league.get("picks", [])
        drafted: dict[int, int | None] = {}
        for pk in self.api_picks:
            if pk["player_id"] != 0:  # ESPN D/ST ids are negative; 0 = empty pick
                drafted[pk["player_id"]] = pk["team_id"]
        for t in league.get("teams", []):
            for pid in t.get("roster_ids", []):
                drafted.setdefault(pid, t["id"])
        self.manual = []
        if self.picks_file and os.path.exists(self.picks_file):
            with open(self.picks_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.split("#", 1)[0].strip()
                    if not line:
                        continue
                    mine = line.lower().startswith("me:")
                    name = line[3:].strip() if mine else line
                    p = find_player(self.players, name)
                    if p is None:
                        print(f"[{ts()}] WARNING: '{name}' in {os.path.basename(self.picks_file)} matches no player")
                        continue
                    self.manual.append((p, mine))
                    drafted.setdefault(p.id, self.my_team_id if mine else -1)
        self.drafted = drafted

    @property
    def picks_made(self) -> int:
        return max(len(self.api_picks), len(self.drafted))

    @property
    def current_pick(self) -> int:
        return self.picks_made + 1

    @property
    def complete(self) -> bool:
        return self.picks_made >= self.cfg.rounds * self.cfg.teams or bool(self.league.get("draft", {}).get("drafted"))

    def team_name(self, team_id: int | None) -> str:
        if team_id is None or team_id < 0:
            return "?"
        t = next((t for t in self.league.get("teams", []) if t["id"] == team_id), None)
        return t["name"] if t else f"Team {team_id}"

    def team_on_clock(self) -> tuple[int, int, str]:
        rnd, slot = pick_to_round_slot(self.current_pick, self.cfg.teams)
        order = self.league.get("draft", {}).get("pick_order") or []
        name = self.team_name(order[slot - 1]) if len(order) >= slot else f"slot {slot}"
        return rnd, slot, name

    def picks_until_mine(self) -> int | None:
        if not self.my_slot:
            return None
        mine = picks_for_slot(self.my_slot, self.cfg.teams, self.cfg.rounds)
        for p in mine:
            if p >= self.current_pick:
                return p - self.current_pick
        return None

    def my_next_pick(self) -> int | None:
        if not self.my_slot:
            return None
        return next_pick_after(self.current_pick, self.my_slot, self.cfg.teams, self.cfg.rounds)

    def my_roster(self) -> Roster:
        r = Roster(self.cfg)
        for pid, tid in self.drafted.items():
            if self.my_team_id is not None and tid == self.my_team_id and pid in self.by_id:
                r.add(self.by_id[pid])
        if self.my_team_id is None:
            for p, mine in self.manual:
                if mine:
                    r.add(p)
        return r

    def available(self) -> list[Player]:
        return [p for p in self.players if p.id not in self.drafted]

    def format_pick(self, pk: dict) -> str:
        p = self.by_id.get(pk["player_id"])
        who = p.label() if p else f"player #{pk['player_id']}"
        rnd, slot = pick_to_round_slot(pk["overall"], self.cfg.teams) if pk["overall"] else (pk["round"], pk["round_pick"])
        mine = " <== YOU" if self.my_team_id is not None and pk["team_id"] == self.my_team_id else ""
        return f"R{rnd}.{slot:02d} (#{pk['overall']:>3})  {self.team_name(pk['team_id'])[:24]:24} -> {who}{mine}"


# ------------------------------------------------------------------ rendering
def render_panel(state: DraftState, targets: set[str], avoid: set[str], top: int = 8) -> str:
    roster = state.my_roster()
    available = state.available()
    cur = state.current_pick
    rnd, slot = pick_to_round_slot(cur, state.cfg.teams)
    nxt = state.my_next_pick()
    until = state.picks_until_mine()
    lookahead = nxt if (until == 0) else (
        # not on the clock yet: my next pick is the upcoming one; look one further ahead for survival math
        next_pick_after(cur + (until or 0), state.my_slot, state.cfg.teams, state.cfg.rounds) if state.my_slot else None)
    my_pick_no = cur + (until or 0)
    last_pick = picks_for_slot(state.my_slot, state.cfg.teams, state.cfg.rounds)[-1] if state.my_slot else None
    recs = recommend(available, roster, state.cfg, my_pick_no, lookahead, last_pick, targets, avoid, top=top)
    lines = []
    if until == 0:
        head = f"YOU ARE ON THE CLOCK  -  Round {rnd}, pick #{cur}"
    elif until is not None:
        head = f"You pick in {until} pick(s)  -  your next pick is #{my_pick_no} (round {pick_to_round_slot(my_pick_no, state.cfg.teams)[0]})"
    else:
        head = f"Current pick #{cur} (round {rnd}); your slot is unknown - pass --slot N"
    lines.append("=" * 100)
    lines.append(head)
    lines.append("=" * 100)
    lines.append(f"Your roster: {roster.summary()}")
    if lookahead:
        lines.append(f"After this, your following pick is #{lookahead} ({lookahead - my_pick_no} picks later)")
    lines.append("")
    lines.append(f"{'#':>2} {'Player':26} {'Pos':3} {'Tm':3} {'Bye':>3} {'Proj':>6} {'Gain':>6} {'Now+':>5} {'ADP':>6} {'Avail@nxt':>9}  {'Fills':14} Notes")
    for i, r in enumerate(recs, 1):
        p = r.player
        surv = f"{r.survive * 100:4.0f}%" if r.survive is not None else "   -"
        lines.append(f"{i:>2} {p.name[:26]:26} {p.pos:3} {p.team:3} {p.bye:>3} {p.proj:6.1f} {r.gain:6.1f} {r.urgency:5.1f} {p.adp:6.1f} {surv:>9}  {r.role:14} {'; '.join(r.notes)}")
    lines.append("   Gain = projected points over what would fill that slot if you waited until your last pick; Now+ = what waiting one round costs.")
    lines.append("")
    ba = best_available(available, n=4)
    for pos in ("QB", "RB", "WR", "TE", "DST", "K"):
        if pos in ba:
            lines.append(f"  Best {pos:3} left: " + ", ".join(f"{p.name} ({p.proj:.0f})" for p in ba[pos]))
    if recs:
        lines.append("")
        lines.append("Timeout insurance: put " + " / ".join(r.player.name for r in recs[:3]) + " at the top of your ESPN queue.")
    lines.append("=" * 100)
    return "\n".join(lines)


def print_roster(roster: Roster) -> None:
    slots, bench = roster.lineup()
    for slot_name, p in slots:
        print(f"  {slot_name:5} {p.label() if p else '(empty)':40} {p.proj if p else 0:6.1f}  bye {p.bye if p else '-'}")
    print("  Bench: " + (", ".join(p.label() for p in bench) if bench else "(empty)"))
    print(f"  Projected starter points: {roster.starters_points():.1f}")


# ------------------------------------------------------------------- commands
def cmd_status(args) -> int:
    client, cfg_json = build_client(args)
    print(f"League {client.league_id}, season {client.season}, cookies: {'yes' if client.has_cookies else 'NO'}"
          f"{' (public default league mode)' if client.public else ''}")
    league = load_league(client)
    cfg = league_config(args, league, cfg_json)
    d = league["draft"]
    when = dt.datetime.fromtimestamp(d["date_ms"] / 1000).strftime("%a %b %d %I:%M %p") if d.get("date_ms") else "?"
    print(f"Name: {league['name']}")
    print(f"Format: {cfg.describe()}")
    print(scoring_note(league))
    print(f"Draft: {d['type']} | {when} | {d['seconds_per_pick']}s per pick | in progress: {d['in_progress']} | done: {d['drafted']}")
    team, slot = resolve_my_team(args, league, client, cfg_json)
    order = d["pick_order"]
    print("Teams / draft order:")
    for t in sorted(league["teams"], key=lambda t: (order.index(t["id"]) + 1) if t["id"] in order else 99):
        owners = ", ".join(league["members"].get(o, o) for o in t["owners"]) or "-"
        s = f"slot {order.index(t['id']) + 1:>2}" if t["id"] in order else "slot  ?"
        me = "  <== you" if team and t["id"] == team["id"] else ""
        print(f"  {s}  id {t['id']:>3}  {t['name'][:30]:30}  owners: {owners}{me}")
    if team:
        print(f"You: {team['name']} (team id {team['id']}), draft slot {slot if slot else 'unknown (order not set yet)'}")
    else:
        print("Could not tell which team is yours. Set \"team_id\" or \"slot\" in config.json, or pass --team-id / --slot.")
    print(f"Picks recorded so far: {len(league['picks'])}")
    return 0


def cmd_board(args) -> int:
    client, cfg_json = build_client(args)
    league = load_league(client)
    cfg = league_config(args, league, cfg_json)
    players = compute_values(load_pool(client, refresh=args.refresh), cfg)
    print(f"{league['name']} - {cfg.describe()}")
    print(scoring_note(league))
    print("Value = 65% ESPN projection (league scoring) + 35% market view; VOR = value over replacement.\n")
    print(f"{'#':>3} {'Player':26} {'Pos':3} {'Tm':3} {'Bye':>3} {'Proj':>6} {'VOR':>6} {'ADP':>6} {'Tier':>4} Inj")
    shown = 0
    for p in players:
        if p.pos in ("K", "DST"):
            continue
        shown += 1
        if shown > args.top:
            break
        print(f"{shown:>3} {p.name[:26]:26} {p.pos:3} {p.team:3} {p.bye:>3} {p.proj:6.1f} {p.vor:6.1f} {p.adp:6.1f} {p.pos}{p.tier:<3} {p.injury if p.injured else ''}")
    print("\nBy position (top 12):")
    by_pos: dict[str, list[Player]] = {}
    for p in players:
        by_pos.setdefault(p.pos, []).append(p)
    for pos in ("QB", "RB", "WR", "TE", "DST", "K"):
        row = by_pos.get(pos, [])[:12]
        print(f"  {pos:3}: " + ", ".join(f"{p.name} {p.vor:.0f}" for p in row))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["overall_rank", "name", "pos", "team", "bye", "proj", "value", "vor", "adp", "espn_rank", "tier", "injury"])
            for i, p in enumerate(players, 1):
                w.writerow([i, p.name, p.pos, p.team, p.bye, f"{p.proj:.1f}", f"{p.value:.1f}", f"{p.vor:.1f}", p.adp, p.rank, p.tier, p.injury])
        print(f"\nWrote {args.csv}")
    if args.queue_file:
        with open(args.queue_file, "w", encoding="utf-8") as f:
            for p in players:
                if p.pos not in ("K", "DST"):
                    f.write(p.name + "\n")
            for pos in ("DST", "K"):
                for p in by_pos.get(pos, [])[:6]:
                    f.write(p.name + "\n")
        print(f"Wrote {args.queue_file} (names in draft order, for the ESPN queue / custom rankings)")
    return 0


def _prepare_state(args) -> tuple[EspnClient, DraftState, set[str], set[str], dict]:
    client, cfg_json = build_client(args)
    league = load_league(client)
    cfg = league_config(args, league, cfg_json)
    players = compute_values(load_pool(client, refresh=args.refresh), cfg)
    team, slot = resolve_my_team(args, league, client, cfg_json)
    picks_file = args.picks_file or (DEFAULT_PICKS_FILE if os.path.exists(DEFAULT_PICKS_FILE) else None)
    state = DraftState(cfg, players, team["id"] if team else None, slot, picks_file)
    state.update(league)
    targets = load_names(args.targets or os.path.join(HERE, "targets.txt"))
    avoid = load_names(args.avoid or os.path.join(HERE, "avoid.txt"))
    print(f"[{ts()}] {league['name']} | {cfg.describe()}")
    print(f"[{ts()}] {scoring_note(league)}")
    print(f"[{ts()}] You: {team['name'] if team else 'unknown team'} | slot {slot or '?'} | "
          f"{len(players)} players loaded | targets {len(targets)} | avoid {len(avoid)}"
          + (f" | manual picks file: {picks_file}" if picks_file else ""))
    return client, state, targets, avoid, cfg_json


def cmd_recommend(args) -> int:
    _client, state, targets, avoid, _ = _prepare_state(args)
    if state.api_picks:
        print(f"[{ts()}] Last pick: {state.format_pick(state.api_picks[-1])}")
    print(render_panel(state, targets, avoid, top=args.top))
    return 0



def auto_make_pick(state: DraftState, client: EspnClient, auto, targets: set[str], avoid: set[str], args) -> bool:
    """
    Automation mode: try to submit the best pick in the draft room and confirm
    it via ESPN's API. Retries while the clock allows (ESPN shows the Draft
    button a few seconds after the API says you're up), moves to the next
    candidate if a submitted pick isn't confirmed. Returns True if confirmed.
    """
    pick_no = state.current_pick
    deadline = time.time() + args.pick_deadline
    tried: set[int] = set()
    attempt = 0
    while time.time() < deadline:
        roster = state.my_roster()
        last_pick = picks_for_slot(state.my_slot, state.cfg.teams, state.cfg.rounds)[-1]
        recs = [r for r in recommend(state.available(), roster, state.cfg, pick_no, state.my_next_pick(), last_pick,
                                     targets, avoid, top=6) if r.player.id not in tried]
        if not recs:
            break
        attempt += 1
        cand = recs[0]
        print(f"[{ts()}] [auto] attempt {attempt}: {cand.player.name}")
        submitted = auto.pick([cand])
        if args.dry_run:
            return submitted
        if not submitted:
            time.sleep(2)  # button not there yet? poll and retry the same candidate
            try:
                state.update(load_league(client))
            except EspnError:
                pass
            if state.current_pick > pick_no:
                print(f"[{ts()}] [auto] pick #{pick_no} is already made (ESPN autopick or you clicked).")
                return True
            continue
        tried.add(cand.player.id)
        confirm_by = time.time() + args.confirm_seconds
        while time.time() < confirm_by:
            time.sleep(2)
            try:
                state.update(load_league(client))
            except EspnError:
                continue
            if state.current_pick > pick_no:
                print(f"[{ts()}] [auto] ESPN confirmed the pick.")
                return True
        print(f"[{ts()}] [auto] not confirmed after {args.confirm_seconds}s; trying the next option")
    print(f"[{ts()}] [auto] gave up on pick #{pick_no}; ESPN's queue/timer takes over.")
    return False


def cmd_live(args) -> int:
    client, state, targets, avoid, _ = _prepare_state(args)
    if not state.my_slot:
        print("Your draft slot is unknown. Once the league manager sets the order it is detected automatically; "
              "or pass --slot N. Continuing in watch-only mode.")
    auto = None
    if args.auto:
        import auto_click
        auto = auto_click.AutoClicker(dry_run=args.dry_run, cdp_url=args.cdp_url)
        print(f"[{ts()}] AUTO-CLICK {'DRY RUN ' if args.dry_run else ''}enabled: {auto.describe()}")
    last_n = -1
    last_wait_msg = 0.0
    last_pool_refresh = time.time()
    shown_for_pick = -1
    while True:
        try:
            league = load_league(client)
            state.update(league)
        except AuthError as e:
            print(f"[{ts()}] {e}")
            return 2
        except EspnError as e:
            print(f"[{ts()}] ESPN error (will retry): {e}")
            time.sleep(args.interval)
            continue
        except KeyboardInterrupt:
            print("\nStopped.")
            return 0
        n = state.picks_made
        d = league["draft"]
        if n == 0 and not d["in_progress"]:
            if time.time() - last_wait_msg > 30:
                when = dt.datetime.fromtimestamp(d["date_ms"] / 1000).strftime("%I:%M %p") if d.get("date_ms") else "?"
                print(f"[{ts()}] Waiting for the draft to start (scheduled {when}). Polling every {args.interval}s...")
                last_wait_msg = time.time()
        if n != last_n:
            for pk in state.api_picks[max(last_n, 0):]:
                print(f"[{ts()}] {state.format_pick(pk)}")
            if len(state.api_picks) < n and last_n >= 0:
                print(f"[{ts()}] ({n - len(state.api_picks)} manual picks from {os.path.basename(state.picks_file or '')})")
            last_n = n
            if state.complete:
                print(f"[{ts()}] Draft complete. Your final roster:")
                print_roster(state.my_roster())
                return 0
            until = state.picks_until_mine()
            rnd, _slot, name = state.team_on_clock()
            print(f"[{ts()}] On the clock: {name} (round {rnd}, pick #{state.current_pick})"
                  + (f" - you are up in {until} pick(s)" if until else ""))
            if until is not None and until <= args.warn and shown_for_pick != state.current_pick:
                shown_for_pick = state.current_pick
                print(render_panel(state, targets, avoid, top=args.top))
                if until == 0:
                    if not args.no_beep:
                        sys.stdout.write("\a\a")
                        sys.stdout.flush()
                    if auto:
                        auto_make_pick(state, client, auto, targets, avoid, args)
        if time.time() - last_pool_refresh > args.pool_refresh:
            try:
                fresh = compute_values(load_pool(client, refresh=True), state.cfg)
                state.players = fresh
                state.by_id = {p.id: p for p in fresh}
                last_pool_refresh = time.time()
                print(f"[{ts()}] Player pool refreshed (injury/projection updates).")
            except EspnError as e:
                print(f"[{ts()}] Pool refresh failed (keeping old pool): {e}")
                last_pool_refresh = time.time()
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
            return 0


def cmd_simulate(args) -> int:
    client, cfg_json = build_client(args)
    league = load_league(client)
    cfg = league_config(args, league, cfg_json)
    pool = load_pool(client, refresh=args.refresh)
    targets = load_names(args.targets or os.path.join(HERE, "targets.txt"))
    avoid = load_names(args.avoid or os.path.join(HERE, "avoid.txt"))
    print(f"{league['name']} - {cfg.describe()} | {scoring_note(league)}")
    slots = set(args.slots or [])
    if not slots:
        _team, slot = resolve_my_team(args, league, client, cfg_json)
        slots = {slot} if slot else {1}
    if args.all:
        ranks = []
        for s in range(1, cfg.teams + 1):
            rosters, _log = sim.simulate(pool, cfg, {s}, seed=args.seed, targets=targets, avoid=avoid)
            table = sorted(rosters, key=lambda k: -rosters[k].starters_points())
            ranks.append(table.index(s) + 1)
            print(f"  slot {s:>2}: engine finished #{ranks[-1]} of {cfg.teams} ({rosters[s].starters_points():.1f} pts)")
        print(f"Average finish across all slots: {sum(ranks) / len(ranks):.2f} (1 = best)")
        return 0
    rosters, log = sim.simulate(pool, cfg, slots, seed=args.seed, targets=targets, avoid=avoid)
    print(sim.report(rosters, slots, log, verbose=args.verbose))
    return 0


def cmd_mark(args) -> int:
    client, cfg_json = build_client(args)
    league = load_league(client)
    cfg = league_config(args, league, cfg_json)
    pool = compute_values(load_pool(client), cfg)
    path = args.picks_file or DEFAULT_PICKS_FILE
    for name in args.names:
        p = find_player(pool, name)
        if p is None:
            print(f"No match for '{name}'. Try the full name as ESPN shows it.")
            return 1
        with open(path, "a", encoding="utf-8") as f:
            f.write(("me: " if args.mine else "") + p.name + "\n")
        print(f"Recorded {'YOUR pick' if args.mine else 'pick'}: {p.label()}  -> {path}")
    return 0


def cmd_unmark(args) -> int:
    path = args.picks_file or DEFAULT_PICKS_FILE
    if not os.path.exists(path):
        print("Nothing recorded.")
        return 0
    with open(path, "r", encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    if not lines:
        print("Nothing recorded.")
        return 0
    removed = lines.pop()
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    print(f"Removed: {removed}")
    return 0



# ------------------------------------------------------------ mock draft mode
def run_mock(client: EspnClient, cfg_json: dict, args, slot: int | None = None, seed: int = 1, pace: float = 3.0,
             auto: bool = False, fast: bool = False, quiet: bool = False, top: int = 8) -> tuple[Roster, dict]:
    """
    Offline practice draft that looks exactly like draft day: the other teams
    follow ESPN ADP (with some randomness) at `pace` seconds per pick, and
    when it's your turn the same panel appears. Press Enter to take the #1
    recommendation, type a name to pick someone else, or use --auto.
    """
    league = load_league(client)
    cfg = league_config(args, league, cfg_json)
    players = compute_values(load_pool(client, refresh=getattr(args, "refresh", False)), cfg)
    targets = load_names(getattr(args, "targets", None) or os.path.join(HERE, "targets.txt"))
    avoid = load_names(getattr(args, "avoid", None) or os.path.join(HERE, "avoid.txt"))
    rng = random.Random(seed)
    slot = int(slot) if slot else rng.randint(1, cfg.teams)
    team_ids = [1000 + i for i in range(1, cfg.teams + 1)]
    teams = [{"id": tid, "name": ("YOU (mock)" if i == slot else f"Mock Team {i}"), "abbrev": "", "owners": [],
              "roster_ids": []} for i, tid in enumerate(team_ids, 1)]
    my_id = team_ids[slot - 1]
    fake = {"name": "Practice draft (offline mock)", "size": cfg.teams, "lineup_slot_counts": league["lineup_slot_counts"],
            "position_limits": league["position_limits"], "scoring": league.get("scoring", {}),
            "draft": {"type": "SNAKE", "pick_order": team_ids, "seconds_per_pick": 60, "date_ms": None,
                      "in_progress": True, "drafted": False},
            "teams": teams, "members": {}, "picks": []}
    state = DraftState(cfg, players, my_id, slot, None)
    state.update(fake)
    bot_cfg = replace(cfg, kdst_picks=5, max_pos={**cfg.max_pos, "QB": min(2, cfg.max_pos.get("QB", 2)),
                                                    "TE": min(2, cfg.max_pos.get("TE", 2))})
    rosters = {s: Roster(cfg) for s in range(1, cfg.teams + 1)}
    reach = {s: rng.uniform(1.0, 3.5) for s in rosters}
    out = (lambda *a, **k: None) if quiet else print
    total = cfg.rounds * cfg.teams
    my_last = picks_for_slot(slot, cfg.teams, cfg.rounds)[-1]
    out(f"[{ts()}] PRACTICE DRAFT (offline) | {cfg.describe()} | {scoring_note(league)}")
    out(f"[{ts()}] You are slot {slot} of {cfg.teams}. Other teams draft by ADP every {0 if fast else pace}s. "
        f"{'Your picks are automatic.' if auto or fast else 'On your turn: Enter = take #1, or type a name.'}")
    for overall in range(1, total + 1):
        rnd, s = pick_to_round_slot(overall, cfg.teams)
        available = state.available()
        if s == slot:
            out(render_panel(state, targets, avoid, top=top))
            recs = recommend(available, state.my_roster(), cfg, overall,
                             next_pick_after(overall, slot, cfg.teams, cfg.rounds), my_last, targets, avoid, top=1)
            default = recs[0].player if recs else available[0]
            pick = None
            if auto or fast:
                pick = default
                if not fast:
                    time.sleep(min(pace, 1.5))
            else:
                if not getattr(args, "no_beep", False):
                    sys.stdout.write("\a")
                while pick is None:
                    try:
                        text = input(f"Your pick (Enter = {default.name}; or type a name; q = quit): ").strip()
                    except EOFError:
                        text = ""
                    if text.lower() == "q":
                        raise KeyboardInterrupt
                    if not text:
                        pick = default
                        break
                    cand = find_player(available, text)
                    if cand is None:
                        print("  No available player matches that. Try again.")
                        continue
                    pick = cand
        else:
            picks_left = cfg.rounds - len(rosters[s])
            pick = sim.bot_pick(available, rosters[s], bot_cfg, picks_left, rng, reach[s])
            if not fast:
                time.sleep(pace)
        rosters[s].add(pick)
        fake["picks"].append({"overall": overall, "round": rnd, "round_pick": (overall - 1) % cfg.teams + 1,
                              "team_id": team_ids[s - 1], "player_id": pick.id, "auto": 0})
        state.update(fake)
        out(f"[{ts()}] {state.format_pick(fake['picks'][-1])}")
    mine = state.my_roster()
    if not quiet:
        print(f"\n[{ts()}] Practice draft complete. Your roster:")
        print_roster(mine)
        table = sorted(rosters, key=lambda k: -rosters[k].starters_points())
        print(f"  Projected starters rank: #{table.index(slot) + 1} of {cfg.teams}")
    return mine, rosters


def cmd_mock(args) -> int:
    client, cfg_json = build_client(args)
    slot = args.slot
    if slot is None:
        try:
            league = load_league(client)
            _team, slot = resolve_my_team(args, league, client, cfg_json)
        except EspnError:
            slot = None
    try:
        run_mock(client, cfg_json, args, slot=slot, seed=args.seed, pace=args.pace, auto=args.auto, fast=args.fast,
                 top=args.top)
    except KeyboardInterrupt:
        print("\nPractice draft stopped.")
    return 0


# ------------------------------------------------------------------ selftest
def cmd_selftest(args) -> int:
    """Check Python, unit tests, ESPN access, cookies/league/team, player pool, simulation, and a fast mock draft."""
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(': ' + detail) if detail else ''}")

    print(f"Self-test started {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} in {HERE}")
    v = sys.version_info
    check("Python 3.9+", (v.major, v.minor) >= (3, 9), f"{v.major}.{v.minor}.{v.micro}")

    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(os.path.join(HERE, "tests"))
    res = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    check("Offline unit tests", res.wasSuccessful() and res.testsRun > 0,
          f"{res.testsRun} tests, {len(res.failures)} failures, {len(res.errors)} errors")
    if not res.wasSuccessful():
        print(stream.getvalue()[-2000:])

    cfg_json = load_config(args.config)
    league_id = int(args.league_id or cfg_json.get("league_id") or DEFAULT_LEAGUE_ID)
    season = int(args.season or cfg_json.get("season") or DEFAULT_SEASON)
    public = EspnClient(league_id, season, cache_dir=CACHE_DIR, public=True)
    try:
        teams = public.pro_teams()
        check("Internet access to ESPN", len(teams) >= 32, f"{len(teams)} NFL teams loaded")
    except EspnError as e:
        check("Internet access to ESPN", False, str(e)[:200])

    real = EspnClient(league_id, season, espn_s2=cfg_json.get("espn_s2"), swid=cfg_json.get("swid"),
                      cache_dir=CACHE_DIR, public=False)
    client_for_pool = public
    league = None
    slot = None
    if not real.has_cookies:
        check("ESPN cookies in config.json", False,
              "not set yet - copy config.example.json to config.json and paste espn_s2 + SWID (README 'Cookies')")
    else:
        try:
            league = load_league(real)
            sc = league.get("scoring") or {}
            check("Private league reachable with your cookies", True,
                  f"'{league['name']}', {league['size']} teams, pass TD = {sc.get(STAT_PASS_TD)}, reception = {sc.get(STAT_RECEPTION)}")
            d = league["draft"]
            check("Draft settings", d["type"] == "SNAKE",
                  f"{d['type']}, {d['seconds_per_pick']}s per pick, order {'set' if d['pick_order'] else 'NOT SET YET'}")
            team, slot = resolve_my_team(args, league, real, cfg_json)
            check("Your team detected", team is not None,
                  (f"{team['name']} (team id {team['id']}), slot {slot or 'unknown until the order is set'}" if team
                   else "set team_id or slot in config.json (see 'python3 draft.py status')"))
            client_for_pool = real
        except AuthError as e:
            check("Private league reachable with your cookies", False, str(e).splitlines()[0])
        except EspnError as e:
            check("Private league reachable with your cookies", False, str(e)[:200])
    if league is None:
        try:
            league = load_league(public)
        except EspnError as e:
            print(f"Cannot continue without league settings: {e}")
            return 1
    cfg = LeagueConfig.from_espn(league, kdst_picks=int(cfg_json.get("kdst_picks", 3)))
    try:
        pool = load_pool(client_for_pool, refresh=args.refresh)
        top = sorted(pool, key=lambda p: p.rank)[:3]
        check("Player pool with projections", len(pool) >= 300 and all(p.proj > 0 for p in top),
              f"{len(pool)} players{' (league scoring)' if client_for_pool is real else ' (ESPN public defaults; cookies not used)'}; "
              f"top: {', '.join(p.name for p in top)}")
    except EspnError as e:
        check("Player pool with projections", False, str(e)[:200])
        pool = []
    if pool:
        s = slot or 1
        rosters, _log = sim.simulate(pool, cfg, {s}, seed=1)
        r = rosters[s]
        legal = len(r) == cfg.rounds and sum(r.open_starters().values()) == 0 and r.count("K") == 1 and r.count("DST") == 1
        table = sorted(rosters, key=lambda k: -rosters[k].starters_points())
        check("Simulated draft builds a legal roster", legal,
              f"slot {s}: {len(r)} players, finished #{table.index(s) + 1} of {cfg.teams} by projected starters")
        try:
            mine, _ = run_mock(client_for_pool, cfg_json, args, slot=s, seed=2, fast=True, auto=True, quiet=True)
            legal = len(mine) == cfg.rounds and sum(mine.open_starters().values()) == 0
            check("Live-draft machinery (fast offline mock)", legal, f"{len(mine)} picks tracked for your team")
        except Exception as e:  # noqa: BLE001
            check("Live-draft machinery (fast offline mock)", False, f"{type(e).__name__}: {e}")
    failed = [n for n, ok, _ in results if not ok]
    print()
    if failed:
        print(f"RESULT: {len(failed)} check(s) need attention: {', '.join(failed)}")
        return 1
    print("RESULT: all checks passed. At draft time run start_live.command / start_live.bat (or: python3 draft.py live).")
    return 0


# ----------------------------------------------------------------------- main
def main(argv=None) -> int:
    try:  # live output must show up immediately even when piped (e.g. run from Claude Code)
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=DEFAULT_CONFIG, help="path to config.json")
    common.add_argument("--public", action="store_true", help="use ESPN's public default PPR league (no cookies; testing only)")
    common.add_argument("--league-id", type=int)
    common.add_argument("--season", type=int)
    common.add_argument("--slot", dest="slots", type=int, action="append",
                        help="your draft slot (1 = first pick of round 1); simulate accepts it more than once")
    common.add_argument("--team-id", type=int, help="your ESPN team id (see status)")
    common.add_argument("--picks-file", help="manual fallback file of drafted players (see 'mark')")
    common.add_argument("--targets", help="file of players to favor (default targets.txt)")
    common.add_argument("--avoid", help="file of players never to recommend (default avoid.txt)")
    common.add_argument("--kdst-picks", type=int, help="only consider K/DST within the last N picks (default 3)")
    common.add_argument("--refresh", action="store_true", help="ignore the cached player pool")

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="command")

    sub.add_parser("status", parents=[common], help="league, teams, draft order, cookie check").set_defaults(fn=cmd_status)

    b = sub.add_parser("board", parents=[common], help="pre-draft cheat sheet")
    b.add_argument("--top", type=int, default=150)
    b.add_argument("--csv", help="also write the full board to this CSV")
    b.add_argument("--queue-file", help="write player names in draft order (for ESPN queue / rankings)")
    b.set_defaults(fn=cmd_board)

    r = sub.add_parser("recommend", parents=[common], help="one-shot recommendation for the current draft state")
    r.add_argument("--top", type=int, default=8)
    r.set_defaults(fn=cmd_recommend)

    l = sub.add_parser("live", parents=[common], help="watch the live draft and recommend picks")
    l.add_argument("--interval", type=float, default=4.0, help="seconds between ESPN polls")
    l.add_argument("--warn", type=int, default=2, help="show the panel when you are within N picks")
    l.add_argument("--top", type=int, default=8)
    l.add_argument("--no-beep", action="store_true")
    l.add_argument("--pool-refresh", type=int, default=900, help="seconds between player-pool refreshes")
    l.add_argument("--auto", action="store_true", help="EXPERIMENTAL: click the pick in the ESPN draft room")
    l.add_argument("--dry-run", action="store_true", help="with --auto: search and highlight, but do not click Draft")
    l.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="Chrome remote-debugging URL for --auto")
    l.add_argument("--confirm-seconds", type=int, default=12, help="with --auto: how long to wait for ESPN to register a submitted pick")
    l.add_argument("--pick-deadline", type=int, default=45, help="with --auto: stop retrying this many seconds after your turn starts")
    l.set_defaults(fn=cmd_live)

    s = sub.add_parser("simulate", parents=[common], help="mock draft against ADP bots (--slot may repeat)")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--all", action="store_true", help="run every slot separately and summarize")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(fn=cmd_simulate)

    k = sub.add_parser("mock", parents=[common], help="offline practice draft that looks like draft day")
    k.add_argument("--pace", type=float, default=3.0, help="seconds per other-team pick (default 3)")
    k.add_argument("--auto", action="store_true", help="make your picks automatically (engine #1)")
    k.add_argument("--fast", action="store_true", help="no delays, automatic picks (smoke test)")
    k.add_argument("--seed", type=int, default=1)
    k.add_argument("--top", type=int, default=8)
    k.add_argument("--no-beep", action="store_true")
    k.set_defaults(fn=cmd_mock)

    t = sub.add_parser("selftest", parents=[common], help="check Python, tests, ESPN access, cookies, team, and a fast mock")
    t.set_defaults(fn=cmd_selftest)

    m = sub.add_parser("mark", parents=[common], help="manual fallback: record a pick made in the draft room")
    m.add_argument("names", nargs="+")
    m.add_argument("--mine", action="store_true", help="the pick was yours")
    m.set_defaults(fn=cmd_mark)

    u = sub.add_parser("unmark", parents=[common], help="remove the last manually recorded pick")
    u.set_defaults(fn=cmd_unmark)

    args = ap.parse_args(argv)
    args.slot = (args.slots or [None])[0]
    try:
        return args.fn(args)
    except AuthError as e:
        print(f"ERROR: {e}")
        return 2
    except EspnError as e:
        print(f"ERROR: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
