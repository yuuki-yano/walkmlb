import datetime as dt
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal, Game, BatterStat
from ..mlb_api import fetch_boxscore, get_cached_boxscore, parse_player_events
from ..crud import compute_steps_for_date

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/steps/goal")
def get_steps_goal(date: str, team: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")
    steps = compute_steps_for_date(db, d, team)
    return {"date": date, "team": team, "steps": steps}

@router.get("/steps/goal/range")
def get_steps_goal_range(month: str, team: Optional[str] = None, db: Session = Depends(get_db)):
    """Return goal steps for each day in a month (YYYY-MM) for optional team.
    Reduces N-per-day calls on calendar page.
    Team specified: use player-level weights per design (consistent with compute_steps_for_date for team).
    Team omitted: aggregate league-wide using team-level weights.
    """
    # Parse month
    try:
        y, m = month.split('-')
        year = int(y); mon = int(m)
        from datetime import date as D, timedelta
        start = D(year, mon, 1)
        end = D(year+1,1,1) - timedelta(days=1) if mon == 12 else D(year, mon+1,1) - timedelta(days=1)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid month")
    from ..config import settings
    days = []
    if not team:
        # League-wide: sum both teams per game per day then apply team-level weights
        games = db.query(Game).filter(Game.date >= start, Game.date <= end).all()
        per_date = {}
        for g in games:
            dkey = g.date
            agg = per_date.setdefault(dkey, {"hits":0,"homers":0,"errors":0})
            agg["hits"] += g.home_hits + g.away_hits
            agg["homers"] += g.home_homers + g.away_homers
            agg["errors"] += g.home_errors + g.away_errors
        cur = start
        from datetime import timedelta
        while cur <= end:
            agg = per_date.get(cur, {"hits":0,"homers":0,"errors":0})
            steps = (
                settings.walk_base
                + settings.walk_per_hit * agg["hits"]
                + settings.walk_per_hr * agg["homers"]
                + settings.walk_per_error * agg["errors"]
            )
            days.append({"date": cur.isoformat(), "steps": max(0,int(steps))})
            cur += timedelta(days=1)
        return {"month": month, "team": None, "days": days}
    # Team-specific: aggregate BatterStat first
    batter_rows = db.query(BatterStat).filter(BatterStat.team == team, BatterStat.date >= start, BatterStat.date <= end).all()
    per_date_players = {}
    for r in batter_rows:
        agg = per_date_players.setdefault(r.date, {"hits":0,"homers":0,"errors":0,"strikeouts":0})
        agg["hits"] += r.h
        agg["homers"] += getattr(r,'hr',0)
        agg["errors"] += getattr(r,'errors',0)
        agg["strikeouts"] += r.so
    # Fallback using Game side-only for dates missing batter stats
    games_team = db.query(Game).filter(Game.date >= start, Game.date <= end).filter((Game.home_team == team) | (Game.away_team == team)).all()
    for g in games_team:
        if g.date in per_date_players:
            continue
        agg = per_date_players.setdefault(g.date, {"hits":0,"homers":0,"errors":0,"strikeouts":0})
        if g.home_team == team:
            agg["hits"] += g.home_hits
            agg["homers"] += g.home_homers
            agg["errors"] += g.home_errors
        else:
            agg["hits"] += g.away_hits
            agg["homers"] += g.away_homers
            agg["errors"] += g.away_errors
    from datetime import timedelta
    cur = start
    while cur <= end:
        agg = per_date_players.get(cur, {"hits":0,"homers":0,"errors":0,"strikeouts":0})
        steps = (
            settings.walk_base
            + settings.walk_per_hit_player * agg["hits"]
            + settings.walk_per_hr_player * agg["homers"]
            + settings.walk_per_error_player * agg["errors"]
            + settings.walk_per_so_player * agg["strikeouts"]
        )
        days.append({"date": cur.isoformat(), "steps": max(0,int(steps))})
        cur += timedelta(days=1)
    return {"month": month, "team": team, "days": days}

@router.get("/steps/goal/game/{game_pk}")
def get_steps_goal_for_game(game_pk: int, side: str, db: Session = Depends(get_db)):
    """Compute steps for a single game's team side (home or away) using team totals."""
    from ..db import Game
    if side not in ("home", "away"):
        raise HTTPException(status_code=400, detail="side must be 'home' or 'away'")
    g = db.query(Game).filter(Game.game_pk == game_pk).one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    hits = g.home_hits if side == "home" else g.away_hits
    homers = g.home_homers if side == "home" else g.away_homers
    errors = g.home_errors if side == "home" else g.away_errors
    from ..config import settings
    steps = max(0, int(settings.walk_base + settings.walk_per_hit * hits + settings.walk_per_hr * homers + settings.walk_per_error * errors))
    team = g.home_team if side == "home" else g.away_team
    return {"gamePk": game_pk, "team": team, "side": side, "steps": steps}

@router.get("/steps/goal/game/{game_pk}/players")
async def get_steps_goal_for_players(game_pk: int, side: str, admin: bool | None = False, db: Session = Depends(get_db)):
    """Compute steps from player events (hits/HR/errors) for a chosen side.
    改修: キャッシュ未存在時でも DB (BatterStat) から再構築 / admin=true の場合は強制リフレッシュ。
    """
    if side not in ("home", "away"):
        raise HTTPException(status_code=400, detail="side must be 'home' or 'away'")
    from ..config import settings
    box = get_cached_boxscore(game_pk)
    if (not box) and admin:
        # 管理操作では常に最新を取りに行く (Final でも改めて空構造可)
        try:
            box = await fetch_boxscore(game_pk)
        except Exception:
            box = None
    if not box:
        # Boxscore フル JSON が無い場合は BatterStat からプレイヤーイベント再構築
        g = db.query(Game).filter(Game.game_pk == game_pk).one_or_none()
        if not g:
            raise HTTPException(status_code=404, detail="Game not found")
        stats = db.query(BatterStat).filter(BatterStat.game_id == g.id, BatterStat.team == (g.home_team if side=="home" else g.away_team)).all()
        hits_n = sum(s.h for s in stats)
        hrs_n = sum(getattr(s, 'hr', 0) for s in stats)
        errs_n = sum(getattr(s, 'errors', 0) for s in stats)
        so_n = sum(s.so for s in stats)
        steps = (
            settings.walk_base
            + settings.walk_per_hit_player * hits_n
            + settings.walk_per_hr_player * hrs_n
            + settings.walk_per_error_player * errs_n
            + settings.walk_per_so_player * so_n
        )
        return {
            "gamePk": game_pk,
            "team": g.home_team if side=="home" else g.away_team,
            "side": side,
            "counts": {"hits": hits_n, "homeRuns": hrs_n, "errors": errs_n, "strikeOuts": so_n},
            "players": {
                "hits": [],
                "homeRuns": [],
                "errors": [],
                "strikeOuts": [],
            },
            "steps": max(0, int(steps)),
            "source": "db-fallback"
        }
    players = parse_player_events(box)[side]
    # counts by event (totals)
    hits_n = sum([p.get('hits', 0) for p in players.get("hits", [])])
    hrs_n = sum([p.get('homeRuns', 0) for p in players.get("homeRuns", [])])
    errs_n = sum([p.get('errors', 0) for p in players.get("errors", [])])
    so_n = sum([p.get('strikeOuts', 0) for p in players.get("strikeOuts", [])])
    steps = (
        settings.walk_base
        + settings.walk_per_hit_player * hits_n
        + settings.walk_per_hr_player * hrs_n
        + settings.walk_per_error_player * errs_n
        + settings.walk_per_so_player * so_n
    )
    team = players.get("team")
    return {
        "gamePk": game_pk,
        "team": team,
        "side": side,
        "counts": {"hits": hits_n, "homeRuns": hrs_n, "errors": errs_n, "strikeOuts": so_n},
        "players": {
            "hits": players.get("hits", []),
            "homeRuns": players.get("homeRuns", []),
            "errors": players.get("errors", []),
            "strikeOuts": players.get("strikeOuts", []),
        },
        "steps": max(0, int(steps)),
        "source": "boxscore-cache" if not admin else "boxscore-admin-refresh"
    }

@router.get("/steps/settings")
def get_steps_settings():
    from ..config import settings
    return {
        "base": settings.walk_base,
        "team": {
            "perHit": settings.walk_per_hit,
            "perHR": settings.walk_per_hr,
            "perError": settings.walk_per_error,
        },
        "player": {
            "perHit": settings.walk_per_hit_player,
            "perHR": settings.walk_per_hr_player,
            "perError": settings.walk_per_error_player,
            "perSO": settings.walk_per_so_player,
        },
    }
