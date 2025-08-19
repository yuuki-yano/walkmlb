import asyncio
import datetime as dt
import json
import logging
from .db import SessionLocal
from .crud import upsert_game, upsert_batter
from .mlb_api import fetch_schedule, fetch_boxscore
from .mlb_api import parse_boxscore_totals, iter_batters
from .mlb_api import get_cached_status, get_cached_linescore, get_cached_boxscore
from .mlb_api import BASE
import httpx

logger = logging.getLogger("updater")

async def update_for_date(date: dt.date):
    logger.info(f"updater: start update_for_date date={date}")
    games = await fetch_schedule(date)
    if not games:
        logger.info("updater: no games returned from schedule")
        return
    updated = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for g in games:
            try:
                game_pk = int(g.get("gamePk") or 0)
            except Exception:
                logger.exception("updater: invalid gamePk in schedule item: %s", g)
                continue
            # Skip heavy updates for games that are Final and already cached
            try:
                sched_status = g.get("status", {}) if isinstance(g, dict) else {}
                det = (sched_status.get("detailedState") or "").lower()
                ab = (sched_status.get("abstractGameState") or "").lower()
                cached_status = get_cached_status(game_pk)
                cdet = (cached_status.get("detailed") or "").lower()
                cab = (cached_status.get("abstract") or "").lower()
                is_final = (
                    "final" in det or "final" in ab or "game over" in det or
                    "final" in cdet or "final" in cab or "game over" in cdet
                )
                if is_final:
                    box_cached = bool(get_cached_boxscore(game_pk))
                    ls_cached = bool((get_cached_linescore(game_pk) or {}).get("innings"))
                    if box_cached and ls_cached:
                        logger.info("updater: skip final game game_pk=%s (already cached)", game_pk)
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
    while True:
        try:
            today = dt.date.today()
            await update_for_date(today)
        except Exception:
            logger.exception("updater: unexpected error in scheduler loop")
        await asyncio.sleep(60)
