from sqlalchemy import create_engine, Column, Integer, String, Date, ForeignKey, UniqueConstraint, Text, DateTime, func, text, Boolean
try:
    from sqlalchemy.dialects.mysql import MEDIUMTEXT as MYSQL_MEDIUMTEXT
except Exception:  # pragma: no cover
    MYSQL_MEDIUMTEXT = None
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
# NOTE: If you previously saw a broken line like 'import setti' it was a partial edit artifact.
# Ensure we import settings correctly from local config module.
from .config import settings

Base = declarative_base()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# ---- Auth Models ----
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(191), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), default="Normal")  # admin | Premium | Subscribe | Normal
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, nullable=False, server_default=text('1'))
    # soft delete could be represented by is_active False; keep simple

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    token = Column(String(191), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    revoked_at = Column(DateTime, nullable=True)

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    token = Column(String(191), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    game_pk = Column(Integer, unique=True, index=True)
    home_team = Column(String(64))
    away_team = Column(String(64))
    home_runs = Column(Integer, default=0)
    away_runs = Column(Integer, default=0)
    home_hits = Column(Integer, default=0)
    away_hits = Column(Integer, default=0)
    home_errors = Column(Integer, default=0)
    away_errors = Column(Integer, default=0)
    home_homers = Column(Integer, default=0)
    away_homers = Column(Integer, default=0)

    batters = relationship("BatterStat", back_populates="game", cascade="all, delete-orphan")

class BatterStat(Base):
    __tablename__ = "batter_stats"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    date = Column(Date, index=True)
    team = Column(String(64), index=True)
    name = Column(String(191))
    position = Column(String(16))
    ab = Column(Integer)
    r = Column(Integer)
    h = Column(Integer)
    hr = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    rbi = Column(Integer)
    bb = Column(Integer)
    so = Column(Integer)
    lob = Column(Integer)

    game = relationship("Game", back_populates="batters")
    __table_args__ = (
        UniqueConstraint("game_id", "team", "name", name="uq_game_team_player"),
    )

class PitcherStat(Base):
    __tablename__ = "pitcher_stats"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    date = Column(Date, index=True)
    team = Column(String(64), index=True)
    name = Column(String(191))
    ip = Column(String(16))  # innings pitched string form
    so = Column(Integer, default=0)
    bb = Column(Integer, default=0)
    h = Column(Integer, default=0)
    hr = Column(Integer, default=0)
    r = Column(Integer, default=0)
    er = Column(Integer, default=0)
    wp = Column(Integer, default=0)
    bk = Column(Integer, default=0)
    baa_num = Column(Integer, default=0)  # hits
    baa_den = Column(Integer, default=0)  # at bats
    __table_args__ = (
        UniqueConstraint("game_id", "team", "name", name="uq_game_team_pitcher"),
    )


class BoxscoreCache(Base):
    __tablename__ = "boxscore_cache"
    game_pk = Column(Integer, primary_key=True, index=True)
    _JSON_TEXT = Text().with_variant(MYSQL_MEDIUMTEXT(), 'mysql') if MYSQL_MEDIUMTEXT else Text()
    json = Column(_JSON_TEXT, nullable=False)
    hash = Column(String(64), nullable=True, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class LinescoreCache(Base):
    __tablename__ = "linescore_cache"
    game_pk = Column(Integer, primary_key=True, index=True)
    _JSON_TEXT = Text().with_variant(MYSQL_MEDIUMTEXT(), 'mysql') if MYSQL_MEDIUMTEXT else Text()
    json = Column(_JSON_TEXT, nullable=False)
    hash = Column(String(64), nullable=True, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class StatusCache(Base):
    __tablename__ = "status_cache"
    game_pk = Column(Integer, primary_key=True, index=True)
    _JSON_TEXT = Text().with_variant(MYSQL_MEDIUMTEXT(), 'mysql') if MYSQL_MEDIUMTEXT else Text()
    json = Column(_JSON_TEXT, nullable=False)
    hash = Column(String(64), nullable=True, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ---- User Profile Extensions ----
class FavoriteTeam(Base):
    __tablename__ = "favorite_teams"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    team = Column(String(64), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("user_id", "team", name="uq_user_team"),
    )

class UserStep(Base):
    __tablename__ = "user_steps"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(Date, nullable=False)
    steps = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_user_date"),
    )


def init_db():
    # Create tables for a fresh database. Further schema changes should be handled via Alembic migrations.
    Base.metadata.create_all(bind=engine)
