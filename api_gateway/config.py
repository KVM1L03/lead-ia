"""Settings for the API gateway, read from environment / .env."""

from __future__ import annotations

from typing import Literal

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
    # Hard cap on leads processed in sync mode to prevent Cloud Run timeout.
    # A 200-lead synchronous request would exceed the 60s Cloud Run request timeout.
    DEMO_MAX_LEADS_SYNC: int = 25

    REDIS_URL: str = "redis://localhost:6379"

    # Selects the rate-limit counter backend.
    # redis  — Redis-backed (durable across restarts, multi-instance safe)
    # memory — in-process dict (soft guard only; resets on restart/cold start)
    #          DO NOT rely on memory for cost protection — use GCP budget caps.
    RATE_LIMIT_BACKEND: Literal["redis", "memory"] = "redis"

    # When False: skip all DB writes. /history shows disabled state.
    PERSISTENCE_ENABLED: bool = True

    # Controls how POST /api/leads/search executes the pipeline.
    # temporal — start a Temporal workflow (local/full-stack default)
    # sync     — run pipeline inline, return results in one HTTP response (demo)
    EXECUTION_MODE: Literal["temporal", "sync"] = "temporal"


settings = Settings()
