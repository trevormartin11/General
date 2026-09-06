"""Offline tests: synthetic player pool, no network.  Run: python3 -m unittest discover -s tests -v"""
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from brain import (LeagueConfig, Player, Roster, compute_values, eligible_positions, next_pick_after,  # noqa: E402
                   pick_to_round_slot, picks_for_slot, recommend, survival)
import sim  # noqa: E402
from draft import DraftState, find_player, render_panel  # noqa: E402

# lineup / limits exactly as the Family Fantasy Football League screenshots show
FAMILY_LEAGUE = {
    "name": "Family Fantasy Football League", "size": 12,
    "lineup_slot_counts": {0: 1, 2: 2, 4: 2, 6: 1, 23: 1, 16: 1, 17: 1, 20: 6, 21: 1},
    "position_limits": {1: 2, 2: 8, 3: 8, 4: 3, 5: 3, 16: 3},
    "draft": {"type": "SNAKE", "pick_order": [], "seconds_per_pick": 60, "date_ms": None,
              "in_progress": False, "drafted": False},
    "teams": [], "members": {}, "picks": [], "scoring": {4: 6.0, 53: 1.0, 3: 0.04},
}


def synthetic_pool(seed: int = 0) -> list[Player]:
    """Realistic-ish value curves per position with ADP following overall value (plus noise)."""
    rng = random.Random(seed)
    spec = {"QB": (28, 390, 240), "RB": (85, 360, 110), "WR": (110, 350, 110), "TE": (32, 245, 95),
            "K": (32, 170, 115), "DST": (32, 135, 75)}
    players, pid = [], 1
    for pos, (n, top, bottom) in spec.items():
        for i in range(n):
            frac = i / (n - 1)
            proj = top - (top - bottom) * (frac ** 0.75)
            players.append(Player(id=pid, name=f"{pos} Player{i + 1}", pos=pos, team="T%02d" % (i % 32 + 1),
                                  bye=5 + (i % 10), proj=round(proj, 1)))
            pid += 1
    # ADP: rank by a crude positional-value-over-worst-starter so K/DST/QB go late like real drafts
    def draftiness(p):
        base = {"QB": 300, "RB": 200, "WR": 200, "TE": 190, "K": 150, "DST": 110}[p.pos]
        return p.proj - base + rng.gauss(0, 6)
    order = sorted(players, key=lambda p: -draftiness(p))
    for i, p in enumerate(order, 1):
        p.adp = float(i) if i <= 180 else 999.0
        p.rank = i
    return players


def family_cfg() -> LeagueConfig:
    return LeagueConfig.from_espn(FAMILY_LEAGUE)


class SnakeMath(unittest.TestCase):
    def test_round_slot(self):
        self.assertEqual(pick_to_round_slot(1, 12), (1, 1))
        self.assertEqual(pick_to_round_slot(12, 12), (1, 12))
        self.assertEqual(pick_to_round_slot(13, 12), (2, 12))
        self.assertEqual(pick_to_round_slot(24, 12), (2, 1))
        self.assertEqual(pick_to_round_slot(25, 12), (3, 1))

    def test_picks_for_slot(self):
        self.assertEqual(picks_for_slot(7, 12, 15)[:3], [7, 18, 31])
        self.assertEqual(picks_for_slot(1, 12, 15)[:3], [1, 24, 25])
        self.assertEqual(len(picks_for_slot(12, 12, 15)), 15)
        self.assertEqual(next_pick_after(7, 7, 12, 15), 18)
        self.assertIsNone(next_pick_after(175, 7, 12, 15))

    def test_survival_monotone(self):
        self.assertGreater(survival(60, 30), survival(20, 30))
        self.assertAlmostEqual(survival(30, 30), 0.5, places=3)
        self.assertGreater(survival(999, 175), 0.9)


class Config(unittest.TestCase):
    def test_family_league(self):
        cfg = family_cfg()
        self.assertEqual(cfg.teams, 12)
        self.assertEqual(cfg.starters, {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "DST": 1, "K": 1, "FLEX": 1})
        self.assertEqual(cfg.bench, 6)
        self.assertEqual(cfg.rounds, 15)
        self.assertEqual(cfg.max_pos["QB"], 2)
        self.assertEqual(cfg.max_pos["TE"], 3)
        self.assertEqual(cfg.flex_positions, ("RB", "TE", "WR"))


