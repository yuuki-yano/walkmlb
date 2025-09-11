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
        # BatterStat にイベント詳細(HR/エラー毎の個別リスト)は無いので集計値のみ算出
        hits_n = sum(s.h for s in stats)
        # HR を列として保持していないので boxscore なしでは 0 とする (必要なら別途保持設計) 
        hrs_n = 0
        # errors, strikeouts は batter_stats に含まれる (errors は今は h/so/lob/rbi ... errors ない) -> 不足: errors を保持していないので 0
        errs_n = 0
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
