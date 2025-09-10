from fastapi import APIRouter, Query, Header, HTTPException
from datetime import date as Date
import asyncio
from .. import updater as upd
from ..config import settings
import base64
from ..db import SessionLocal, BoxscoreCache, LinescoreCache, StatusCache
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
