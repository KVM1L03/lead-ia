"""GET /api/config — expose runtime feature flags to the frontend.

The frontend uses this to decide:
  - Whether to show the /history page (persistence_enabled).
  - Whether to poll for results or render them inline (execution_mode).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from api_gateway.config import settings

router = APIRouter(prefix="/api")


class ConfigResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    persistence_enabled: bool
    execution_mode: Literal["temporal", "sync"]


@router.get("/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    return ConfigResponse(
        persistence_enabled=settings.PERSISTENCE_ENABLED,
        execution_mode=settings.EXECUTION_MODE,
    )
