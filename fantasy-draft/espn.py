"""
Read-only ESPN Fantasy Football API client (standard library only).

Endpoints used (all GET):
  * League:  {BASE}/seasons/{season}/segments/0/leagues/{league_id}?view=...
             views: mSettings, mTeam, mDraftDetail, mRoster
  * Players: same URL with view=kona_player_info and an X-Fantasy-Filter
             header. When called through the league URL, ESPN applies the
             league's own scoring settings to the projections
             ("appliedTotal"), so 6-pt passing TDs / full PPR are baked in.
  * Public fallback (no cookies): .../leaguedefaults/3 (ESPN's default PPR league).
  * Pro teams / bye weeks: {BASE}/seasons/{season}?view=proTeamSchedules_wl

Private leagues need the espn_s2 and SWID cookies of a logged-in member.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

POS_BY_ID = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
POSITION_ID = {v: k for k, v in POS_BY_ID.items()}
SLOT_BY_ID = {
    0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DST", 17: "K",
    20: "BE", 21: "IR", 23: "FLEX", 7: "OP", 3: "RB/WR", 5: "WR/TE",
}
# Slot ids that are "flex-like" and which positions may fill them.
FLEX_SLOT_ELIGIBLE = {23: ("RB", "WR", "TE"), 3: ("RB", "WR"), 5: ("WR", "TE"), 7: ("QB", "RB", "WR", "TE")}

PLAYER_FILTER_SLOTS = [0, 2, 4, 6, 16, 17]  # QB RB WR TE DST K


class EspnError(Exception):
    pass


class AuthError(EspnError):
    pass


def norm_name(s: str) -> str:
    """Normalize a player name for matching: lowercase, strip punctuation/suffixes."""
    s = (s or "").lower().replace("&", "and")
    s = re.sub(r"[.'’`\-]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


class EspnClient:
    def __init__(self, league_id: int, season: int, espn_s2: str | None = None, swid: str | None = None,
                 cache_dir: str | None = None, timeout: int = 25, public: bool = False):
        self.league_id = int(league_id)
        self.season = int(season)
        self.espn_s2 = (espn_s2 or "").strip() or None
        self.swid = (swid or "").strip() or None
        if self.swid and not self.swid.startswith("{"):
            self.swid = "{" + self.swid.strip("{}") + "}"
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.public = public
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    # ------------------------------------------------------------------ http
    @property
    def has_cookies(self) -> bool:
        return bool(self.espn_s2 and self.swid)

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.has_cookies:
            h["Cookie"] = f"espn_s2={self.espn_s2}; SWID={self.swid}"
        if extra:
            h.update(extra)
        return h

    def _get(self, url: str, extra_headers: dict | None = None, retries: int = 3):
        last_err = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers=self._headers(extra_headers))
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise AuthError(
                        f"ESPN returned HTTP {e.code} for {url.split('?')[0]}.\n"
                        "This league is private: put a logged-in member's espn_s2 and SWID cookies in config.json "
                        "(see README 'Cookies'). Cookies expire; grab fresh ones if this worked before."
                    ) from e
                if e.code == 404:
                    raise EspnError(f"ESPN returned 404 for {url} (wrong league id or season?)") from e
                last_err = e
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
                last_err = e
            time.sleep(1.5 * (attempt + 1))
        raise EspnError(f"ESPN request failed after {retries} attempts: {last_err}")

    # --------------------------------------------------------------- endpoints
    def _league_url(self) -> str:
        if self.public:
            return f"{BASE}/seasons/{self.season}/segments/0/leaguedefaults/3"
        return f"{BASE}/seasons/{self.season}/segments/0/leagues/{self.league_id}"

    def league(self, views=("mSettings", "mTeam", "mDraftDetail", "mRoster")) -> dict:
        qs = "&".join(f"view={v}" for v in views)
        return self._get(f"{self._league_url()}?{qs}")

    def pro_teams(self) -> dict:
        """Return {proTeamId: {"abbrev":..., "bye": int}}."""
        cache = self._cache_path("proteams.json")
        data = self._read_cache(cache, ttl=6 * 3600)
        if data is None:
            data = self._get(f"{BASE}/seasons/{self.season}?view=proTeamSchedules_wl")
            self._write_cache(cache, data)
        out = {}
        for t in data.get("settings", {}).get("proTeams", []):
            out[int(t["id"])] = {"abbrev": t.get("abbrev", "FA"), "bye": int(t.get("byeWeek") or 0),
                                 "name": t.get("name", ""), "location": t.get("location", "")}
        return out

    def player_pool(self, limit: int = 450, use_cache: bool = True, cache_ttl: int = 900) -> list[dict]:
        """Return normalized player dicts sorted by ESPN PPR rank."""
        cache = self._cache_path(f"pool_{'public' if self.public else self.league_id}.json")
        raw = self._read_cache(cache, ttl=cache_ttl) if use_cache else None
        if raw is None:
            flt = {
                "players": {
                    "filterSlotIds": {"value": PLAYER_FILTER_SLOTS},
                    "limit": int(limit),
                    "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "PPR"},
                    "filterRanksForRankTypes": {"value": ["PPR"]},
                    "filterStatsForSourceIds": {"value": [1]},
                }
            }
            raw = self._get(f"{self._league_url()}?view=kona_player_info",
                            extra_headers={"X-Fantasy-Filter": json.dumps(flt)})
            self._write_cache(cache, raw)
        teams = self.pro_teams()
        return [self._normalize_player(item, teams) for item in raw.get("players", [])]

    def _normalize_player(self, item: dict, teams: dict) -> dict:
        p = item.get("player", item)
        pos = POS_BY_ID.get(p.get("defaultPositionId"), "?")
        proj = None
        weekly = {}
        for s in p.get("stats", []) or []:
            if s.get("statSourceId") != 1 or s.get("seasonId") != self.season:
                continue
            if s.get("statSplitTypeId") == 0:
                proj = s.get("appliedTotal")
            elif s.get("statSplitTypeId") == 1:
                weekly[int(s.get("scoringPeriodId") or 0)] = s.get("appliedTotal")
        ranks = p.get("draftRanksByRankType") or {}
        rank = (ranks.get("PPR") or ranks.get("STANDARD") or {}).get("rank")
        own = p.get("ownership") or {}
        team = teams.get(int(p.get("proTeamId") or 0), {})
        return {
            "id": int(p["id"]),
            "name": p.get("fullName") or f"{p.get('firstName','')} {p.get('lastName','')}".strip(),
            "pos": pos,
            "team": team.get("abbrev", "FA"),
            "bye": team.get("bye", 0),
            "proj": float(proj) if proj is not None else 0.0,
            "weekly": weekly,
            "adp": float(own.get("averageDraftPosition") or 999.0),
            "pct_owned": float(own.get("percentOwned") or 0.0),
            "rank": int(rank) if rank else 999,
            "injury": p.get("injuryStatus") or "ACTIVE",
            "on_team_id": int(item.get("onTeamId") or 0),
            "status": item.get("status") or "",
        }

    # ------------------------------------------------------------------ cache
    def _cache_path(self, name: str) -> str | None:
        return os.path.join(self.cache_dir, name) if self.cache_dir else None

    @staticmethod
    def _read_cache(path: str | None, ttl: int):
        if not path or not os.path.exists(path):
            return None
        if time.time() - os.path.getmtime(path) > ttl:
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_cache(path: str | None, data) -> None:
        if not path:
            return
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)


# ---------------------------------------------------------------- league parse
def parse_league(data: dict) -> dict:
    """Extract the parts of the league payload we care about."""
    st = data.get("settings", {}) or {}
    roster = st.get("rosterSettings", {}) or {}
    draft = st.get("draftSettings", {}) or {}
    teams = []
    for t in data.get("teams", []) or []:
        name = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
        roster_ids = [int(e["playerId"]) for e in ((t.get("roster") or {}).get("entries") or []) if e.get("playerId")]
        teams.append({"id": int(t["id"]), "name": name or f"Team {t['id']}", "abbrev": t.get("abbrev", ""),
                      "owners": [str(o) for o in (t.get("owners") or [])], "roster_ids": roster_ids})
    members = {str(m.get("id")): (m.get("displayName") or f"{m.get('firstName','')} {m.get('lastName','')}".strip())
               for m in (data.get("members") or [])}
    dd = data.get("draftDetail", {}) or {}
    picks = []
    for pk in dd.get("picks", []) or []:
        pid = int(pk.get("playerId") or 0)
        picks.append({"overall": int(pk.get("overallPickNumber") or 0), "round": int(pk.get("roundId") or 0),
                      "round_pick": int(pk.get("roundPickNumber") or 0), "team_id": int(pk.get("teamId") or 0),
                      "player_id": pid, "auto": pk.get("autoDraftTypeId", 0)})
    picks.sort(key=lambda x: x["overall"])
    scoring = {}
    for item in (st.get("scoringSettings", {}) or {}).get("scoringItems", []) or []:
        try:
            scoring[int(item["statId"])] = float(item.get("points") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
    return {
        "name": st.get("name", "?"),
        "size": int(st.get("size") or len(teams) or 0),
        "scoring": scoring,
        "lineup_slot_counts": {int(k): int(v) for k, v in (roster.get("lineupSlotCounts") or {}).items()},
        "position_limits": {int(k): int(v) for k, v in (roster.get("positionLimits") or {}).items()},
        "draft": {
            "type": draft.get("type", "?"),
            "pick_order": [int(x) for x in (draft.get("pickOrder") or [])],
            "seconds_per_pick": draft.get("timePerSelection"),
            "date_ms": draft.get("date"),
            "in_progress": bool(dd.get("inProgress")),
            "drafted": bool(dd.get("drafted")),
        },
        "teams": teams,
        "members": members,
        "picks": picks,
        "scoring_period": data.get("scoringPeriodId"),
    }


def find_my_team(league: dict, swid: str | None) -> dict | None:
    if not swid:
        return None
    key = "{" + swid.strip("{}").upper() + "}"
    for t in league["teams"]:
        if any(o.strip("{}").upper() == key.strip("{}") for o in t["owners"]):
            return t
    return None
