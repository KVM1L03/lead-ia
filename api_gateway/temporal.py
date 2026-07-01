"""Shared Temporal client dependency for all api_gateway routes.

One process-wide client is created lazily on the first request that needs it.
Both /api/leads/search and /api/leads/status/{id} use this dependency.
"""

from __future__ import annotations

import os

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

_temporal_client: Client | None = None


async def get_temporal_client() -> Client:
    """FastAPI dependency — returns the shared Temporal client (lazy init)."""
    global _temporal_client
    if _temporal_client is None:
        address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
        _temporal_client = await Client.connect(address, data_converter=pydantic_data_converter)
    return _temporal_client
