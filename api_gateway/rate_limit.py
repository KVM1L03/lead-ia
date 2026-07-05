"""Demo-mode abuse protection — two independent rate-limiting layers.

Layer 1 — Run limit (wallet guard):
  Global daily cap on workflow runs.

Layer 2 — Request limit (server guard):
  Per-IP per-minute request cap.

Both layers are no-ops when DEMO_MODE=false (zero Redis or memory calls).

Backend selection:
  RATE_LIMIT_BACKEND=redis   — Redis-backed (durable, multi-instance safe).
  RATE_LIMIT_BACKEND=memory  — In-process dict. SOFT GUARD ONLY: resets on
    process restart / Cloud Run cold start. With max-instances>1 the effective
    limit is per-instance. Do NOT rely on this for cost protection — GCP budget
    caps are the real backstop (T5.4b-NEW).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from api_gateway.config import settings as settings  # explicit re-export for mypy

# ── Redis singleton ────────────────────────────────────────────────────────────

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


# ── RunLimiter — Redis-backed Layer 1 ─────────────────────────────────────────
#
# WHY atomicity matters:
#   A naive two-step (INCR then EXPIRE as separate commands) has a crash window:
#     1. INCR succeeds: key exists with count=1, NO TTL set.
#     2. Process crashes before EXPIRE runs → key persists forever.
#   MULTI/EXEC + EXPIRE NX fixes this atomically.


class RunLimiter:
    """Global daily cap on workflow runs. Key: demo:runs:{YYYY-MM-DD} (UTC)."""

    def __init__(self, redis: Redis, max_runs: int) -> None:
        self._redis = redis
        self._max_runs = max_runs

    async def check_and_increment(self) -> bool:
        """Atomically increment today's run counter.

        Returns True if allowed (count ≤ max_runs), False if capped.
        TTL set to seconds remaining until end of UTC day, on first write only
        (via EXPIRE NX — no-op if the key already has a TTL).
        """
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        key = f"demo:runs:{today}"

        now = datetime.now(UTC)
        end_of_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        ttl = int((end_of_day - now).total_seconds()) + 1

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, ttl, nx=True)  # NX: set TTL only if no TTL exists
            results = await pipe.execute()

        return int(results[0]) <= self._max_runs


# ── RequestLimiter — Redis-backed Layer 2 ─────────────────────────────────────


class RequestLimiter:
    """Per-IP fixed-window cap. Key: demo:reqs:{ip}:{YYYY-MM-DDTHH:MM} (UTC)."""

    def __init__(self, redis: Redis, max_per_minute: int) -> None:
        self._redis = redis
        self._max_per_minute = max_per_minute

    async def check_and_increment(self, ip: str) -> bool:
        """Atomically increment this IP's per-minute counter via MULTI/EXEC.

        Returns True if allowed, False if over limit.
        Unconditional EXPIRE 60 s is fine: the key already encodes the minute.
        """
        minute = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")
        key = f"demo:reqs:{ip}:{minute}"

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 60)
            results = await pipe.execute()

        return int(results[0]) <= self._max_per_minute


# ── MemoryRateLimitStore — in-process counters (demo) ─────────────────────────


class MemoryRateLimitStore:
    """In-process rate limit counters. EPHEMERAL — resets on process restart.

    Used when RATE_LIMIT_BACKEND=memory (live demo, no Redis).
    This is a SOFT UX GUARD ONLY. Hard cost protection lives in GCP budget caps.
    With Cloud Run max-instances>1 the effective limit is per-instance — the
    real cap is looser by N instances. Acceptable for a demo; budget cap backstops.
    """

    def __init__(self, max_runs: int, max_per_minute: int) -> None:
        self._max_runs = max_runs
        self._max_per_minute = max_per_minute
        self._run_counts: dict[str, int] = {}
        self._request_counts: dict[str, int] = {}

    async def check_run(self) -> bool:
        """Increment today's run counter (UTC date key). Returns True if allowed."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        count = self._run_counts.get(today, 0) + 1
        self._run_counts[today] = count
        return count <= self._max_runs

    async def check_request(self, ip: str) -> bool:
        """Increment this IP's per-minute counter. Returns True if allowed."""
        minute = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")
        key = f"{ip}:{minute}"
        count = self._request_counts.get(key, 0) + 1
        self._request_counts[key] = count
        return count <= self._max_per_minute


# ── RedisRateLimitStore — Redis-backed store (wraps RunLimiter/RequestLimiter) ─


class RedisRateLimitStore:
    """Redis-backed rate limit store for production/local use."""

    def __init__(self, redis: Redis, max_runs: int, max_per_minute: int) -> None:
        self._run_limiter = RunLimiter(redis, max_runs)
        self._req_limiter = RequestLimiter(redis, max_per_minute)

    async def check_run(self) -> bool:
        return await self._run_limiter.check_and_increment()

    async def check_request(self, ip: str) -> bool:
        return await self._req_limiter.check_and_increment(ip)


# ── Store factory ──────────────────────────────────────────────────────────────

_memory_store: MemoryRateLimitStore | None = None
_redis_store: RedisRateLimitStore | None = None


def get_rate_limit_store() -> MemoryRateLimitStore | RedisRateLimitStore:
    """Return the process-wide rate limit store for the configured backend.

    When RATE_LIMIT_BACKEND=memory: get_redis() is NEVER called.
    When RATE_LIMIT_BACKEND=redis: get_redis() is called lazily on first use.
    """
    global _memory_store, _redis_store
    if settings.RATE_LIMIT_BACKEND == "memory":
        if _memory_store is None:
            _memory_store = MemoryRateLimitStore(
                max_runs=settings.DEMO_MAX_RUNS_PER_DAY,
                max_per_minute=settings.DEMO_MAX_REQUESTS_PER_MINUTE,
            )
        return _memory_store
    if _redis_store is None:
        _redis_store = RedisRateLimitStore(
            get_redis(),
            max_runs=settings.DEMO_MAX_RUNS_PER_DAY,
            max_per_minute=settings.DEMO_MAX_REQUESTS_PER_MINUTE,
        )
    return _redis_store


# ── IP extraction ──────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> str:
    """Return the real client IP, reading X-Forwarded-For before socket peer.

    Cloud Run's load balancer overwrites the socket peer with its own address.
    The real client IP is the first value in X-Forwarded-For.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Middleware — Layer 2 wiring ────────────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP request rate limit. Always registered; no-ops when DEMO_MODE=false.

    get_rate_limit_store() is called lazily inside dispatch() so that get_redis()
    is never called at import time — this keeps tests simple and avoids a
    connection attempt when Redis is not running.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not settings.DEMO_MODE:
            return await call_next(request)
        store = get_rate_limit_store()
        if not await store.check_request(_client_ip(request)):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)


# ── Dependency — Layer 1 wiring ────────────────────────────────────────────────


async def enforce_run_limit() -> None:
    """FastAPI dependency: enforce global daily run cap when DEMO_MODE=true.

    Short-circuits with no store access when DEMO_MODE=false.
    Raises HTTP 429 with a clear JSON body when the day's cap is reached.
    """
    if not settings.DEMO_MODE:
        return

    store = get_rate_limit_store()
    if not await store.check_run():
        raise HTTPException(
            status_code=429,
            detail={
                "error": "demo_run_limit",
                "message": (
                    f"This demo is capped at {settings.DEMO_MAX_RUNS_PER_DAY} workflow "
                    "runs per day to control costs. Fork the repo to run without limits: "
                    "https://github.com/KVM1L03/lead-ia"
                ),
                "limit": settings.DEMO_MAX_RUNS_PER_DAY,
            },
        )
