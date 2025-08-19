from fastapi import APIRouter, Query
from datetime import date as Date
import asyncio
from .. import updater as upd

router = APIRouter()

@router.get("/updater/status")
def updater_status():
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
async def updater_run_once_post(date: str | None = Query(None, description="YYYY-MM-DD")):
    return await _start_run_once(date)

@router.get("/updater/run-once")
async def updater_run_once_get(date: str | None = Query(None, description="YYYY-MM-DD")):
    return await _start_run_once(date)
