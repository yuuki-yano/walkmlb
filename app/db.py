from sqlalchemy import create_engine, Column, Integer, String, Date, ForeignKey, UniqueConstraint, Text, DateTime, func, text
try:
    from sqlalchemy.dialects.mysql import MEDIUMTEXT as MYSQL_MEDIUMTEXT
except Exception:  # pragma: no cover
    MYSQL_MEDIUMTEXT = None
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from .config import settings

Base = declarative_base()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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
    rbi = Column(Integer)
    bb = Column(Integer)
    so = Column(Integer)
    lob = Column(Integer)

    game = relationship("Game", back_populates="batters")
    __table_args__ = (
        UniqueConstraint("game_id", "team", "name", name="uq_game_team_player"),
    )


class BoxscoreCache(Base):
    __tablename__ = "boxscore_cache"
    game_pk = Column(Integer, primary_key=True, index=True)
    _JSON_TEXT = Text().with_variant(MYSQL_MEDIUMTEXT(), 'mysql') if MYSQL_MEDIUMTEXT else Text()
    json = Column(_JSON_TEXT, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class LinescoreCache(Base):
    __tablename__ = "linescore_cache"
    game_pk = Column(Integer, primary_key=True, index=True)
    _JSON_TEXT = Text().with_variant(MYSQL_MEDIUMTEXT(), 'mysql') if MYSQL_MEDIUMTEXT else Text()
    json = Column(_JSON_TEXT, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class StatusCache(Base):
    __tablename__ = "status_cache"
    game_pk = Column(Integer, primary_key=True, index=True)
    _JSON_TEXT = Text().with_variant(MYSQL_MEDIUMTEXT(), 'mysql') if MYSQL_MEDIUMTEXT else Text()
    json = Column(_JSON_TEXT, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


def init_db():
    Base.metadata.create_all(bind=engine)
    # Ensure MySQL columns can store large JSON payloads (MEDIUMTEXT ~16MB)
    if settings.database_url.startswith("mysql") and MYSQL_MEDIUMTEXT:
        try:
            with engine.begin() as conn:
                for tbl in ("boxscore_cache", "linescore_cache", "status_cache"):
                    try:
                        conn.execute(text(f"ALTER TABLE `{tbl}` MODIFY COLUMN `json` MEDIUMTEXT"))
                    except Exception:
                        # Ignore if already MEDIUMTEXT or if table/column doesn't exist yet
                        pass
        except Exception:
            # Do not block app startup on migration best-effort
            pass
