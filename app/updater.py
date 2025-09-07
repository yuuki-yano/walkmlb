import asyncio
import datetime as dt
import json
import logging
from .db import SessionLocal
from .crud import upsert_game, upsert_batter
from .mlb_api import fetch_schedule, refresh_boxscore
from .mlb_api import parse_boxscore_totals, iter_batters
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

async def update_for_date(date: dt.date, *, force: bool = False) -> int:
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
            # First, get current status to decide whether to update (unless forced)
            status_state = await _refresh_and_get_status_state(client, game_pk)
            # Skip updates if game is Final or later (unless force=True)
            if (not force) and status_state == "final":
                continue
            # Boxscore: refresh from MLB and overwrite cache so totals update
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
            # Status cache already refreshed at start of loop
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
    # Adaptive loop: 60s when any game is Live; 300s otherwise
    global LAST_START, LAST_FINISH, LAST_UPDATED_GAMES, LAST_ERROR, IS_RUNNING
    while True:
        try:
            LAST_ERROR = None
            IS_RUNNING = True
            LAST_START = dt.datetime.now()
            tz = zoneinfo.ZoneInfo(settings.update_tz)
            today_local = dt.datetime.now(tz).date()
            # First, update any active (Live) games regardless of date
            active_updated = await _update_active_games()
            if active_updated > 0:
                LAST_UPDATED_GAMES = active_updated
            else:
                # No live games; perform a lighter sweep for today, skipping finals
                LAST_UPDATED_GAMES = await update_for_date(today_local)
            LAST_FINISH = dt.datetime.now()
            IS_RUNNING = False
        except Exception as e:
            LAST_ERROR = str(e)
            IS_RUNNING = False
            logger.exception("updater: unexpected error in scheduler loop")
        # Cleanup old cache entries beyond retention window
        try:
            await _cleanup_old_cache()
        except Exception:
            logger.exception("updater: cache cleanup failed")
        # Sleep interval: 60s if any Live games exist, else 300s
        try:
            has_live = await _has_any_live_games()
            if not has_live:
                # Fallback: check today's schedule for live status (one network call)
                tz = zoneinfo.ZoneInfo(settings.update_tz)
                today_local = dt.datetime.now(tz).date()
                try:
                    sched = await fetch_schedule(today_local)
                    for g in sched or []:
                        st = (g.get("status", {}) or {})
                        abstract = (st.get("abstractGameState") or "").lower()
                        detailed = (st.get("detailedState") or "").lower()
                        # if abstract == "live" or "in progress" in detailed or "live" in detailed:
                        #     has_live = True
                        #     break
                except Exception:
                    pass
        except Exception:
            has_live = False
        await asyncio.sleep(60 if has_live else 300)


# ---- Helper functions ----

async def _refresh_and_get_status_state(client: httpx.AsyncClient, game_pk: int) -> str:
    """Refresh live status cache for a game and return simplified state: 'live' | 'final' | 'other'."""
    try:
        url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
        r = await client.get(url)
        r.raise_for_status()
        j = r.json()
        await _upsert_simple_cache("status_cache", game_pk, j)
        s = j.get("gameData", {}).get("status", {})
        detailed = (s.get("detailedState") or "").lower()
        abstract = (s.get("abstractGameState") or "").lower()
        if "final" in detailed or abstract in ("final", "completed") or "game over" in detailed:
            return "final"
        if abstract == "live" or "in progress" in detailed or "progress" in detailed or "live" in detailed:
            return "live"
        return "other"
    except Exception:
        logger.exception("updater: status refresh failed game_pk=%s", game_pk)
        return "other"


async def _has_any_live_games() -> bool:
    """Check StatusCache for any live game quickly without network if possible."""
    from .db import SessionLocal, StatusCache
    import json as _json
    db = SessionLocal()
    try:
        for row in db.query(StatusCache).all():
            try:
                j = _json.loads(row.json)
                s = j.get("gameData", {}).get("status", {})
                detailed = (s.get("detailedState") or "").lower()
                abstract = (s.get("abstractGameState") or "").lower()
                if abstract == "live" or "in progress" in detailed or "live" in detailed:
                    return True
            except Exception:
                continue
        return False
    finally:
        db.close()


