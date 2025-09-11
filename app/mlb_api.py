import datetime as dt
from typing import Any, Dict, List, Tuple
import httpx
import json
import hashlib
from .db import SessionLocal, BoxscoreCache, LinescoreCache, StatusCache

BASE = "https://statsapi.mlb.com/api/v1"

def _is_final_cached(game_pk: int) -> bool:
    """Return True if StatusCache says the game is Final; avoids any network calls."""
    db = SessionLocal()
    try:
        row = db.query(StatusCache).filter(StatusCache.game_pk == game_pk).one_or_none()
        if not row:
            return False
        j = json.loads(row.json)
        s = (j.get("gameData", {}) or {}).get("status", {}) or {}
        detailed = (s.get("detailedState") or "").lower()
        abstract = (s.get("abstractGameState") or "").lower()
        return ("final" in detailed) or (abstract in ("final", "completed")) or ("game over" in detailed)
    except Exception:
        return False
    finally:
        db.close()

async def fetch_schedule(date: dt.date) -> List[Dict[str, Any]]:
    params = {
        "sportId": 1,
        "date": date.isoformat(),
        "hydrate": "lineScore"
    }
    async with httpx.AsyncClient(timeout=59.0) as client:
        r = await client.get(f"{BASE}/schedule", params=params)
        r.raise_for_status()
        data = r.json()
    dates = data.get("dates", [])
    if not dates:
        return []
    return dates[0].get("games", [])

def _get_cached_boxscore(game_pk: int):
    db = SessionLocal()
    try:
        row = db.query(BoxscoreCache).filter(BoxscoreCache.game_pk == game_pk).one_or_none()
        if row:
            return json.loads(row.json)
        return None
    finally:
        db.close()

def get_cached_boxscore(game_pk: int) -> Dict[str, Any] | None:
    """Return cached boxscore JSON if present, else None. No network calls."""
    res = _get_cached_boxscore(game_pk)
    return res

TRIM_BOX_KEYS = [
    # Paths (top-level or nested) we plan to remove if present; we only target top-level keys here
    "gameData","decision","flags","alerts","liveData","seriesStatus","seriesSummary",
]

