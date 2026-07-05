from fastapi import FastAPI

from api_gateway.rate_limit import RateLimitMiddleware
from api_gateway.routes import approve, config, leads, status

app = FastAPI()

# Layer 2: per-IP request rate limit.
# Always registered; short-circuits (no Redis call) when DEMO_MODE=false.
# RequestLimiter is created lazily inside dispatch() — no Redis connection at startup.
app.add_middleware(RateLimitMiddleware)

app.include_router(leads.router)
app.include_router(status.router)
app.include_router(approve.router)
app.include_router(config.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
