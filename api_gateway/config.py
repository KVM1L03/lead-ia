"""Settings for the API gateway, read from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        strict=True,
    )

    DEMO_MODE: bool = False
    DEMO_MAX_RUNS_PER_DAY: int = 20
    DEMO_MAX_REQUESTS_PER_MINUTE: int = 30
    REDIS_URL: str = "redis://localhost:6379"


settings = Settings()
