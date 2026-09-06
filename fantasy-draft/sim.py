"""
Mock-draft simulator: the engine drafts from one or more slots while the other
teams follow ESPN ADP (with a little human-style randomness and sane roster rules).
Used to sanity-check strategy before draft day:  python3 draft.py simulate --slot 7
"""
from __future__ import annotations

import copy
import random
from dataclasses import replace

from brain import (LeagueConfig, Player, Roster, compute_values, eligible_positions, next_pick_after,
                   pick_to_round_slot, picks_for_slot, recommend)


def bot_pick(available: list[Player], roster: Roster, bot_cfg: LeagueConfig, picks_left: int,
             rng: random.Random, reach_sd: float) -> Player:
    roles, _forced = eligible_positions(roster, bot_cfg, picks_left)
    cands = [p for p in available if p.pos in roles]
    if not cands:
        cands = list(available)
    cands.sort(key=lambda p: (p.adp, p.rank, -p.value))
    idx = min(len(cands) - 1, int(abs(rng.gauss(0.0, reach_sd))))
    return cands[idx]


def simulate(pool: list[Player], cfg: LeagueConfig, my_slots: set[int], seed: int = 0,
             targets: set | None = None, avoid: set | None = None) -> tuple[dict, list]:
    rng = random.Random(seed)
    players = compute_values([copy.copy(p) for p in pool], cfg)
    available = {p.id: p for p in players}
    rosters = {s: Roster(cfg) for s in range(1, cfg.teams + 1)}
    bot_cfg = replace(cfg, kdst_picks=5, max_pos={**cfg.max_pos, "QB": min(2, cfg.max_pos.get("QB", 2)),
                                                    "TE": min(2, cfg.max_pos.get("TE", 2))})
    reach = {s: rng.uniform(1.0, 3.5) for s in rosters}
    log = []
    total = cfg.rounds * cfg.teams
    for overall in range(1, total + 1):
        rnd, slot = pick_to_round_slot(overall, cfg.teams)
        roster = rosters[slot]
        picks_left = cfg.rounds - len(roster)
        avail = list(available.values())
        if slot in my_slots:
            nxt = next_pick_after(overall, slot, cfg.teams, cfg.rounds)
            last = picks_for_slot(slot, cfg.teams, cfg.rounds)[-1]
            recs = recommend(avail, roster, cfg, overall, nxt, last, targets, avoid, top=1)
            pick = recs[0].player if recs else avail[0]
        else:
            pick = bot_pick(avail, roster, bot_cfg, picks_left, rng, reach[slot])
        roster.add(pick)
        del available[pick.id]
        log.append((overall, rnd, slot, pick))
    return rosters, log


def report(rosters: dict, my_slots: set[int], log: list | None = None, verbose: bool = False) -> str:
    lines = []
    table = sorted(((s, r.starters_points()) for s, r in rosters.items()), key=lambda x: -x[1])
    lines.append("Projected starting-lineup points by draft slot (higher is better):")
    for rank, (s, pts) in enumerate(table, 1):
        tag = "  <== engine" if s in my_slots else ""
        lines.append(f"  {rank:>2}. slot {s:>2}  {pts:7.1f}{tag}")
    for s in sorted(my_slots):
        r = rosters[s]
        slots, bench = r.lineup()
        lines.append("")
        lines.append(f"Engine roster from slot {s} ({r.starters_points():.1f} projected starter pts):")
        for slot_name, p in slots:
            lines.append(f"  {slot_name:5} {p.label() if p else '(empty)':40} {p.proj if p else 0:6.1f}  bye {p.bye if p else '-'}")
        lines.append("  Bench: " + ", ".join(p.label() for p in bench))
        if log:
            mine = [(o, rd, p) for (o, rd, sl, p) in log if sl == s]
            lines.append("  Picks: " + "; ".join(f"R{rd} #{o} {p.name} ({p.pos}, ADP {p.adp:.0f})" for o, rd, p in mine))
    if verbose and log:
        lines.append("")
        lines.append("Full pick log:")
        for overall, rnd, slot, p in log:
            lines.append(f"  #{overall:>3} R{rnd:<2} slot {slot:>2}  {p.label():38} ADP {p.adp:6.1f}  proj {p.proj:6.1f}")
    return "\n".join(lines)
