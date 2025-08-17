from sqlalchemy import create_engine, Column, Integer, String, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from .config import settings

Base = declarative_base()
engine = create_engine(
    settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    game_pk = Column(Integer, unique=True, index=True)
    home_team = Column(String)
    away_team = Column(String)
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
    team = Column(String, index=True)
    name = Column(String)
    position = Column(String)
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


def init_db():
    Base.metadata.create_all(bind=engine)
