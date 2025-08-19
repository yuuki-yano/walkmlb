import asyncio
import datetime as dt
import json
import logging
from .db import SessionLocal
from .crud import upsert_game, upsert_batter
from .mlb_api import fetch_schedule, fetch_boxscore, refresh_boxscore
from .mlb_api import parse_boxscore_totals, iter_batters
from .mlb_api import get_cached_status, get_cached_linescore, get_cached_boxscore
from .mlb_api import BASE
import httpx
import zoneinfo
from .config import settings

logger = logging.getLogger("updater")

# Runtime status (for diagnostics)
LAST_START: dt.datetime | None = None
LAST_FINISH: dt.datetime | None = None
LAST_UPDATED_GAMES: int = 0
LAST_ERROR: str | None = None
IS_RUNNING: bool = False

async def update_for_date(date: dt.date) -> int:
    logger.info(f"updater: start update_for_date date={date}")
    games = await fetch_schedule(date)
    if not games:
        logger.info("updater: no games returned from schedule")
        return 0
    updated = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for g in games:
            try:
                game_pk = int(g.get("gamePk") or 0)
            except Exception:
                logger.exception("updater: invalid gamePk in schedule item: %s", g)
                continue
            # For Final games, ensure we capture the final boxscore/linescore/status once.
            try:
                sched_status = g.get("status", {}) if isinstance(g, dict) else {}
                det = (sched_status.get("detailedState") or "")
                ab = (sched_status.get("abstractGameState") or "")
                cached_status = get_cached_status(game_pk)
                cdet = (cached_status.get("detailed") or "")
                cab = (cached_status.get("abstract") or "")
                # Case-sensitive evaluation per request
                # is_final_api = (det == "Final" or ab == "Final")
                is_final_api = False
                # is_game_over_api = (det == "Game Over" or ab == "Game Over")
                is_game_over_api = False
                is_final_db = (cdet == "Final" or cab == "Final")

                # If DB already Final, skip further work
                if is_final_db:
                    logger.info("updater: skip (DB already Final) game_pk=%s", game_pk)
                    continue

                # If API says Final or Game Over but DB not Final yet => finalize now
                if is_final_api or is_game_over_api:
                    # Force refresh once to ensure final totals are stored
                    box = await refresh_boxscore(game_pk)
                    totals = parse_boxscore_totals(box)
                    home_team = box.get("teams", {}).get("home", {}).get("team", {}).get("name", "Home")
                    away_team = box.get("teams", {}).get("away", {}).get("team", {}).get("name", "Away")
                    db = SessionLocal()
                    try:
                        game = upsert_game(db, date=date, game_pk=game_pk, home_team=home_team, away_team=away_team,
                                           home_totals=totals.get("home", {}), away_totals=totals.get("away", {}))
                        db.flush()
                        for row in iter_batters(box):
                            upsert_batter(db, game=game, date=date, row=row)
                        db.commit()
                    finally:
                        db.close()
                    # Refresh linescore and status caches
                    try:
                        r = await client.get(f"{BASE}/game/{game_pk}/linescore")
                        r.raise_for_status()
                        await _upsert_simple_cache("linescore_cache", game_pk, r.json())
                    except Exception:
                        logger.exception("updater: linescore final fetch failed game_pk=%s", game_pk)
                    try:
                        url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
                        r = await client.get(url)
                        r.raise_for_status()
                        await _upsert_simple_cache("status_cache", game_pk, r.json())
                    except Exception:
                        logger.exception("updater: status final fetch failed game_pk=%s", game_pk)
                    updated += 1
                    logger.info("updater: finalized game cached game_pk=%s (reason=%s)", game_pk, "Final" if is_final_api else "Game Over")
                    continue
            except Exception:
                # If any issue determining final state, proceed with normal update
                pass
            # Boxscore: store + upsert game and batters
            box = await fetch_boxscore(game_pk)  # fetch (network) and cache inside
            totals = parse_boxscore_totals(box)
            home_team = box.get("teams", {}).get("home", {}).get("team", {}).get("name", "Home")
            away_team = box.get("teams", {}).get("away", {}).get("team", {}).get("name", "Away")
            db = SessionLocal()
            try:
                game = upsert_game(db, date=date, game_pk=game_pk, home_team=home_team, away_team=away_team,
                                   home_totals=totals.get("home", {}), away_totals=totals.get("away", {}))
                db.flush()
                for row in iter_batters(box):
                    upsert_batter(db, game=game, date=date, row=row)
                db.commit()
                updated += 1
            finally:
                db.close()
            # Linescore cache
            try:
                r = await client.get(f"{BASE}/game/{game_pk}/linescore")
                r.raise_for_status()
                await _upsert_simple_cache("linescore_cache", game_pk, r.json())
            except Exception:
                logger.exception("updater: linescore fetch failed game_pk=%s", game_pk)
            # Status cache (live feed)
            try:
                url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
                r = await client.get(url)
                r.raise_for_status()
                await _upsert_simple_cache("status_cache", game_pk, r.json())
            except Exception:
                logger.exception("updater: status fetch failed game_pk=%s", game_pk)
    logger.info(f"updater: finished update_for_date date={date} updated_games={updated}")
    return updated

async def _upsert_simple_cache(table: str, game_pk: int, payload: dict):
    from .db import LinescoreCache, StatusCache
    model = LinescoreCache if table == "linescore_cache" else StatusCache
    db = SessionLocal()
    try:
        row = db.query(model).filter(model.game_pk == game_pk).one_or_none()
        data = json.dumps(payload)
        if row:
            row.json = data
        else:
            db.add(model(game_pk=game_pk, json=data))
        db.commit()
    finally:
        db.close()

async def run_scheduler():
    # simple loop every minute
    global LAST_START, LAST_FINISH, LAST_UPDATED_GAMES, LAST_ERROR, IS_RUNNING
    while True:
        try:
            LAST_ERROR = None
            IS_RUNNING = True
            LAST_START = dt.datetime.now()
            tz = zoneinfo.ZoneInfo(settings.update_tz)
            today_local = dt.datetime.now(tz).date()
            LAST_UPDATED_GAMES = await update_for_date(today_local)
            LAST_FINISH = dt.datetime.now()
            IS_RUNNING = False
        except Exception as e:
            LAST_ERROR = str(e)
            IS_RUNNING = False
            logger.exception("updater: unexpected error in scheduler loop")
        await asyncio.sleep(60)