def _shrink_boxscore(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Create a shallow copy; remove very large or unused keys.
    out = dict(payload)
    for k in TRIM_BOX_KEYS:
        if k in out:
            out.pop(k, None)
    # Optionally trim players sub-structure stats we don't need (keep essentials)
    teams = out.get("teams", {}) or {}
    for side in ("home","away"):
        t = teams.get(side)
        if not t:
            continue
        players = t.get("players") or {}
        for pid, pdata in list(players.items()):
            stats = pdata.get("stats", {}) or {}
            batting = stats.get("batting", {})
            # Keep only fields we use in iter_batters/parse totals
            keep_batting = {k: batting.get(k) for k in ["atBats","runs","hits","rbi","baseOnBalls","strikeOuts","leftOnBase","homeRuns"] if k in batting}
            stats_trim = {"batting": keep_batting}
            fielding = stats.get("fielding", {}) or {}
            errs = fielding.get("errors")
            if errs is not None:
                stats_trim["fielding"] = {"errors": errs}
            pdata["stats"] = stats_trim
            # Remove large keys if present
            for rm in ("allPositions","gameStatus","status"):
                if rm in pdata:
                    pdata.pop(rm, None)
    return out

def _calc_hash(payload: Dict[str, Any]) -> str:
    # Stable json dump
    dumped = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()

def _set_cached_boxscore(game_pk: int, payload: Dict[str, Any]):
    shrunk = _shrink_boxscore(payload)
    h = _calc_hash(shrunk)
    db = SessionLocal()
    try:
        row = db.query(BoxscoreCache).filter(BoxscoreCache.game_pk == game_pk).one_or_none()
        data = json.dumps(shrunk)
        if row:
            if row.hash == h:
                return  # No change
            row.json = data
            row.hash = h
        else:
            row = BoxscoreCache(game_pk=game_pk, json=data, hash=h)
            db.add(row)
        db.commit()
    finally:
        db.close()

async def fetch_boxscore(game_pk: int) -> Dict[str, Any]:
    # Try local cache first
    cached = _get_cached_boxscore(game_pk)
    if cached:
        return cached
    # If cached status indicates Final, do not hit network; return empty structure
    if _is_final_cached(game_pk):
        return {}
    # Otherwise fetch from MLB API and cache
    async with httpx.AsyncClient(timeout=59.0) as client:
        r = await client.get(f"{BASE}/game/{game_pk}/boxscore")
        r.raise_for_status()
        data = r.json()
        _set_cached_boxscore(game_pk, data)
        return data

async def refresh_boxscore(game_pk: int) -> Dict[str, Any]:
    """Always fetch boxscore from MLB API and overwrite cache."""
    async with httpx.AsyncClient(timeout=59.0) as client:
        r = await client.get(f"{BASE}/game/{game_pk}/boxscore")
        r.raise_for_status()
        data = r.json()
    _set_cached_boxscore(game_pk, data)
    return data

async def fetch_game_status(game_pk: int) -> Dict[str, str]:
    """No TTL here; rely on updater to refresh DB every minute. If absent, fetch and store once."""
    db = SessionLocal()
    try:
        row = db.query(StatusCache).filter(StatusCache.game_pk == game_pk).one_or_none()
        if row:
            j = json.loads(row.json)
        else:
            url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
            async with httpx.AsyncClient(timeout=59.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                j = r.json()
            payload = json.dumps(j)
            db.add(StatusCache(game_pk=game_pk, json=payload))
            db.commit()
    finally:
        db.close()
    s = j.get("gameData", {}).get("status", {})
    return {"detailed": s.get("detailedState", "Unknown"), "abstract": s.get("abstractGameState", "Unknown")}

def _shrink_linescore(ls: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ls)
    # Keep only innings, teams score, balls/strikes if exist
    keep = {k: out.get(k) for k in ["innings","teams","currentInning","currentInningOrdinal","isTopInning","balls","strikes","outs"] if k in out}
    return keep

async def fetch_linescore(game_pk: int) -> Dict[str, Any]:
    """No TTL here; rely on updater. If absent, fetch once and store."""
    db = SessionLocal()
    try:
        row = db.query(LinescoreCache).filter(LinescoreCache.game_pk == game_pk).one_or_none()
        if row:
            return json.loads(row.json)
        # If cached status indicates Final, avoid fetching and return a minimal structure
        if _is_final_cached(game_pk):
            return {"innings": [], "teams": {"home": {"runs": 0}, "away": {"runs": 0}}}
        async with httpx.AsyncClient(timeout=59.0) as client:
            r = await client.get(f"{BASE}/game/{game_pk}/linescore")
            r.raise_for_status()
            data = r.json()
        shrunk = _shrink_linescore(data)
        h = _calc_hash(shrunk)
        existing = row
        if existing and existing.hash == h:
            return json.loads(existing.json)
        if existing:
            existing.json = json.dumps(shrunk)
            existing.hash = h
        else:
            db.add(LinescoreCache(game_pk=game_pk, json=json.dumps(shrunk), hash=h))
        db.commit()
        return shrunk
    finally:
        db.close()

def get_cached_status(game_pk: int) -> Dict[str, str]:
    db = SessionLocal()
    try:
        row = db.query(StatusCache).filter(StatusCache.game_pk == game_pk).one_or_none()
        if not row:
            return {"detailed": "Unknown", "abstract": "Unknown"}
        j = json.loads(row.json)
        s = j.get("gameData", {}).get("status", {})
        return {"detailed": s.get("detailedState", "Unknown"), "abstract": s.get("abstractGameState", "Unknown")}
    finally:
        db.close()

def get_cached_linescore(game_pk: int) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        row = db.query(LinescoreCache).filter(LinescoreCache.game_pk == game_pk).one_or_none()
        return json.loads(row.json) if row else {"innings": [], "teams": {"home": {"runs": 0}, "away": {"runs": 0}}}
    finally:
        db.close()


def extract_game_summary(game: Dict[str, Any]) -> Tuple[int, str, str, dt.date]:
    game_pk = int(game.get("gamePk") or 0)
    home_team = game.get("teams", {}).get("home", {}).get("team", {}).get("name", "")
    away_team = game.get("teams", {}).get("away", {}).get("team", {}).get("name", "")
    game_date = dt.date.fromisoformat(game.get("gameDate", "1970-01-01T00:00:00Z")[:10])
    return game_pk, home_team, away_team, game_date


def parse_boxscore_totals(box: Dict[str, Any]) -> Dict[str, Any]:
    teams = box.get("teams", {})
    home = teams.get("home", {})
    away = teams.get("away", {})

    def team_vals(team: Dict[str, Any]):
        b = team.get("teamStats", {}).get("batting", {})
        f = team.get("teamStats", {}).get("fielding", {})
        return {
            "runs": team.get("teamStats", {}).get("batting", {}).get("runs", 0),
            "hits": b.get("hits", 0),
            "errors": f.get("errors", 0),
            "homers": b.get("homeRuns", 0),
        }

    return {
        "home": team_vals(home),
        "away": team_vals(away),
    }


def iter_batters(box: Dict[str, Any]):
    teams = box.get("teams", {})
    for side in ("home", "away"):
        t = teams.get(side, {})
        team_name = t.get("team", {}).get("name", side)
        players = t.get("players", {})
        for p in players.values():
            person = p.get("person", {})
            stats = p.get("stats", {}).get("batting", {})
            position = p.get("position", {}).get("abbreviation", "")
            if not stats:
                continue
            yield {
                "team": team_name,
                "name": person.get("fullName", "Unknown"),
                "position": position,
                "ab": stats.get("atBats", 0),
                "r": stats.get("runs", 0),
                "h": stats.get("hits", 0),
                "hr": stats.get("homeRuns", 0),
                # fielding errors for batter (if any) – look into fielding stats
                "errors": (p.get("stats", {}).get("fielding", {}) or {}).get("errors", 0),
                "rbi": stats.get("rbi", 0),
                "bb": stats.get("baseOnBalls", 0),
                "so": stats.get("strikeOuts", 0),
                "lob": stats.get("leftOnBase", 0) or 0,
            }

def parse_player_events(box: Dict[str, Any]) -> Dict[str, Any]:
    """Collect per-player event counts (hits, home runs, errors, strikeouts) by team."""
    teams = box.get("teams", {})
    def make_side(name_key: str):
        return {
            "team": teams.get(name_key, {}).get("team", {}).get("name", name_key),
            "players": {}
        }
    out = {"home": make_side("home"), "away": make_side("away")}
    for side in ("home", "away"):
        t = teams.get(side, {})
        players = t.get("players", {})
        for p in players.values():
            person = p.get("person", {})
            name = person.get("fullName", "Unknown")
            b = p.get("stats", {}).get("batting", {})
            f = p.get("stats", {}).get("fielding", {})
            hits = int(b.get("hits", 0) or 0)
            hrs = int(b.get("homeRuns", 0) or 0)
            errs = int(f.get("errors", 0) or 0)
            sos = int(b.get("strikeOuts", 0) or 0)
            if any((hits, hrs, errs, sos)):
                d = out[side]["players"].setdefault(name, {"hits": 0, "homeRuns": 0, "errors": 0, "strikeOuts": 0})
                d["hits"] += hits
                d["homeRuns"] += hrs
                d["errors"] += errs
                d["strikeOuts"] += sos
    # Convert to arrays per event type with counts
    def to_arrays(side: str):
        plist = out[side]["players"]
        def arr(key: str):
            return [{"name": n, key: c[key]} for n, c in plist.items() if c.get(key, 0)]
        return {
            "team": out[side]["team"],
            "hits": arr("hits"),
            "homeRuns": arr("homeRuns"),
            "errors": arr("errors"),
            "strikeOuts": arr("strikeOuts"),
        }
    return {"home": to_arrays("home"), "away": to_arrays("away")}
