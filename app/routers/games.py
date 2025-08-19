import datetime as dt
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal, Game, BatterStat
from ..mlb_api import fetch_boxscore, parse_boxscore_totals, parse_player_events
from ..mlb_api import get_cached_status, get_cached_linescore, get_cached_boxscore, fetch_game_status, fetch_linescore

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
