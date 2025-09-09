import datetime as dt
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal, Game, BatterStat
from ..mlb_api import fetch_boxscore, parse_boxscore_totals, parse_player_events
from ..mlb_api import get_cached_status, get_cached_linescore, get_cached_boxscore, fetch_game_status, fetch_linescore
from ..db import StatusCache
import json as _json

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/games")
async def list_games(date: str, team: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")
    q = db.query(Game).filter(Game.date == d)
    if team:
        q = q.filter((Game.home_team == team) | (Game.away_team == team))
    items = []
    for g in q.all():
        status = get_cached_status(g.game_pk)
        if (status.get("detailed") == "Unknown" and status.get("abstract") == "Unknown"):
            try:
                status = await fetch_game_status(g.game_pk)
            except Exception:
                pass
        items.append({
            "gamePk": g.game_pk,
            "date": g.date.isoformat(),
            "home": {"team": g.home_team, "R": g.home_runs, "H": g.home_hits, "E": g.home_errors, "HR": g.home_homers},
            "away": {"team": g.away_team, "R": g.away_runs, "H": g.away_hits, "E": g.away_errors, "HR": g.away_homers},
            "status": status,
            "link": f"/game.html?gamePk={g.game_pk}",
        })
    return {"date": date, "games": items}

@router.get("/batters")
def list_batters(date: str, team: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")
    q = db.query(BatterStat).filter(BatterStat.date == d)
    if team:
        q = q.filter(BatterStat.team == team)
    res = [
        {
            "team": b.team,
            "name": b.name,
            "pos": b.position,
            "AB": b.ab, "R": b.r, "H": b.h, "RBI": b.rbi, "BB": b.bb, "SO": b.so, "LOB": b.lob,
        }
        for b in q.all()
    ]
    return {"date": date, "batters": res}

@router.get("/games/{game_pk}")
async def game_detail(game_pk: int, db: Session = Depends(get_db)):
    g = db.query(Game).filter(Game.game_pk == game_pk).one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    box = get_cached_boxscore(game_pk)
    if not box:
        box = await fetch_boxscore(game_pk)
    totals = parse_boxscore_totals(box)
    players = parse_player_events(box)
    status = get_cached_status(game_pk)
    if (status.get("detailed") == "Unknown" and status.get("abstract") == "Unknown"):
        try:
            status = await fetch_game_status(game_pk)
        except Exception:
            pass
    ls = get_cached_linescore(game_pk)
    # If innings are missing/empty, fetch once and cache so scoreboard shows up
    if not ls.get("innings"):
        try:
            ls = await fetch_linescore(game_pk)
        except Exception:
            pass
    scoreboard = {
        "innings": [
            {
                "num": inn.get("num"),
                "away": inn.get("away", {}).get("runs", 0),
                "home": inn.get("home", {}).get("runs", 0),
            } for inn in ls.get("innings", [])
        ],
        "totals": {
            "away": ls.get("teams", {}).get("away", {}).get("runs", 0),
            "home": ls.get("teams", {}).get("home", {}).get("runs", 0),
        }
    }
    def pack(side: str, team_name: str):
        t = totals[side]
        p = players[side]
        return {
            "team": team_name,
            "runsTotal": t.get("runs", 0),
            "hitsTotal": t.get("hits", 0),
            "errorsTotal": t.get("errors", 0),
            "homersTotal": t.get("homers", 0),
            "hitsPlayers": p.get("hits", []),
            "errorsPlayers": p.get("errors", []),
            "homeRunsPlayers": p.get("homeRuns", []),
            "strikeOutsPlayers": p.get("strikeOuts", []),
        }
    return {
        "gamePk": game_pk,
        "date": g.date.isoformat(),
        "home": pack("home", g.home_team),
        "away": pack("away", g.away_team),
    "status": status,
    "scoreboard": scoreboard,
    }

@router.get("/games/{game_pk}/plate-appearances")
async def game_plate_appearances(game_pk: int, side: str, db: Session = Depends(get_db)):
    if side not in ("home", "away"):
        raise HTTPException(status_code=400, detail="side must be 'home' or 'away'")
    # Get raw live feed JSON from status_cache or fetch if missing
    row = db.query(StatusCache).filter(StatusCache.game_pk == game_pk).one_or_none()
    feed = None
    if row:
        try:
            feed = _json.loads(row.json)
        except Exception:
            feed = None
    if not feed:
        # Fallback: fetch live feed once
        import httpx
        try:
            url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
            async with httpx.AsyncClient(timeout=59.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                feed = r.json()
            # Save to cache
            try:
                payload = _json.dumps(feed)
                if row:
                    row.json = payload
                else:
                    db.add(StatusCache(game_pk=game_pk, json=payload))
                db.commit()
            except Exception:
                pass
        except Exception:
            raise HTTPException(status_code=404, detail="live feed not available")

    all_plays = (feed.get("liveData", {}) or {}).get("plays", {}).get("allPlays", [])
    game_data = feed.get("gameData", {}) or {}
    # Determine home/away by halfInning (top=away, bottom=home)
    # Map player -> list[str]
    pa_map: dict[str, list[str]] = {}
    # Abbreviation mapping
    mapping = {
        "single": "1B", "double": "2B", "triple": "3B", "home_run": "HR", "home run": "HR",
        "walk": "BB", "intent_walk": "IBB", "hit_by_pitch": "HBP", "strikeout": "K", "strikeout_double_play": "K",
        "field_out": "OUT", "force_out": "FO", "grounded_into_double_play": "GDP", "double_play": "DP",
        "sac_fly": "SF", "sac_bunt": "SH", "catcher_interf": "CI",
    }
    for p in all_plays:
        about = p.get("about", {}) or {}
        if not about.get("isComplete"):
            continue
        half = about.get("halfInning")  # 'top' or 'bottom'
        if half not in ("top", "bottom"):
            continue
        play_side = "away" if half == "top" else "home"
        if play_side != side:
            continue
        matchup = p.get("matchup", {}) or {}
        batter = (matchup.get("batter", {}) or {}).get("fullName")
        if not batter:
            continue
        res = p.get("result", {}) or {}
        ev_type = (res.get("eventType") or res.get("event") or "").lower()
        abbr = mapping.get(ev_type, None)
        # Fallback: for unknown events skip (we could include raw for debugging)
        if not abbr:
            continue
        pa_map.setdefault(batter, []).append(abbr)

    players = [{"name": n, "pa": seq} for n, seq in pa_map.items()]
    return {"gamePk": game_pk, "side": side, "players": players}

@router.get("/games/{game_pk}/batting-order")
async def game_batting_order(game_pk: int, side: str, db: Session = Depends(get_db)):
    if side not in ("home", "away"):
        raise HTTPException(status_code=400, detail="side must be 'home' or 'away'")
    box = get_cached_boxscore(game_pk)
    if not box:
        box = await fetch_boxscore(game_pk)
    team = (box.get("teams", {}) or {}).get(side, {})
    players = team.get("players", {}) or {}
    # Collect players with battingOrder info
    entries = []
    for p in players.values():
        person = p.get("person", {}) or {}
        name = person.get("fullName") or "Unknown"
        bo = p.get("battingOrder")
        if not bo:
            # no battingOrder means did not bat; skip for batting order list
            continue
        try:
            order = int(bo)
        except Exception:
            continue
        pos = (p.get("position", {}) or {}).get("abbreviation") or ""
        all_positions = [ap.get("abbreviation") for ap in (p.get("allPositions") or []) if ap.get("abbreviation")]
        entries.append({
            "name": name,
            "order": order,
            "slot": order // 100,
            "pos": pos,
            "positions": all_positions,
        })
    # Group by slot and sort within slot by order
    slots_map: dict[int, list] = {}
    for e in entries:
        slots_map.setdefault(e["slot"], []).append(e)
    slots = []
    for slot in sorted(slots_map.keys()):
        stints = sorted(slots_map[slot], key=lambda x: x["order"])  # 101,102,...
        # Build simple display notes for substitutions/position changes
        out_stints = []
        for s in stints:
            pos = s.get("pos") or ""
            positions = s.get("positions") or []
            # If first label is PH/PR, mark as such; if later positions include field positions, include them
            note_parts = []
            if pos in ("PH", "PR"):
                note_parts.append(pos)
            extra = [pp for pp in positions if pp not in ("PH", "PR")]
            if extra:
                note_parts.append("→" + "/".join(extra))
            note = " ".join(note_parts)
            out_stints.append({
                "name": s["name"],
                "order": s["order"],
                "pos": pos,
                "positions": positions,
                "note": note,
            })
        slots.append({"slot": slot, "stints": out_stints})
    # Also provide a flat map name -> order for sorting elsewhere
    name_to_order = {e["name"]: e["order"] for e in entries}
    return {"gamePk": game_pk, "side": side, "slots": slots, "nameToOrder": name_to_order}

@router.get("/games/{game_pk}/pitchers")
async def game_pitchers(game_pk: int, side: str):
    """Return pitcher stats for the given side (team perspective: side=home returns home pitchers).
    Includes: strikeOuts, baseOnBalls, hits, homeRuns, wildPitches, balks, passedBall (from play events when available).
    """
    if side not in ("home", "away"):
        raise HTTPException(status_code=400, detail="side must be 'home' or 'away'")
    # boxscore provides pitching stats per player
    box = get_cached_boxscore(game_pk)
    if not box:
        box = await fetch_boxscore(game_pk)
    team = (box.get("teams", {}) or {}).get(side, {})
    players = team.get("players", {}) or {}
    out = []
    for p in players.values():
        person = p.get("person", {}) or {}
        name = person.get("fullName") or "Unknown"
        pitch = (p.get("stats", {}) or {}).get("pitching", {}) or {}
        if not pitch:
            continue
        at_bats = int(pitch.get("atBats", 0) or 0)
        hits = int(pitch.get("hits", 0) or 0)
        baa = (hits / at_bats) if at_bats > 0 else None
        out.append({
            "name": name,
            "id": person.get("id"),
            "SO": int(pitch.get("strikeOuts", 0) or 0),
            "BB": int(pitch.get("baseOnBalls", 0) or 0),
            "H": hits,
            "HR": int(pitch.get("homeRuns", 0) or 0),
            "WP": int(pitch.get("wildPitches", 0) or 0),
            "BK": int(pitch.get("balks", 0) or 0),
            "IP": pitch.get("inningsPitched") or "0.0",
            "R": int(pitch.get("runs", 0) or 0),
            "ER": int(pitch.get("earnedRuns", 0) or 0),
            "AB": at_bats,
            "BAA": round(baa, 3) if baa is not None else None,
        })
    # Passed ball is a catching stat; try to glean from live plays for this side's defense
    # If available, accumulate per catcher and attach as PB
    try:
        # get live feed from StatusCache or fetch once
        from ..db import SessionLocal, StatusCache
        import json as _json
        db = SessionLocal()
        row = db.query(StatusCache).filter(StatusCache.game_pk == game_pk).one_or_none()
        feed = None
        if row:
            try:
                feed = _json.loads(row.json)
            except Exception:
                feed = None
        if not feed:
            import httpx
            async with httpx.AsyncClient(timeout=59.0) as client:
                r = await client.get(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
                r.raise_for_status()
                feed = r.json()
        db.close()
        pb_map: dict[str,int] = {}
        appearance_order: dict[int,int] = {}
        # Attempt to read pitchers appearance order from liveData.boxscore.teams[side].pitchers (list of player IDs)
        try:
            team_box = (feed.get("liveData", {}) or {}).get("boxscore", {}).get("teams", {}).get(side, {})
            pid_list = team_box.get("pitchers", []) or []
            appearance_order = {int(pid): idx for idx, pid in enumerate(pid_list)}
        except Exception:
            appearance_order = {}
        for p in (feed.get("liveData", {}) or {}).get("plays", {}).get("allPlays", []) or []:
            about = p.get("about", {}) or {}
            if not about.get("isComplete"):
                continue
            # Defensive side is opposite of halfInning
            half = about.get("halfInning")
            if half not in ("top", "bottom"):
                continue
            defense_side = "home" if half == "top" else "away"
            if defense_side != side:
                continue
            res = (p.get("result", {}) or {})
            ev = (res.get("eventType") or res.get("event") or "").lower()
            if "passed ball" in ev or ev == "passed_ball":
                # Try catcher name from credits or matchup
                credits = p.get("credits", []) or []
                catcher = None
                for c in credits:
                    if (c.get("position", {}) or {}).get("abbreviation") == "C":
                        catcher = (c.get("player", {}) or {}).get("fullName")
                        break
                if not catcher:
                    catcher = ((p.get("matchup", {}) or {}).get("catcher", {}) or {}).get("fullName")
                if catcher:
                    pb_map[catcher] = pb_map.get(catcher, 0) + 1
        if pb_map:
            # Attach PB to rows if catcher is listed among pitchers/catchers; else append as separate line
            names = {r["name"] for r in out}
            for n, c in pb_map.items():
                if n in names:
                    for r in out:
                        if r["name"] == n:
                            r["PB"] = (r.get("PB", 0) + c)
                else:
                    out.append({"name": n, "PB": c, "SO": 0, "BB": 0, "H": 0, "HR": 0, "WP": 0, "BK": 0})
        # Sort by appearance order if available
        def sort_key(row: dict):
            pid = row.get("id")
            if isinstance(pid, int) and pid in appearance_order:
                return (0, appearance_order[pid])
            return (1, row.get("name") or "")
        out.sort(key=sort_key)
    except Exception:
        # ignore PB extraction errors
        pass
    return {"gamePk": game_pk, "side": side, "pitchers": out}
