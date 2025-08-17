import datetime as dt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..mlb_api import fetch_schedule, fetch_boxscore, extract_game_summary, parse_boxscore_totals, iter_batters
from .. import crud

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/import")
async def import_date(date: str, db: Session = Depends(get_db)):
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    games = await fetch_schedule(d)
    imported = 0
    for g in games:
        game_pk, home_team, away_team, gdate = extract_game_summary(g)
        box = await fetch_boxscore(game_pk)
        totals = parse_boxscore_totals(box)
        game = crud.upsert_game(
            db, date=gdate, game_pk=game_pk, home_team=home_team, away_team=away_team,
            home_totals=totals["home"], away_totals=totals["away"]
        )
        db.flush()
        for row in iter_batters(box):
            crud.upsert_batter(db, game=game, date=gdate, row=row)
        imported += 1
    db.commit()
    return {"date": date, "games": imported}
