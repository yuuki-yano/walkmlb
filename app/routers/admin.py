from fastapi import APIRouter, Query, Header, HTTPException
from datetime import date as Date
import asyncio
from .. import updater as upd
from ..config import settings
import base64, uuid, asyncio, datetime as _dt
from ..db import SessionLocal, BoxscoreCache, LinescoreCache, StatusCache
from ..db import Game, PitcherStat, engine
from ..mlb_api import refresh_boxscore
import json as _json

def _assert_admin(authorization: str | None):
    """Authorize request via Bearer token or Basic auth.

    Rules:
      - If neither token nor basic credentials configured, allow (open admin).
      - If at least one configured, header must match one of them.
      - Bearer <token> accepted when ADMIN_TOKEN set.
      - Basic <base64(user:pass)> accepted when ADMIN_BASIC_USER / ADMIN_BASIC_PASS set.
    """
    token_cfg = settings.admin_token
    basic_user = settings.admin_basic_user
    basic_pass = settings.admin_basic_pass

    if not (token_cfg or (basic_user and basic_pass)):
        return  # Nothing configured -> open

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    auth = authorization.strip()

    # Bearer path
    if auth.lower().startswith("bearer ") and token_cfg:
        supplied = auth[7:].strip()
        if supplied == token_cfg:
            return
        # fall through to maybe basic

    # Basic path
    if auth.lower().startswith("basic ") and basic_user and basic_pass:
        b64 = auth.split(" ",1)[1]
        try:
            decoded = base64.b64decode(b64).decode('utf-8')
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid basic auth encoding")
        if ':' not in decoded:
            raise HTTPException(status_code=401, detail="Invalid basic auth format")
        u, p = decoded.split(':',1)
        if u == basic_user and p == basic_pass:
            return

    raise HTTPException(status_code=401, detail="Unauthorized")

router = APIRouter()

# In-memory job store for long tasks (lost on restart)
_REBUILD_JOBS: dict[str, dict] = {}

@router.get("/updater/status")
def updater_status(authorization: str | None = Header(None)):
    _assert_admin(authorization)
    def ts(x):
        return x.isoformat() if x else None
    return {
        "isRunning": upd.IS_RUNNING,
        "lastStart": ts(upd.LAST_START),
        "lastFinish": ts(upd.LAST_FINISH),
        "lastUpdatedGames": upd.LAST_UPDATED_GAMES,
        "lastError": upd.LAST_ERROR,
    }

@router.get("/updater/logs")
def updater_logs(limit: int = Query(200, le=1000), authorization: str | None = Header(None)):
    """Return recent verbose updater logs (if enabled)."""
    _assert_admin(authorization)
    if not settings.updater_log_detail:
        return {"enabled": False, "logs": []}
    # Return newest last (chronological) limited slice
    data = list(upd.DETAIL_LOGS)[-limit:]
    return {"enabled": True, "logs": data, "count": len(data)}

async def _start_run_once(date: str | None):
    # Parse date or use today
    d = Date.fromisoformat(date) if date else Date.today()

    async def _runner():
        try:
            upd.LAST_ERROR = None
            upd.IS_RUNNING = True
            upd.LAST_START = upd.dt.datetime.now()
            upd.LAST_UPDATED_GAMES = await upd.update_for_date(d, force=True)
            upd.LAST_FINISH = upd.dt.datetime.now()
        except Exception as e:
            upd.LAST_ERROR = str(e)
        finally:
            upd.IS_RUNNING = False

    asyncio.create_task(_runner())
    return {"accepted": True, "date": d.isoformat()}

@router.post("/updater/run-once")
async def updater_run_once_post(date: str | None = Query(None, description="YYYY-MM-DD"), authorization: str | None = Header(None)):
    _assert_admin(authorization)
    return await _start_run_once(date)

@router.get("/updater/run-once")
async def updater_run_once_get(date: str | None = Query(None, description="YYYY-MM-DD"), authorization: str | None = Header(None)):
    _assert_admin(authorization)
    return await _start_run_once(date)


@router.post("/updater/backfill-month")
async def updater_backfill_month(
    month: str = Query(..., description="YYYY-MM"),
    authorization: str | None = Header(None),
):
    """Fetches schedule + box/line/status for each day in given month and stores them.
    Runs asynchronously; returns an id-less acceptance response and progress can be read via /updater/status.
    """
    _assert_admin(authorization)

    # Parse month string safely
    try:
        y, m = month.split("-")
        start = Date(int(y), int(m), 1)
        if start.month == 12:
            end = Date(start.year + 1, 1, 1)
        else:
            end = Date(start.year, start.month + 1, 1)
        end = end - upd.dt.timedelta(days=1)
    except Exception:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    async def _runner():
        try:
            upd.LAST_ERROR = None
            upd.IS_RUNNING = True
            upd.LAST_START = upd.dt.datetime.now()
            total = 0
            cur = start
            while cur <= end:
                total += await upd.update_for_date(cur, force=True)
                cur += upd.dt.timedelta(days=1)
            upd.LAST_UPDATED_GAMES = total
            upd.LAST_FINISH = upd.dt.datetime.now()
        except Exception as e:
            upd.LAST_ERROR = str(e)
        finally:
            upd.IS_RUNNING = False

    asyncio.create_task(_runner())
    return {"accepted": True, "month": month}

