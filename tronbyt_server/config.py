"""Application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    SECRET_KEY: str = "lksdj;as987q3908475ukjhfgklauy983475iuhdfkjghairutyh"
    USERS_DIR: str = "users"
    DATA_DIR: str = "data"
    PRODUCTION: str = "1"
    DB_FILE: str = "users/usersdb.sqlite"
    LANGUAGES: list[str] = ["en", "de"]
    MAX_USERS: int = 100
    ENABLE_USER_REGISTRATION: str = "0"
    LOG_LEVEL: str = "WARNING"
    SYSTEM_APPS_REPO: str = "https://github.com/tronbyt/apps.git"

    # Supabase settings (required for multi-tenant mode)
    AUTH_MODE: Literal["local", "supabase"] = "local"
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # Rate limiting settings
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_BURST: int = 10


@lru_cache
def get_settings() -> Settings:
    """Return the settings object."""
    return Settings()
