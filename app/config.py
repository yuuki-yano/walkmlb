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
    # Optional basic auth (either token OR basic accepted)
    admin_basic_user: str | None = os.getenv("ADMIN_BASIC_USER") or None
    admin_basic_pass: str | None = os.getenv("ADMIN_BASIC_PASS") or None

    # Cache retention (days) for *_cache tables (boxscore/linescore/status)
    cache_retention_days: int = int(os.getenv("CACHE_RETENTION_DAYS", 3))
    maintenance_mode: bool = bool(int(os.getenv("MAINTENANCE_MODE", "0")))
    maintenance_message: str | None = os.getenv("MAINTENANCE_MESSAGE") or None
    announcement_message: str | None = os.getenv("ANNOUNCEMENT_MESSAGE") or None

    # Auth / Security
    auth_secret: str = os.getenv("AUTH_SECRET", "change-me-secret")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60*24))  # default 1 day
    refresh_token_expire_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 30))
    allow_self_signup: bool = os.getenv("ALLOW_SELF_SIGNUP", "1") in ("1","true","TRUE","yes")
    # Optional initial admin bootstrap (created at startup if no users exist)
    admin_bootstrap_email: str | None = os.getenv("ADMIN_BOOTSTRAP_EMAIL") or None
    admin_bootstrap_password: str | None = os.getenv("ADMIN_BOOTSTRAP_PASSWORD") or None

    # Login protection
    auth_max_failed_logins: int = int(os.getenv("AUTH_MAX_FAILED_LOGINS", 5))
    auth_lock_minutes: int = int(os.getenv("AUTH_LOCK_MINUTES", 15))

    # Verbose updater logging (per-game logs)
    updater_log_detail: bool = os.getenv("UPDATER_LOG_DETAIL", "0") in ("1", "true", "TRUE", "yes", "on")

settings = Settings()
