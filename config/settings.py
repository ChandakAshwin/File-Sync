import os

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except Exception:  # pragma: no cover - fallback for environments without pydantic-settings
    try:
        from pydantic import BaseModel as BaseSettings  # type: ignore
        class SettingsConfigDict(dict):  # type: ignore
            pass
    except Exception:
        class BaseSettings:  # type: ignore
            pass
        class SettingsConfigDict(dict):  # type: ignore
            pass

# Resolve project root and absolute path to .env regardless of CWD
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


class Settings(BaseSettings):
    """
    Central configuration for Wokelo File Sync.

    Values are loaded from environment variables and optionally from a local .env file
    (not committed). Defaults are reasonable for local development on WSL/Windows.
    """

    # Database and infra
    DATABASE_URL: str = "postgresql+psycopg2://filesync:password@localhost:5432/filesync_dev"
    # Back-compat name if other modules use DB_URL
    DB_URL: str | None = None

    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    ELASTICSEARCH_URL: str = "http://127.0.0.1:9200"

    # Scheduling defaults (can be overridden per-CCPair)
    INDEX_CHECK_INTERVAL_MINUTES: int = 10
    PRUNE_CHECK_INTERVAL_MINUTES: int = 60

    # Storage directory for local cached files
    STORAGE_DIR: str = "data/cache"

    # Box OAuth (override via .env in real usage)
    BOX_CLIENT_ID: str | None = None
    BOX_CLIENT_SECRET: str | None = None
    BOX_REDIRECT_URI: str = "http://localhost:8000/auth/box/callback"

    # pydantic-settings v2 style config; ignore unknown env keys like POSTGRES_*, LOG_LEVEL,
    # ELASTIC_CLIENT_APIVERSIONING, etc., so they don't raise ValidationError
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")


settings = Settings()
# If DB_URL was not explicitly provided, mirror DATABASE_URL for backwards compatibility
if settings.DB_URL is None:
    object.__setattr__(settings, "DB_URL", settings.DATABASE_URL)