class Eligibility(unittest.TestCase):
    def test_kdst_gated_until_late(self):
        cfg = family_cfg()
        roster = Roster(cfg)
        roles, forced = eligible_positions(roster, cfg, picks_left=15)
        self.assertNotIn("K", roles)
        self.assertNotIn("DST", roles)
        self.assertFalse(forced)
        roles, _ = eligible_positions(roster, cfg, picks_left=3)
        self.assertIn("K", roles)
        self.assertIn("DST", roles)

    def test_forced_fill_restricts_to_open_starters(self):
        cfg = family_cfg()
        roster = Roster(cfg)
        pool = synthetic_pool()
        # fill everything except WR2 and K, with 2 picks left
        for pos, n in (("QB", 1), ("RB", 3), ("WR", 1), ("TE", 1), ("DST", 1)):
            for p in [x for x in pool if x.pos == pos][:n]:
                roster.add(p)
        for p in [x for x in pool if x.pos == "RB"][3:9]:
            roster.add(p)
        self.assertEqual(len(roster), 13)
        roles, forced = eligible_positions(roster, cfg, picks_left=2)
        self.assertTrue(forced)
        self.assertEqual(set(roles), {"WR", "K"})

    def test_position_max_respected(self):
        cfg = family_cfg()
        roster = Roster(cfg)
        for p in [x for x in synthetic_pool() if x.pos == "QB"][:2]:
            roster.add(p)
        roles, _ = eligible_positions(roster, cfg, picks_left=10)
        self.assertNotIn("QB", roles)


class Simulation(unittest.TestCase):
    def _legal(self, roster: Roster, cfg: LeagueConfig):
        self.assertEqual(len(roster), cfg.rounds)
        for pos, mx in cfg.max_pos.items():
            self.assertLessEqual(roster.count(pos), mx, pos)
        self.assertEqual(roster.count("K"), 1)
        self.assertEqual(roster.count("DST"), 1)
        self.assertEqual(sum(roster.open_starters().values()), 0, "all starting slots must be filled")

    def test_engine_builds_legal_competitive_rosters(self):
        cfg = family_cfg()
        pool = synthetic_pool()
        for slot in (1, 7, 12):
            rosters, log = sim.simulate(pool, cfg, {slot}, seed=slot)
            for r in rosters.values():
                self._legal(r, cfg)
            # K/DST not before the last 3 rounds
            mine = [(rd, p) for (o, rd, s, p) in log if s == slot]
            for rd, p in mine:
                if p.pos in ("K", "DST"):
                    self.assertGreaterEqual(rd, cfg.rounds - 2, f"{p.name} drafted in round {rd}")
            self.assertLessEqual(roster_count(rosters[slot], "QB"), 2)
            table = sorted(rosters, key=lambda k: -rosters[k].starters_points())
            self.assertLessEqual(table.index(slot) + 1, 3, f"engine finished {table.index(slot) + 1} from slot {slot}")

    def test_two_engine_teams_same_draft(self):
        cfg = family_cfg()
        rosters, _ = sim.simulate(synthetic_pool(), cfg, {3, 8}, seed=4)
        for s in (3, 8):
            self._legal(rosters[s], cfg)


def roster_count(roster: Roster, pos: str) -> int:
    return roster.count(pos)


class Recommend(unittest.TestCase):
    def test_first_pick_is_elite_rb_or_wr(self):
        cfg = family_cfg()
        players = compute_values(synthetic_pool(), cfg)
        recs = recommend(players, Roster(cfg), cfg, 1, 24, 169, top=3)
        self.assertTrue(recs)
        self.assertIn(recs[0].player.pos, ("RB", "WR"))
        self.assertLessEqual(recs[0].player.adp, 3)

    def test_avoid_and_targets(self):
        from espn import norm_name
        cfg = family_cfg()
        players = compute_values(synthetic_pool(), cfg)
        top = recommend(players, Roster(cfg), cfg, 1, 24, 169, top=1)[0].player
        recs = recommend(players, Roster(cfg), cfg, 1, 24, 169, avoid={norm_name(top.name)}, top=3)
        self.assertNotIn(top.id, [r.player.id for r in recs])
        second = recs[0].player
        recs2 = recommend(players, Roster(cfg), cfg, 1, 24, 169, targets={norm_name(second.name)}, top=2)
        self.assertIn("your target", " ".join(n for r in recs2 for n in r.notes if r.player.id == second.id))


