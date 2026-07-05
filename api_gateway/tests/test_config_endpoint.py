"""Tests for GET /api/config and status degradation when persistence is off."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from api_gateway.db import get_session_maybe
from api_gateway.main import app
from api_gateway.temporal import get_temporal_client_maybe


@pytest.fixture
async def http() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ── /api/config tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_default_values(http: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api_gateway.routes.config.settings.PERSISTENCE_ENABLED", True)
    monkeypatch.setattr("api_gateway.routes.config.settings.EXECUTION_MODE", "temporal")
    resp = await http.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["persistence_enabled"] is True
    assert data["execution_mode"] == "temporal"


@pytest.mark.asyncio
async def test_config_demo_mode_values(http: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api_gateway.routes.config.settings.PERSISTENCE_ENABLED", False)
    monkeypatch.setattr("api_gateway.routes.config.settings.EXECUTION_MODE", "sync")
    resp = await http.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["persistence_enabled"] is False
    assert data["execution_mode"] == "sync"


# ── Status degradation when persistence is off ────────────────────────────────


@pytest.fixture
async def http_no_persist() -> AsyncGenerator[AsyncClient, None]:
    async def _no_session() -> AsyncGenerator[None, None]:
        yield None

    app.dependency_overrides[get_session_maybe] = _no_session
    app.dependency_overrides[get_temporal_client_maybe] = lambda: AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_status_returns_503_when_persistence_disabled(
    http_no_persist: AsyncClient,
) -> None:
    """When session is None (PERSISTENCE_ENABLED=False), /status returns 503."""
    resp = await http_no_persist.get("/api/leads/status/some-run-id")
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"] == "persistence_disabled"
