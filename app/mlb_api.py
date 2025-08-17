import datetime as dt
from typing import Any, Dict, List, Tuple
import httpx

BASE = "https://statsapi.mlb.com/api/v1"

async def fetch_schedule(date: dt.date) -> List[Dict[str, Any]]:
    params = {
        "sportId": 1,
        "date": date.isoformat(),
        "hydrate": "lineScore"
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{BASE}/schedule", params=params)
        r.raise_for_status()
        data = r.json()
    dates = data.get("dates", [])
    if not dates:
        return []
    return dates[0].get("games", [])

async def fetch_boxscore(game_pk: int) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{BASE}/game/{game_pk}/boxscore")
        r.raise_for_status()
        return r.json()

async def fetch_game_status(game_pk: int) -> Dict[str, str]:
    """Return detailed and abstract status for a game from the live feed."""
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        j = r.json()
    s = j.get("gameData", {}).get("status", {})
    return {
        "detailed": s.get("detailedState", "Unknown"),
        "abstract": s.get("abstractGameState", "Unknown"),
    }

async def fetch_linescore(game_pk: int) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{BASE}/game/{game_pk}/linescore")
        r.raise_for_status()
        return r.json()


def extract_game_summary(game: Dict[str, Any]) -> Tuple[int, str, str, dt.date]:
    game_pk = game.get("gamePk")
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