class DraftStateFlow(unittest.TestCase):
    def _league(self):
        lg = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in FAMILY_LEAGUE.items()}
        lg["draft"] = dict(FAMILY_LEAGUE["draft"], pick_order=[101 + i for i in range(12)], in_progress=True)
        lg["teams"] = [{"id": 101 + i, "name": f"Team {i + 1}", "abbrev": "", "owners": ["{SWID-%d}" % i], "roster_ids": []}
                       for i in range(12)]
        lg["picks"] = []
        return lg

    def test_live_flow_slot_7(self):
        cfg = family_cfg()
        players = compute_values(synthetic_pool(), cfg)
        lg = self._league()
        state = DraftState(cfg, players, my_team_id=107, my_slot=7, picks_file=None)
        state.update(lg)
        self.assertEqual(state.current_pick, 1)
        self.assertEqual(state.picks_until_mine(), 6)
        self.assertEqual(state.my_next_pick(), 7)
        by_adp = sorted(players, key=lambda p: p.adp)
        for overall in range(1, 7):
            rnd, slot = pick_to_round_slot(overall, 12)
            lg["picks"].append({"overall": overall, "round": rnd, "round_pick": slot, "team_id": 100 + slot,
                                "player_id": by_adp[overall - 1].id, "auto": 0})
        state.update(lg)
        self.assertEqual(state.current_pick, 7)
        self.assertEqual(state.picks_until_mine(), 0)
        self.assertEqual(state.team_on_clock()[2], "Team 7")
        self.assertEqual(state.my_next_pick(), 18)
        self.assertEqual(len(state.available()), len(players) - 6)
        panel = render_panel(state, set(), set(), top=5)
        self.assertIn("YOU ARE ON THE CLOCK", panel)
        self.assertIn("Round 1, pick #7", panel)
        # my pick lands on my roster
        lg["picks"].append({"overall": 7, "round": 1, "round_pick": 7, "team_id": 107, "player_id": by_adp[6].id, "auto": 0})
        state.update(lg)
        self.assertEqual([p.id for p in state.my_roster().players], [by_adp[6].id])
        self.assertEqual(state.picks_until_mine(), 10)
        self.assertIn("You pick in 10 pick(s)", render_panel(state, set(), set()))

    def test_manual_picks_file(self):
        import tempfile
        cfg = family_cfg()
        players = compute_values(synthetic_pool(), cfg)
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("RB Player1\nme: WR Player1\n# comment\n\n")
            path = f.name
        try:
            state = DraftState(cfg, players, my_team_id=None, my_slot=4, picks_file=path)
            state.update(self._league())
            self.assertEqual(state.picks_made, 2)
            self.assertEqual([p.name for p in state.my_roster().players], ["WR Player1"])
            self.assertNotIn("RB Player1", [p.name for p in state.available()])
        finally:
            os.unlink(path)


class NameMatching(unittest.TestCase):
    def setUp(self):
        self.pool = [Player(1, "Ja'Marr Chase", "WR"), Player(2, "Ravens D/ST", "DST"), Player(3, "Travis Etienne Jr.", "RB"),
                     Player(4, "Kenneth Walker III", "RB"), Player(5, "Amon-Ra St. Brown", "WR"), Player(6, "Bijan Robinson", "RB"),
                     Player(7, "Brian Robinson Jr.", "RB")]

    def test_matches(self):
        self.assertEqual(find_player(self.pool, "jamarr chase").id, 1)
        self.assertEqual(find_player(self.pool, "Baltimore Ravens").id, 2)
        self.assertEqual(find_player(self.pool, "ravens dst").id, 2)
        self.assertEqual(find_player(self.pool, "Ravens").id, 2)
        self.assertEqual(find_player(self.pool, "Travis Etienne").id, 3)
        self.assertEqual(find_player(self.pool, "kenneth walker").id, 4)
        self.assertEqual(find_player(self.pool, "Amon Ra St Brown").id, 5)
        self.assertEqual(find_player(self.pool, "Bijan Robinson").id, 6)
        self.assertEqual(find_player(self.pool, "Brian Robinson").id, 7)
        self.assertIsNone(find_player(self.pool, "Nobody Real"))


if __name__ == "__main__":
    unittest.main()
