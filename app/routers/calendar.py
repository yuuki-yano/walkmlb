from fastapi import APIRouter, Query, HTTPException
from datetime import date as Date, timedelta
from typing import Dict, Any
import json
import zoneinfo

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from ..db import SessionLocal, Game, StatusCache
from ..mlb_api import get_cached_status
from ..updater import update_for_date

router = APIRouter()


def _month_range(month: str) -> tuple[Date, Date]:
    # month format: YYYY-MM
    try:
        y, m = month.split("-")
        start = Date(int(y), int(m), 1)
    except Exception:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    # next month - 1 day
    if start.month == 12:
        next_month = Date(start.year + 1, 1, 1)
    else:
        next_month = Date(start.year, start.month + 1, 1)
    end = next_month - timedelta(days=1)
    return start, end


@router.get("/calendar")
async def get_calendar(team: str = Query(..., description="Team name contains"),
                 month: str = Query(..., description="YYYY-MM"),
                 tz: str = Query("JP", description="JP or Local"),
                 fill: int = Query(1, description="1: fetch & save missing days in month, 0: no fetch")) -> Dict[str, Any]:
    start, end = _month_range(month)
    db: Session = SessionLocal()
    try:
        # Optionally fill missing dates (no rows at all on that date)
        if fill:
            cur = start
            while cur <= end:
                exists = db.query(Game.id).filter(Game.date == cur).limit(1).one_or_none()
                if not exists:
                    await update_for_date(cur)
                cur += timedelta(days=1)

        # Re-query after optional fill
        q = db.query(Game).filter(and_(Game.date >= start, Game.date <= end))
        if team:
            # Prefer exact match (dropdown supplies canonical name); fallback to LIKE if no exact exists
            exact = db.query(Game.id).filter(and_(Game.date >= start, Game.date <= end, or_(Game.home_team == team, Game.away_team == team))).limit(1).one_or_none()
            if exact:
                q = q.filter(or_(Game.home_team == team, Game.away_team == team))
            else:
                team_like = f"%{team}%"
                q = q.filter(or_(Game.home_team.like(team_like), Game.away_team.like(team_like)))
        games = q.order_by(Game.date.asc(), Game.game_pk.asc()).all()

        days_map: Dict[str, list] = {}
        tz_jp = zoneinfo.ZoneInfo("Asia/Tokyo")

        # preload raw status json per game
        raw_status: Dict[int, Dict[str, Any]] = {}
        if games:
            pks = [g.game_pk for g in games]
            for row in db.query(StatusCache).filter(StatusCache.game_pk.in_(pks)).all():
                try:
                    raw_status[row.game_pk] = json.loads(row.json)
                except Exception:
                    pass

        for g in games:
            dkey = g.date.isoformat()
            arr = days_map.setdefault(dkey, [])

            status = get_cached_status(g.game_pk)
            # derive times if we have raw status
            timeJP = None
            timeLocal = None
            rs = raw_status.get(g.game_pk)
            if rs:
                dt_str = rs.get("gameData", {}).get("datetime", {}).get("dateTime")
                venue_tz = rs.get("gameData", {}).get("venue", {}).get("timeZone", {}).get("id")
                try:
                    if dt_str:
                        from datetime import datetime
                        # dateTime is ISO UTC like 2025-08-20T23:05:00Z or with offset
                        dt_utc = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                        timeJP = dt_utc.astimezone(tz_jp).strftime("%Y-%m-%d %H:%M")
                        if venue_tz:
                            tz_local = zoneinfo.ZoneInfo(venue_tz)
                            timeLocal = dt_utc.astimezone(tz_local).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            item = {
                "gamePk": g.game_pk,
                "home": {"team": g.home_team, "R": g.home_runs, "H": g.home_hits, "E": g.home_errors, "HR": g.home_homers},
                "away": {"team": g.away_team, "R": g.away_runs, "H": g.away_hits, "E": g.away_errors, "HR": g.away_homers},
                "status": status,
                "timeJP": timeJP,
                "timeLocal": timeLocal,
            }
            arr.append(item)

        # Ensure all dates in month appear, even if no games
        out_days = []
        cur = start
        while cur <= end:
            dkey = cur.isoformat()
            out_days.append({"date": dkey, "games": days_map.get(dkey, [])})
            cur += timedelta(days=1)
        return {"team": team, "month": month, "days": out_days}
    finally:
        db.close()


@router.get("/calendar/teams")
def get_calendar_teams() -> Dict[str, Any]:
    db: Session = SessionLocal()
    try:
        q1 = db.query(Game.home_team.label("team")).distinct()
        q2 = db.query(Game.away_team.label("team")).distinct()
        union = q1.union(q2)
        names = [row.team for row in union if row.team]
        names = sorted(set(names))
        return {"teams": names}
    finally:
        db.close()


@router.get("/calendar/missing")
def get_calendar_missing(month: str = Query(..., description="YYYY-MM"),
                         team: str | None = Query(None, description="If provided, find days with zero games for this team (home or away)")) -> Dict[str, Any]:
    start, end = _month_range(month)
    db: Session = SessionLocal()
    try:
        filters = [Game.date >= start, Game.date <= end]
        if team:
            filters.append(or_(Game.home_team == team, Game.away_team == team))
        have = {d for (d,) in db.query(Game.date).filter(and_(*filters)).distinct().all()}
        out = []
        cur = start
        while cur <= end:
            if cur not in have:
                out.append(cur.isoformat())
            cur += timedelta(days=1)
        return {"missing": out}
    finally:
        db.close()
