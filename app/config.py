import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./walkmlb.db")
    base_path: str = os.getenv("BASE_PATH", "")
    # Timezone used by updater to decide the 'current' MLB date
    update_tz: str = os.getenv("UPDATE_TZ", "America/New_York")
    walk_base: int = int(os.getenv("WALK_BASE", 6000))
    walk_per_hit: int = int(os.getenv("WALK_PER_HIT", 100))
    walk_per_hr: int = int(os.getenv("WALK_PER_HR", 300))
    walk_per_error: int = int(os.getenv("WALK_PER_ERROR", 50))

    # Player-based weights (detail page). By default: hits/HR reduce steps, errors increase steps.
    walk_per_hit_player: int = int(os.getenv("WALK_PER_HIT_PLAYER", -100))
    walk_per_hr_player: int = int(os.getenv("WALK_PER_HR_PLAYER", -300))
    walk_per_error_player: int = int(os.getenv("WALK_PER_ERROR_PLAYER", 50))
    walk_per_so_player: int = int(os.getenv("WALK_PER_SO_PLAYER", 100))

    # Simple admin authentication token for protected endpoints
    admin_token: str | None = os.getenv("ADMIN_TOKEN") or None

    # Cache retention (days) for *_cache tables (boxscore/linescore/status)
    cache_retention_days: int = int(os.getenv("CACHE_RETENTION_DAYS", 3))

    # Verbose updater logging (per-game logs)
    updater_log_detail: bool = os.getenv("UPDATER_LOG_DETAIL", "0") in ("1", "true", "TRUE", "yes", "on")

settings = Settings()
