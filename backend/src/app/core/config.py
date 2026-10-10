from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables (and `.env` when present)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Backend API"
    environment: str = "development"
    api_prefix: str = "/api"

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    database_echo: bool = False

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