# ---- Cache diagnostics ----

def _cache_counts(db):
    return {
        "boxscore": db.query(BoxscoreCache).count(),
        "linescore": db.query(LinescoreCache).count(),
        "status": db.query(StatusCache).count(),
    }

@router.get("/cache/summary")
def cache_summary(authorization: str | None = Header(None)):
    _assert_admin(authorization)
    db = SessionLocal()
    try:
        counts = _cache_counts(db)
        latest = {}
        for model, key in ((BoxscoreCache, "boxscore"), (LinescoreCache, "linescore"), (StatusCache, "status")):
            row = db.query(model).order_by(model.updated_at.desc()).limit(1).one_or_none()
            if row:
                latest[key] = row.updated_at.isoformat() if getattr(row, 'updated_at', None) else None
        return {"counts": counts, "latest": latest}
    finally:
        db.close()

@router.delete("/cache/clear")
def cache_clear(kind: str | None = Query(None, description="boxscore|linescore|status|all"), authorization: str | None = Header(None)):
    _assert_admin(authorization)
    kinds = {"boxscore": BoxscoreCache, "linescore": LinescoreCache, "status": StatusCache}
    db = SessionLocal()
    try:
        if not kind or kind == "all":
            removed = {}
            for k, model in kinds.items():
                cnt = db.query(model).delete(synchronize_session=False)
                removed[k] = cnt
            db.commit()
            return {"cleared": removed}
        if kind not in kinds:
            raise HTTPException(status_code=400, detail="invalid kind")
        cnt = db.query(kinds[kind]).delete(synchronize_session=False)
        db.commit()
        return {"cleared": {kind: cnt}}
    finally:
        db.close()

# ---- Maintenance / Announcement ----

@router.get("/maintenance/status")
def maintenance_status(authorization: str | None = Header(None)):
    _assert_admin(authorization)
    return {
        "maintenance": bool(settings.maintenance_mode),
        "maintenanceMessage": settings.maintenance_message,
        "announcementMessage": settings.announcement_message,
    }

@router.post("/maintenance/update")
def maintenance_update(
    maintenance: bool | None = Query(None, description="1=on,0=off"),
    maintenanceMessage: str | None = Query(None),
    announcementMessage: str | None = Query(None),
    authorization: str | None = Header(None)
):
    """Update maintenance / announcement messages (in-memory for runtime; env not rewritten)."""
    _assert_admin(authorization)
    # mutate existing settings instance (pydantic models allow assignment by default)
    if maintenance is not None:
        settings.maintenance_mode = bool(maintenance)  # type: ignore
    if maintenanceMessage is not None:
        settings.maintenance_message = maintenanceMessage  # type: ignore
    if announcementMessage is not None:
        settings.announcement_message = announcementMessage  # type: ignore
    return {
        "updated": True,
        "maintenance": settings.maintenance_mode,
        "maintenanceMessage": settings.maintenance_message,
        "announcementMessage": settings.announcement_message,
    }

# ---- Pitcher stats rebuild utilities ----

def _extract_pitchers_from_boxscore(box: dict, side: str, team_name: str):
    players = (box.get("teams", {}) or {}).get(side, {}).get("players", {}) or {}
    out = []
    for pdata in players.values():
        pitch = (pdata.get("stats", {}) or {}).get("pitching", {}) or {}
        if not pitch:
            continue
        person = (pdata.get("person", {}) or {})
        name = person.get("fullName") or "Unknown"
        out.append({
            "name": name,
            "SO": pitch.get("strikeOuts"),
            "BB": pitch.get("baseOnBalls"),
            "H": pitch.get("hits"),
            "HR": pitch.get("homeRuns"),
            "IP": pitch.get("inningsPitched"),
            "R": pitch.get("runs"),
            "ER": pitch.get("earnedRuns"),
            "WP": pitch.get("wildPitches"),
            "BK": pitch.get("balks"),
            "AB": pitch.get("atBats"),
        })
    return out

@router.post("/rebuild/pitchers/game/{game_pk}")
async def rebuild_pitchers_game(game_pk: int, authorization: str | None = Header(None)):
    """Force re-fetch boxscore and rebuild PitcherStat rows for a single game (even if Final)."""
    _assert_admin(authorization)
    db = SessionLocal()
    try:
        g = db.query(Game).filter(Game.game_pk == game_pk).one_or_none()
        if not g:
            return {"gamePk": game_pk, "updated": 0, "detail": "game not found"}
        box = await refresh_boxscore(game_pk)
        # Ensure pitcher_stats table exists (best-effort)
        try:
            PitcherStat.__table__.create(bind=engine, checkfirst=True)
        except Exception:
            pass
        from ..crud import upsert_pitcher
        updated = 0
        for side in ("home","away"):
            team_name = (box.get("teams", {}) or {}).get(side, {}).get("team", {}) or {}
            tname = team_name.get("name", side)
            for row in _extract_pitchers_from_boxscore(box, side, tname):
                upsert_pitcher(db, game=g, date=g.date, team=tname, row=row)
                updated += 1
        db.commit()
        return {"gamePk": game_pk, "updated": updated}
    finally:
        db.close()

