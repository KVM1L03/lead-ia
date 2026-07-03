"""Demo-mode abuse protection — two independent rate-limiting layers.

Layer 1 — RunLimiter (wallet guard):
  Global daily cap on workflow runs. Counter in Redis; MULTI/EXEC pipeline
  with EXPIRE NX makes INCR + conditional TTL-set atomic.

Layer 2 — RequestLimiter (server guard):
  Per-IP per-minute request cap. MULTI/EXEC pipeline with unconditional
  EXPIRE 60 s. The key encodes the minute, so resetting TTL on each call
  is harmless.

Both layers are no-ops when DEMO_MODE=false (zero Redis calls).
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

from api_gateway.config import settings

# ── Redis singleton ────────────────────────────────────────────────────────────

_redis: Redis[str] | None = None


def get_redis() -> Redis[str]:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


# ── RunLimiter — Layer 1 (wallet guard) ───────────────────────────────────────
#
# WHY atomicity matters:
#   A naive two-step (INCR then EXPIRE as separate commands) has a crash window:
#     1. INCR succeeds: key exists with count=1, NO TTL set.
#     2. Process crashes (Cloud Run scale-to-zero, OOM kill) before EXPIRE runs.
#     → key persists forever; every future run for that day is blocked.
#
# HOW we fix it — MULTI/EXEC pipeline + EXPIRE NX:
#   MULTI/EXEC wraps both INCR and EXPIRE in a single atomic transaction.
#   EXPIRE NX (Redis 7.0+) sets the TTL *only if the key has no TTL*, so
#   subsequent increments don't push the expiry past midnight.
#   The result is identical to a Lua script but uses no external interpreter.


class RunLimiter:
    """Global daily cap on workflow runs. Key: demo:runs:{YYYY-MM-DD} (UTC)."""

    def __init__(self, redis: Redis[str], max_runs: int) -> None:
        self._redis = redis
        self._max_runs = max_runs

    async def check_and_increment(self) -> bool:
        """Atomically increment today's run counter.

        Returns True if the run is allowed (count ≤ max_runs), False if capped.
        TTL is set to seconds remaining until end of UTC day, on first write only
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


# ── RequestLimiter — Layer 2 (server guard) ───────────────────────────────────


class RequestLimiter:
    """Per-IP fixed-window cap. Key: demo:reqs:{ip}:{YYYY-MM-DDTHH:MM} (UTC)."""

    def __init__(self, redis: Redis[str], max_per_minute: int) -> None:
        self._redis = redis
        self._max_per_minute = max_per_minute

    async def check_and_increment(self, ip: str) -> bool:
        """Atomically increment this IP's per-minute counter via MULTI/EXEC.

        Returns True if the request is allowed, False if over limit.
        Unconditional EXPIRE 60 s is fine: the key already encodes the minute,
        so resetting the TTL on each request doesn't extend the window.
        """
        minute = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")
        key = f"demo:reqs:{ip}:{minute}"

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 60)
            results = await pipe.execute()

        return int(results[0]) <= self._max_per_minute


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

    RequestLimiter is created lazily inside dispatch() so that get_redis() is
    never called at import time — this keeps tests simple (patch get_redis) and
    avoids a connection attempt when Redis is not running.
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

        limiter = RequestLimiter(get_redis(), settings.DEMO_MAX_REQUESTS_PER_MINUTE)
        if not await limiter.check_and_increment(_client_ip(request)):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)


# ── Dependency — Layer 1 wiring ────────────────────────────────────────────────


async def enforce_run_limit() -> None:
    """FastAPI dependency: enforce global daily run cap when DEMO_MODE=true.

    Short-circuits with no Redis call when DEMO_MODE=false.
    Raises HTTP 429 with a clear JSON body when the day's cap is reached.
    """
    if not settings.DEMO_MODE:
        return

    limiter = RunLimiter(get_redis(), settings.DEMO_MAX_RUNS_PER_DAY)
    if not await limiter.check_and_increment():
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
