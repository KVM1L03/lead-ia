"""Tests for rate limiting — RunLimiter, RequestLimiter, and FastAPI wiring.

All Redis interaction uses fakeredis.aioredis.FakeRedis — no live Redis needed.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway import rate_limit
from api_gateway.db import get_session
from api_gateway.main import app
from api_gateway.rate_limit import (
    RequestLimiter,
    RunLimiter,
    enforce_run_limit,
)
from api_gateway.temporal import get_temporal_client

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def fake_redis() -> AsyncGenerator[Redis, None]:
    r: Redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_temporal() -> AsyncMock:
    client = AsyncMock()
    handle = MagicMock()
    handle.id = "wf-id"
    client.start_workflow = AsyncMock(return_value=handle)
    return client


_SEARCH_BODY = {
    "prompt": "dental clinics warsaw",
    "limit": 20,
    "sender_context": "I sell scheduling software",
}


# ── RunLimiter unit tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_limiter_allows_up_to_limit(fake_redis: Redis) -> None:
    limiter = RunLimiter(fake_redis, max_runs=20)
    for _ in range(20):
        assert await limiter.check_and_increment() is True


@pytest.mark.asyncio
async def test_run_limiter_blocks_at_limit(fake_redis: Redis) -> None:
    limiter = RunLimiter(fake_redis, max_runs=20)
    for _ in range(20):
        await limiter.check_and_increment()
    assert await limiter.check_and_increment() is False


@pytest.mark.asyncio
async def test_run_limiter_concurrent_atomicity(fake_redis: Redis) -> None:
    """Lua atomicity: exactly max_runs allowed under concurrent requests."""
    limiter = RunLimiter(fake_redis, max_runs=5)
    results = await asyncio.gather(*[limiter.check_and_increment() for _ in range(10)])
    assert sum(1 for r in results if r is True) == 5


@pytest.mark.asyncio
async def test_run_limiter_ttl_set_to_end_of_day(fake_redis: Redis) -> None:
    limiter = RunLimiter(fake_redis, max_runs=20)
    await limiter.check_and_increment()

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    ttl = await fake_redis.ttl(f"demo:runs:{today}")

    now = datetime.now(UTC)
    end_of_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    expected_max = int((end_of_day - now).total_seconds()) + 2
    assert 1 <= ttl <= expected_max


@pytest.mark.asyncio
async def test_run_limiter_ttl_not_reset_on_subsequent_calls(
    fake_redis: Redis,
) -> None:
    """TTL set only on first increment — later calls must not push it past midnight."""
    limiter = RunLimiter(fake_redis, max_runs=20)
    await limiter.check_and_increment()

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    ttl_after_first = await fake_redis.ttl(f"demo:runs:{today}")

    await limiter.check_and_increment()
    ttl_after_second = await fake_redis.ttl(f"demo:runs:{today}")

    assert ttl_after_second <= ttl_after_first


# ── RequestLimiter unit tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_limiter_allows_up_to_limit(fake_redis: Redis) -> None:
    limiter = RequestLimiter(fake_redis, max_per_minute=30)
    for _ in range(30):
        assert await limiter.check_and_increment("1.2.3.4") is True


@pytest.mark.asyncio
async def test_request_limiter_blocks_at_limit(fake_redis: Redis) -> None:
    limiter = RequestLimiter(fake_redis, max_per_minute=30)
    for _ in range(30):
        await limiter.check_and_increment("1.2.3.4")
    assert await limiter.check_and_increment("1.2.3.4") is False


@pytest.mark.asyncio
async def test_request_limiter_different_ips_independent(
    fake_redis: Redis,
) -> None:
    limiter = RequestLimiter(fake_redis, max_per_minute=2)
    assert await limiter.check_and_increment("1.1.1.1") is True
    assert await limiter.check_and_increment("1.1.1.1") is True
    assert await limiter.check_and_increment("1.1.1.1") is False
    assert await limiter.check_and_increment("2.2.2.2") is True


# ── enforce_run_limit dependency: DEMO_MODE=false bypasses Redis ──────────────


@pytest.mark.asyncio
async def test_demo_mode_false_no_redis_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """When DEMO_MODE=false, enforce_run_limit must return without calling Redis."""
    monkeypatch.setattr(rate_limit.settings, "DEMO_MODE", False)

    redis_called = False

    def _spy() -> Redis:
        nonlocal redis_called
        redis_called = True
        raise AssertionError("get_redis() must not be called when DEMO_MODE=false")

    monkeypatch.setattr(rate_limit, "get_redis", _spy)

    for _ in range(100):
        await enforce_run_limit()

    assert not redis_called


# ── FastAPI integration: 429 bodies and headers ───────────────────────────────


@pytest.fixture
async def http_with_exhausted_run_limit(
    fake_redis: Redis,
    mock_session: AsyncMock,
    mock_temporal: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Client where the daily run counter is already at 20 in fake Redis."""
    limiter = RunLimiter(fake_redis, max_runs=20)
    for _ in range(20):
        await limiter.check_and_increment()

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _run_limit_override() -> None:
        # Re-create limiter pointing at the same fake_redis instance
        inner = RunLimiter(fake_redis, max_runs=20)
        if not await inner.check_and_increment():
            from fastapi import HTTPException

            raise HTTPException(
                status_code=429,
                detail={
                    "error": "demo_run_limit",
                    "message": "Demo capped.",
                    "limit": 20,
                },
            )

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_temporal_client] = lambda: mock_temporal
    app.dependency_overrides[enforce_run_limit] = _run_limit_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_run_limit_429_json_body(
    http_with_exhausted_run_limit: AsyncClient,
) -> None:
    with patch("api_gateway.routes.leads.translate_prompt", return_value="dental"):
        resp = await http_with_exhausted_run_limit.post("/api/leads/search", json=_SEARCH_BODY)
    assert resp.status_code == 429
    body = resp.json()
    assert body["detail"]["error"] == "demo_run_limit"
    assert body["detail"]["limit"] == 20


@pytest.mark.asyncio
async def test_request_limit_429_retry_after(fake_redis: Redis) -> None:
    """31st request from same IP within a minute → 429 with Retry-After: 60."""
    # Pre-fill the per-minute counter to 30 for IP "1.2.3.4"
    req_limiter = RequestLimiter(fake_redis, max_per_minute=30)
    for _ in range(30):
        await req_limiter.check_and_increment("1.2.3.4")

    # Middleware is lazy: it calls get_redis() inside dispatch.
    # Patch get_redis to return fake_redis so the 31st call hits the same counter.
    with (
        patch("api_gateway.rate_limit.settings.DEMO_MODE", True),
        patch("api_gateway.rate_limit.get_redis", return_value=fake_redis),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Forwarded-For": "1.2.3.4"},
        ) as client:
            resp = await client.get("/health")

    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "60"
    assert "Too many requests" in resp.json()["detail"]