@router.post("/rebuild/pitchers/date")
async def rebuild_pitchers_date(date: str, authorization: str | None = Header(None)):
    """Rebuild pitcher stats for all games on a date (YYYY-MM-DD)."""
    _assert_admin(authorization)
    import datetime as _dt
    try:
        d = _dt.date.fromisoformat(date)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid date")
    db = SessionLocal()
    try:
        games = db.query(Game).filter(Game.date == d).all()
        total_games = len(games)
        total_pitchers = 0
        from ..crud import upsert_pitcher
        for g in games:
            box = await refresh_boxscore(g.game_pk)
            try:
                PitcherStat.__table__.create(bind=engine, checkfirst=True)
            except Exception:
                pass
            for side in ("home","away"):
                team_name = (box.get("teams", {}) or {}).get(side, {}).get("team", {}) or {}
                tname = team_name.get("name", side)
                for row in _extract_pitchers_from_boxscore(box, side, tname):
                    upsert_pitcher(db, game=g, date=g.date, team=tname, row=row)
                    total_pitchers += 1
        db.commit()
        return {"date": d.isoformat(), "games": total_games, "pitchers": total_pitchers}
    finally:
        db.close()

@router.post("/rebuild/pitchers/month")
async def rebuild_pitchers_month(month: str, background: int | None = Query(None, description="1=run async (recommended)"), authorization: str | None = Header(None)):
    """Rebuild pitcher stats for all games in a month (YYYY-MM).
    If background=1, runs asynchronously and returns a jobId for polling.
    """
    _assert_admin(authorization)
    import datetime as _dt
    try:
        y, m = month.split('-')
        first = _dt.date(int(y), int(m), 1)
        if first.month == 12:
            last = _dt.date(first.year + 1, 1, 1) - _dt.timedelta(days=1)
        else:
            last = _dt.date(first.year, first.month + 1, 1) - _dt.timedelta(days=1)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid month")
    db = SessionLocal()
    try:
        games = db.query(Game).filter(Game.date >= first, Game.date <= last).all()
    finally:
        db.close()
    total_games = len(games)
    async_mode = (background == 1)
    if async_mode:
        job_id = uuid.uuid4().hex
        _REBUILD_JOBS[job_id] = {
            "id": job_id,
            "type": "rebuild_month_pitchers",
            "month": month,
            "status": "running",
            "started": _dt.datetime.utcnow().isoformat(),
            "finished": None,
            "games": total_games,
            "progressGames": 0,
            "pitchers": 0,
            "error": None,
        }
        async def _runner(glist):
            from ..crud import upsert_pitcher
            local = SessionLocal()
            try:
                for idx, g in enumerate(glist):
                    try:
                        box = await refresh_boxscore(g.game_pk)
                        try:
                            PitcherStat.__table__.create(bind=engine, checkfirst=True)
                        except Exception:
                            pass
                        for side in ("home","away"):
                            team_name = (box.get("teams", {}) or {}).get(side, {}).get("team", {}) or {}
                            tname = team_name.get("name", side)
                            for row in _extract_pitchers_from_boxscore(box, side, tname):
                                upsert_pitcher(local, game=g, date=g.date, team=tname, row=row)
                                _REBUILD_JOBS[job_id]["pitchers"] += 1
                        local.commit()
                    except Exception as e:
                        _REBUILD_JOBS[job_id]["error"] = str(e)
                    _REBUILD_JOBS[job_id]["progressGames"] = idx + 1
                _REBUILD_JOBS[job_id]["status"] = "finished"
                _REBUILD_JOBS[job_id]["finished"] = _dt.datetime.utcnow().isoformat()
            finally:
                local.close()
        asyncio.create_task(_runner(games))
        return {"accepted": True, "jobId": job_id, "games": total_games}
    # synchronous
    from ..crud import upsert_pitcher
    db2 = SessionLocal()
    total_pitchers = 0
    try:
        for g in games:
            box = await refresh_boxscore(g.game_pk)
            try:
                PitcherStat.__table__.create(bind=engine, checkfirst=True)
            except Exception:
                pass
            for side in ("home","away"):
                team_name = (box.get("teams", {}) or {}).get(side, {}).get("team", {}) or {}
                tname = team_name.get("name", side)
                for row in _extract_pitchers_from_boxscore(box, side, tname):
                    upsert_pitcher(db2, game=g, date=g.date, team=tname, row=row)
                    total_pitchers += 1
        db2.commit()
        return {"month": month, "games": total_games, "pitchers": total_pitchers, "background": False}
    finally:
        db2.close()

@router.get("/rebuild/pitchers/job/{job_id}")
def rebuild_job_status(job_id: str, authorization: str | None = Header(None)):
    _assert_admin(authorization)
    job = _REBUILD_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job