async def _update_active_games() -> int:
    """Update all games currently 'Live' in StatusCache regardless of date."""
    from .db import SessionLocal, StatusCache, Game
    import json as _json
    updated = 0
    db = SessionLocal()
    try:
        rows = db.query(StatusCache).all()
    finally:
        db.close()
    if not rows:
        return 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for row in rows:
            try:
                j = _json.loads(row.json)
            except Exception:
                continue
            # s = j.get("gameData", {}).get("status", {})
            # detailed = (s.get("detailedState") or "").lower()
            # abstract = (s.get("abstractGameState") or "").lower()
            # if not (abstract == "live" or "in progress" in detailed or "live" in detailed):
            #     continue
            game_pk = row.game_pk
            # Determine date for DB upsert: prefer existing Game row; else derive from status datetime; default to 'today' in update_tz
            tz = zoneinfo.ZoneInfo(settings.update_tz)
            gdate = dt.datetime.now(tz).date()
            try:
                # try existing game
                db2 = SessionLocal()
                try:
                    g = db2.query(Game).filter(Game.game_pk == game_pk).one_or_none()
                    if g:
                        gdate = g.date
                finally:
                    db2.close()
                from datetime import datetime
                dt_str = j.get("gameData", {}).get("datetime", {}).get("dateTime")
                if dt_str:
                    dt_utc = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    gdate = dt_utc.astimezone(tz).date()
            except Exception:
                gdate = dt.datetime.now(tz).date()

            # Refresh status (to keep it fresh) and skip if it just turned final
            state = await _refresh_and_get_status_state(client, game_pk)
            if state == "final":
                continue

            # Refresh boxscore and linescore, then persist
            try:
                box = await refresh_boxscore(game_pk)
                totals = parse_boxscore_totals(box)
                home_team = box.get("teams", {}).get("home", {}).get("team", {}).get("name", "Home")
                away_team = box.get("teams", {}).get("away", {}).get("team", {}).get("name", "Away")
                db3 = SessionLocal()
                try:
                    game = upsert_game(db3, date=gdate, game_pk=game_pk, home_team=home_team, away_team=away_team,
                                       home_totals=totals.get("home", {}), away_totals=totals.get("away", {}))
                    db3.flush()
                    for rowp in iter_batters(box):
                        upsert_batter(db3, game=game, date=gdate, row=rowp)
                    db3.commit()
                    updated += 1
                finally:
                    db3.close()
                # linescore
                try:
                    r = await client.get(f"{BASE}/game/{game_pk}/linescore")
                    r.raise_for_status()
                    await _upsert_simple_cache("linescore_cache", game_pk, r.json())
                except Exception:
                    logger.exception("updater: linescore fetch failed game_pk=%s", game_pk)
            except Exception:
                logger.exception("updater: active game update failed game_pk=%s", game_pk)
    return updated


async def _cleanup_old_cache():
    """Delete cache rows (boxscore/linescore/status) older than retention days.
    Uses updated_at column; only runs if retention_days > 0.
    """
    days = settings.cache_retention_days
    if days <= 0:
        return
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    from .db import SessionLocal, BoxscoreCache, LinescoreCache, StatusCache
    db = SessionLocal()
    try:
        # SQLite / MySQL both support comparison on datetime column
        removed = 0
        for model in (BoxscoreCache, LinescoreCache, StatusCache):
            q = db.query(model).filter(model.updated_at < cutoff)
            cnt = q.count()
            if cnt:
                q.delete(synchronize_session=False)
                removed += cnt
        if removed:
            db.commit()
            logger.info(f"updater: cache cleanup removed={removed} older than {days}d")
    finally:
        db.close()
