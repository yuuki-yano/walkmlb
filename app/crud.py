import datetime as dt
from sqlalchemy.orm import Session
from . import db
from .config import settings


def upsert_game(session: Session, *, date: dt.date, game_pk: int, home_team: str, away_team: str,
                 home_totals: dict, away_totals: dict) -> db.Game:
    game = session.query(db.Game).filter_by(game_pk=game_pk).one_or_none()
    if not game:
        game = db.Game(game_pk=game_pk, date=date)
        session.add(game)
    game.home_team = home_team
    game.away_team = away_team
    game.home_runs = int(home_totals.get("runs", 0))
    game.away_runs = int(away_totals.get("runs", 0))
    game.home_hits = int(home_totals.get("hits", 0))
    game.away_hits = int(away_totals.get("hits", 0))
    game.home_errors = int(home_totals.get("errors", 0))
    game.away_errors = int(away_totals.get("errors", 0))
    game.home_homers = int(home_totals.get("homers", 0))
    game.away_homers = int(away_totals.get("homers", 0))
    return game


def upsert_batter(session: Session, *, game: db.Game, date: dt.date, row: dict):
    exists = session.query(db.BatterStat).filter_by(
        game_id=game.id, team=row["team"], name=row["name"],
    ).one_or_none()
    if not exists:
        exists = db.BatterStat(
            game_id=game.id, date=date, team=row["team"], name=row["name"], position=row.get("position", "")
        )
        session.add(exists)
    exists.ab = int(row.get("ab", 0))
    exists.r = int(row.get("r", 0))
    exists.h = int(row.get("h", 0))
    exists.rbi = int(row.get("rbi", 0))
    exists.bb = int(row.get("bb", 0))
    exists.so = int(row.get("so", 0))
    exists.lob = int(row.get("lob", 0))
    exists.hr = int(row.get("hr", 0))
    exists.errors = int(row.get("errors", 0))

def upsert_pitcher(session: Session, *, game: db.Game, date: dt.date, team: str, row: dict):
    exists = session.query(db.PitcherStat).filter_by(
        game_id=game.id, team=team, name=row["name"],
    ).one_or_none()
    if not exists:
        exists = db.PitcherStat(
            game_id=game.id, date=date, team=team, name=row["name"],
        )
        session.add(exists)
    exists.ip = row.get("IP") or "0.0"
    exists.so = int(row.get("SO", 0))
    exists.bb = int(row.get("BB", 0))
    exists.h = int(row.get("H", 0))
    exists.hr = int(row.get("HR", 0))
    exists.r = int(row.get("R", 0))
    exists.er = int(row.get("ER", 0))
    exists.wp = int(row.get("WP", 0))
    exists.bk = int(row.get("BK", 0))
    exists.baa_num = int(row.get("H", 0))
    exists.baa_den = int(row.get("AB", 0))


def compute_steps_for_date(session: Session, date: dt.date, team: str | None = None) -> int:
    """Compute steps for a date.

    Behavior update (2025-09-12):
      * When a specific team is provided, only that team's stats are counted (previously opponent team was also included, inflating values).
      * Team-specific calculation now uses PLAYER-LEVEL weights (walk_per_*_player) and includes strikeouts, matching the per-game player endpoint aggregation shown on Top page.
      * When no team is provided, legacy behavior (all games both sides with TEAM-level weights) is retained for a broad 'league total'.
    """
    if not team:
        # League-wide total using team-level weights (unchanged legacy behavior)
        q = session.query(db.Game).filter(db.Game.date == date)
        totals = {"hits": 0, "homers": 0, "errors": 0}
        for g in q:
            totals["hits"] += g.home_hits + g.away_hits
            totals["homers"] += g.home_homers + g.away_homers
            totals["errors"] += g.home_errors + g.away_errors
        steps = (
            settings.walk_base
            + settings.walk_per_hit * totals["hits"]
            + settings.walk_per_hr * totals["homers"]
            + settings.walk_per_error * totals["errors"]
        )
        return max(0, int(steps))

    # Team-specific: aggregate player stats from BatterStat for accuracy & strikeouts
    from .db import BatterStat, Game as GameModel
    rows = session.query(BatterStat).filter(BatterStat.date == date, BatterStat.team == team).all()
    hits = sum(r.h for r in rows)
    homers = sum(getattr(r, 'hr', 0) for r in rows)
    errors = sum(getattr(r, 'errors', 0) for r in rows)
    strikeouts = sum(r.so for r in rows)
    if not rows:
        # Fallback: if no BatterStat yet (e.g., early live game before persistence), derive from Game row side-only
        gq = session.query(GameModel).filter(GameModel.date == date, (GameModel.home_team == team) | (GameModel.away_team == team))
        for g in gq:
            if g.home_team == team:
                hits += g.home_hits
                homers += g.home_homers
                errors += g.home_errors
            else:
                hits += g.away_hits
                homers += g.away_homers
                errors += g.away_errors
        # strikeouts unavailable without batter stats; treat as 0
    steps = (
        settings.walk_base
        + settings.walk_per_hit_player * hits
        + settings.walk_per_hr_player * homers
        + settings.walk_per_error_player * errors
        + settings.walk_per_so_player * strikeouts
    )
    return max(0, int(steps))
