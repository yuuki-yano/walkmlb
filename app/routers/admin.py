from fastapi import APIRouter, Query, Header, HTTPException
from datetime import date as Date
import asyncio
from .. import updater as upd
from ..config import settings

def _assert_admin(authorization: str | None):
    """Very simple bearer token check if ADMIN_TOKEN is configured.
    Accepts header like 'Bearer <token>' or raw token.
    """
    if not settings.admin_token:
        return
    token = None
    if authorization:
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        else:
            token = authorization.strip()
    if token != settings.admin_token:
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

async def _start_run_once(date: str | None):
    # Parse date or use today
    d = Date.fromisoformat(date) if date else Date.today()

    async def _runner():
        try:
            upd.LAST_ERROR = None
            upd.IS_RUNNING = True
            upd.LAST_START = upd.dt.datetime.now()
            upd.LAST_UPDATED_GAMES = await upd.update_for_date(d)
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
                total += await upd.update_for_date(cur)
                cur += upd.dt.timedelta(days=1)
            upd.LAST_UPDATED_GAMES = total
            upd.LAST_FINISH = upd.dt.datetime.now()
        except Exception as e:
            upd.LAST_ERROR = str(e)
        finally:
            upd.IS_RUNNING = False

    asyncio.create_task(_runner())
    return {"accepted": True, "month": month}
