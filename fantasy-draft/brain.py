"""
Draft decision engine.

Value model (per player, computed once):
  value = injury_mult * (0.65 * ESPN projected season points under league scoring
                         + 0.35 * projected points of the player the *market* (ADP)
                                  thinks he is at his position)
  VOR   = value - value of the classic replacement-level player at his position
          (worst starter league-wide incl. a flex share, plus a small bench
           allowance). Used for the pre-draft board and tiers.

Pick score (per available player, given my roster and pick position):
  floor[pos]  = expected value of the best player at that position who will
                still be there at my LAST pick (ADP survival odds) - i.e. what
                I would get if I punted the slot to the end of the draft.
  v_next[pos] = expected value of the best player at that position who will
                still be there at my NEXT pick.
  gain    = value - floor[pos]                       (real gain vs punting)
  urgency = max(0, value - v_next[pos])              (what waiting a round costs)
  score   = (gain + 0.5 * urgency) * role_factor * preference_mult
            role_factor = 1.0 for an open starting slot (incl. FLEX),
                          0.40 RB / 0.35 WR / 0.15 TE / 0.15 QB for bench depth,
                          shrinking 20% for each extra backup already at that position
Hard rules: position maximums, never a 2nd K/DST, K/DST only in the last
`kdst_picks` picks (unless forced), and a forced-fill guard so every starting
slot gets filled before the draft ends.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

STARTER_POSITIONS = ("QB", "RB", "WR", "TE", "DST", "K")
FLEX_SHARE = {"RB": 0.45, "WR": 0.50, "TE": 0.05}
BASELINE_EXTRA = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 0, "DST": 0}
TIER_WIDTH = {"QB": 22.0, "RB": 22.0, "WR": 22.0, "TE": 18.0, "K": 8.0, "DST": 8.0}
INJURY_MULT = {"OUT": 0.6, "INJURY_RESERVE": 0.55, "SUSPENSION": 0.7, "DOUBTFUL": 0.9}
BENCH_FACTOR = {"RB": 0.40, "WR": 0.35, "TE": 0.15, "QB": 0.15, "K": 0.0, "DST": 0.0}
MARKET_BLEND = 0.35
URGENCY_WEIGHT = 0.5
TARGET_MULT = 1.08


@dataclass
class Player:
    id: int
    name: str
    pos: str
    team: str = "FA"
    bye: int = 0
    proj: float = 0.0
    adp: float = 999.0
    rank: int = 999
    injury: str = "ACTIVE"
    value: float = 0.0
    vor: float = 0.0
    pos_rank: int = 0
    market_rank: int = 0
    tier: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "Player":
        return cls(id=int(d["id"]), name=d["name"], pos=d["pos"], team=d.get("team", "FA"), bye=int(d.get("bye") or 0),
                   proj=float(d.get("proj") or 0.0), adp=float(d.get("adp") or 999.0), rank=int(d.get("rank") or 999),
                   injury=d.get("injury") or "ACTIVE")

    @property
    def injured(self) -> bool:
        return self.injury in INJURY_MULT

    def label(self) -> str:
        return f"{self.name} ({self.pos}, {self.team})"


@dataclass
class LeagueConfig:
    teams: int = 12
    starters: dict = field(default_factory=lambda: {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "DST": 1, "K": 1})
    bench: int = 6
    max_pos: dict = field(default_factory=lambda: {"QB": 2, "RB": 8, "WR": 8, "TE": 3, "K": 3, "DST": 3})
    flex_positions: tuple = ("RB", "WR", "TE")
    kdst_picks: int = 3  # K/DST only eligible within the last N picks (unless forced)

    @property
    def rounds(self) -> int:
        return sum(self.starters.values()) + self.bench

    @classmethod
    def from_espn(cls, league: dict, kdst_picks: int = 3) -> "LeagueConfig":
        from espn import SLOT_BY_ID, FLEX_SLOT_ELIGIBLE, POS_BY_ID
        counts = league.get("lineup_slot_counts") or {}
        starters = {p: 0 for p in STARTER_POSITIONS}
        starters["FLEX"] = 0
        bench = 0
        flex_pos: set = set()
        for slot_id, n in counts.items():
            if n <= 0:
                continue
            name = SLOT_BY_ID.get(slot_id)
            if name in STARTER_POSITIONS:
                starters[name] += n
            elif name == "BE":
                bench += n
            elif slot_id in FLEX_SLOT_ELIGIBLE:
                starters["FLEX"] += n
                flex_pos.update(FLEX_SLOT_ELIGIBLE[slot_id])
            # IR (21) and unknown slots are ignored: they are not draft picks.
        limits = league.get("position_limits") or {}
        max_pos = {}
        for pid, pos in POS_BY_ID.items():
            lim = limits.get(pid, -1)
            max_pos[pos] = 99 if lim is None or lim < 0 else int(lim)
            if max_pos[pos] == 0:  # ESPN uses 0 for "no limit" in some payloads
                max_pos[pos] = 99
        teams = int(league.get("size") or len(league.get("teams") or []) or 12)
        return cls(teams=teams, starters=starters, bench=bench, max_pos=max_pos,
                   flex_positions=tuple(sorted(flex_pos)) or ("RB", "WR", "TE"), kdst_picks=kdst_picks)

    def describe(self) -> str:
        st = ", ".join(f"{k}x{v}" for k, v in self.starters.items() if v)
        return f"{self.teams} teams | starters: {st} | bench {self.bench} | {self.rounds} rounds"


# ------------------------------------------------------------------ snake math
def pick_to_round_slot(overall: int, teams: int) -> tuple[int, int]:
    rnd = (overall - 1) // teams + 1
    idx = (overall - 1) % teams
    slot = idx + 1 if rnd % 2 == 1 else teams - idx
    return rnd, slot


def picks_for_slot(slot: int, teams: int, rounds: int) -> list[int]:
    out = []
    for rnd in range(1, rounds + 1):
        pos = slot if rnd % 2 == 1 else teams - slot + 1
        out.append((rnd - 1) * teams + pos)
    return out


def next_pick_after(current_overall: int, slot: int, teams: int, rounds: int) -> int | None:
    for p in picks_for_slot(slot, teams, rounds):
        if p > current_overall:
            return p
    return None


# --------------------------------------------------------------------- values
def replacement_ranks(cfg: LeagueConfig) -> dict:
    out = {}
    for pos in STARTER_POSITIONS:
        n = cfg.teams * cfg.starters.get(pos, 0)
        if pos in cfg.flex_positions:
            n += cfg.teams * cfg.starters.get("FLEX", 0) * FLEX_SHARE.get(pos, 0.0)
        out[pos] = max(1, int(round(n + BASELINE_EXTRA.get(pos, 0))))
    return out


def compute_values(players: list[Player], cfg: LeagueConfig) -> list[Player]:
    """Fill value / vor / pos_rank / market_rank / tier on every player. Returns players sorted by vor desc."""
    by_pos: dict[str, list[Player]] = {}
    for p in players:
        by_pos.setdefault(p.pos, []).append(p)
    repl = replacement_ranks(cfg)
    for pos, group in by_pos.items():
        # market view: rank within position by ADP (then ESPN rank)
        mkt = sorted(group, key=lambda p: (p.adp, p.rank))
        for i, p in enumerate(mkt, 1):
            p.market_rank = i
        proj_sorted = sorted((p.proj for p in group), reverse=True)
        for p in group:
            m = min(p.market_rank, len(proj_sorted)) - 1
            market_value = proj_sorted[m]
            blended = (1 - MARKET_BLEND) * p.proj + MARKET_BLEND * market_value
            p.value = blended * INJURY_MULT.get(p.injury, 1.0)
        ranked = sorted(group, key=lambda p: -p.value)
        r = repl.get(pos, len(ranked))
        baseline = ranked[min(r, len(ranked)) - 1].value if ranked else 0.0
        tier, top = 1, ranked[0].value if ranked else 0.0
        for i, p in enumerate(ranked, 1):
            p.pos_rank = i
            p.vor = p.value - baseline
            if top - p.value > TIER_WIDTH.get(pos, 20.0):
                tier += 1
                top = p.value
            p.tier = tier
    return sorted(players, key=lambda p: -p.vor)


# --------------------------------------------------------------------- roster
class Roster:
    def __init__(self, cfg: LeagueConfig):
        self.cfg = cfg
        self.players: list[Player] = []

    def add(self, p: Player) -> None:
        self.players.append(p)

    def __len__(self) -> int:
        return len(self.players)

    def count(self, pos: str) -> int:
        return sum(1 for p in self.players if p.pos == pos)

    def open_starters(self) -> dict:
        cfg = self.cfg
        open_ = {pos: max(0, cfg.starters.get(pos, 0) - self.count(pos)) for pos in STARTER_POSITIONS}
        surplus = sum(max(0, self.count(q) - cfg.starters.get(q, 0)) for q in cfg.flex_positions)
        open_["FLEX"] = max(0, cfg.starters.get("FLEX", 0) - surplus)
        return open_

    def lineup(self) -> tuple[list[tuple[str, Player | None]], list[Player]]:
        """Greedy best lineup: list of (slot, player) plus bench list."""
        used: set[int] = set()
        slots: list[tuple[str, Player | None]] = []
        pool = sorted(self.players, key=lambda p: -p.value)
        for pos in STARTER_POSITIONS:
            for _ in range(self.cfg.starters.get(pos, 0)):
                pick = next((p for p in pool if p.pos == pos and p.id not in used), None)
                if pick:
                    used.add(pick.id)
                slots.append((pos, pick))
        for _ in range(self.cfg.starters.get("FLEX", 0)):
            pick = next((p for p in pool if p.pos in self.cfg.flex_positions and p.id not in used), None)
            if pick:
                used.add(pick.id)
            slots.append(("FLEX", pick))
        bench = [p for p in pool if p.id not in used]
        return slots, bench

    def starters_points(self) -> float:
        slots, _ = self.lineup()
        return sum(p.proj for _, p in slots if p)

    def summary(self) -> str:
        parts = []
        for pos in ("QB", "RB", "WR", "TE", "FLEX", "DST", "K"):
            need = self.cfg.starters.get(pos, 0)
            if pos == "FLEX":
                have = need - self.open_starters()["FLEX"]
            else:
                have = min(self.count(pos), need)
            parts.append(f"{pos} {have}/{need}")
        bench_used = max(0, len(self.players) - sum(self.cfg.starters.values()))
        parts.append(f"BN {bench_used}/{self.cfg.bench}")
        return "  ".join(parts)


# ----------------------------------------------------------------- eligibility
def eligible_positions(roster: Roster, cfg: LeagueConfig, picks_left: int) -> tuple[dict, bool]:
    """
    Return ({pos: role}, forced) for positions the roster may draft now, where
    role is "starter", "flex" or "bench". picks_left includes the current pick.
    """
    open_ = roster.open_starters()
    total_open = sum(open_.values())
    forced = picks_left <= total_open
    roles: dict[str, str] = {}
    for pos in STARTER_POSITIONS:
        if roster.count(pos) >= cfg.max_pos.get(pos, 99):
            continue
        fills_starter = open_[pos] > 0
        fills_flex = (not fills_starter) and pos in cfg.flex_positions and open_["FLEX"] > 0
        if pos in ("K", "DST"):
            if roster.count(pos) >= 1:
                continue  # never a second kicker / defense
            if fills_starter and (picks_left <= cfg.kdst_picks or forced):
                roles[pos] = "starter"
            continue
        if fills_starter:
            roles[pos] = "starter"
        elif fills_flex:
            roles[pos] = "flex"
        elif not forced and BENCH_FACTOR.get(pos, 0.0) > 0:
            roles[pos] = "bench"
    if forced and not roles:  # should not happen, but never return nothing
        roles = {pos: "starter" for pos in STARTER_POSITIONS if roster.count(pos) < cfg.max_pos.get(pos, 99)}
    return roles, forced


# ------------------------------------------------------------------ lookahead
def survival(adp: float, pick_no: int) -> float:
    """Probability a player with this ADP is still available when pick_no comes up."""
    if adp >= 900:
        adp = 250.0
    scale = 2.5 + 0.10 * adp
    z = (adp - pick_no) / scale
    z = max(-30.0, min(30.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def expected_best_value(cands: list[Player], pick_no: int) -> float:
    """Expected value of the best of `cands` (sorted by value desc) still available at pick_no."""
    e, alive, last = 0.0, 1.0, 0.0
    for c in cands:
        s = survival(c.adp, pick_no)
        e += c.value * s * alive
        alive *= (1.0 - s)
        last = c.value
        if alive < 1e-4:
            break
    return e + alive * last


# ------------------------------------------------------------------- recommend
@dataclass
class Recommendation:
    player: Player
    score: float
    gain: float
    urgency: float
    survive: float | None
    role: str
    notes: list[str]


def recommend(available: list[Player], roster: Roster, cfg: LeagueConfig, current_pick: int, next_pick: int | None,
              last_pick: int | None = None, targets: set[str] | None = None, avoid: set[str] | None = None,
              top: int = 8) -> list[Recommendation]:
    from espn import norm_name
    targets = targets or set()
    avoid = avoid or set()
    picks_left = cfg.rounds - len(roster)
    if picks_left <= 0 or not available:
        return []
    roles, forced = eligible_positions(roster, cfg, picks_left)
    by_pos: dict[str, list[Player]] = {}
    for p in available:
        by_pos.setdefault(p.pos, []).append(p)
    for group in by_pos.values():
        group.sort(key=lambda p: -p.value)
    if last_pick is None or last_pick <= current_pick:
        last_pick = None
    floor = {pos: (expected_best_value(g, last_pick) if last_pick else g[-1].value) for pos, g in by_pos.items()}
    v_next = {pos: (expected_best_value(g, next_pick) if next_pick else None) for pos, g in by_pos.items()}

    recs: list[Recommendation] = []
    for p in available:
        role = roles.get(p.pos)
        if role is None or norm_name(p.name) in avoid:
            continue
        gain = p.value - floor[p.pos]
        urgency = max(0.0, p.value - v_next[p.pos]) if v_next.get(p.pos) is not None else 0.0
        surv = survival(p.adp, next_pick) if next_pick else None
        if role == "bench":
            # depth has diminishing returns: each extra backup at a position is worth 20% less
            surplus = max(0, roster.count(p.pos) - cfg.starters.get(p.pos, 0))
            factor = BENCH_FACTOR.get(p.pos, 0.0) * (0.8 ** max(0, surplus - 1))
        else:
            factor = 1.0
        pref = TARGET_MULT if norm_name(p.name) in targets else 1.0
        score = (gain + URGENCY_WEIGHT * urgency) * factor * pref
        if role == "starter":
            label = f"{p.pos}{roster.count(p.pos) + 1} starter"
        elif role == "flex":
            label = "FLEX starter"
        else:
            label = f"bench {p.pos}"
        notes = []
        if forced:
            notes.append("must fill a starting slot")
        if p.injured:
            notes.append(f"injury: {p.injury}")
        if pref > 1:
            notes.append("your target")
        if surv is not None and surv < 0.35:
            notes.append("likely gone by your next pick")
        if urgency > 12:
            notes.append("cliff at position after him")
        recs.append(Recommendation(p, score, gain, urgency, surv, label, notes))
    recs.sort(key=lambda r: -r.score)
    return recs[:top]


def best_available(available: list[Player], n: int = 5) -> dict:
    """Top n by value at each position (for the 'what's left' panel)."""
    out: dict[str, list[Player]] = {}
    for p in sorted(available, key=lambda p: -p.value):
        out.setdefault(p.pos, [])
        if len(out[p.pos]) < n:
            out[p.pos].append(p)
    return out
