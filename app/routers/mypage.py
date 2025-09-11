from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, date
from pydantic import BaseModel
from ..db import SessionLocal, FavoriteTeam, UserStep
from .auth import get_current_user, User

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class TeamIn(BaseModel):
    team: str

@router.get("/me/teams")
def list_favorite_teams(u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(FavoriteTeam).filter(FavoriteTeam.user_id == u.id).order_by(FavoriteTeam.id.asc()).all()
    return {"teams": [r.team for r in rows]}

@router.post("/me/teams")
def add_favorite_team(body: TeamIn, u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = (body.team or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="team required")
    exists = db.query(FavoriteTeam).filter(FavoriteTeam.user_id == u.id, FavoriteTeam.team == t).one_or_none()
    if exists:
        return {"added": False, "team": t}
    row = FavoriteTeam(user_id=u.id, team=t)
    db.add(row)
    db.commit()
    return {"added": True, "team": t}

@router.delete("/me/teams/{team}")
def remove_favorite_team(team: str, u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    affected = db.query(FavoriteTeam).filter(FavoriteTeam.user_id == u.id, FavoriteTeam.team == team).delete(synchronize_session=False)
    db.commit()
    return {"removed": affected > 0}

class StepsIn(BaseModel):
    steps: int
    date: str | None = None  # 'YYYY-MM-DD'

@router.get("/me/steps")
def get_steps(date_str: str | None = Query(None, alias="date"), u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d: date
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid date")
    else:
        d = datetime.utcnow().date()
    rec = db.query(UserStep).filter(UserStep.user_id == u.id, UserStep.date == d).one_or_none()
    if not rec:
        return {"date": d.isoformat(), "steps": 0, "exists": False}
    return {"date": d.isoformat(), "steps": rec.steps, "exists": True}

@router.post("/me/steps")
def upsert_steps(body: StepsIn, u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.steps is None or body.steps < 0:
        raise HTTPException(status_code=400, detail="invalid steps")
    d: date
    if body.date:
        try:
            d = datetime.strptime(body.date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid date")
    else:
        d = datetime.utcnow().date()
    rec = db.query(UserStep).filter(UserStep.user_id == u.id, UserStep.date == d).one_or_none()
    if rec:
        rec.steps = body.steps
        db.commit()
        return {"updated": True, "date": d.isoformat(), "steps": rec.steps}
    else:
        rec = UserStep(user_id=u.id, date=d, steps=body.steps)
        db.add(rec)
        db.commit()
        return {"created": True, "date": d.isoformat(), "steps": rec.steps}

@router.get("/me/steps/range")
def get_steps_range(month: str, u: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # month: YYYY-MM -> return list of {date, steps}
    try:
        y, m = month.split('-')
        y = int(y); m = int(m)
        from datetime import date as D, timedelta
        start = D(y, m, 1)
        end = D(y+1, 1, 1) - timedelta(days=1) if m == 12 else D(y, m+1, 1) - timedelta(days=1)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid month")
    rows = db.query(UserStep).filter(UserStep.user_id == u.id, UserStep.date >= start, UserStep.date <= end).all()
    out = { r.date.isoformat(): r.steps for r in rows }
    # Ensure all days appear
    cur = start
    res = []
    while cur <= end:
        d = cur.isoformat()
        res.append({"date": d, "steps": int(out.get(d, 0))})
        cur = cur + timedelta(days=1)
    return {"month": f"{start.year}-{str(start.month).zfill(2)}", "days": res}
