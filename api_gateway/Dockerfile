# ── Stage 1: build venv ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --compile-bytecode

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# curl is needed for the docker-compose healthcheck probe
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --no-create-home --shell /bin/false appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

# ai_worker/ is required: leads.py imports LeadGenerationWorkflow for the Temporal SDK type
# maps_bridge/ is required: MAPS_TRANSPORT=inline calls maps_bridge.provider_factory in-process
COPY api_gateway/ ./api_gateway/
COPY ai_worker/ ./ai_worker/
COPY maps_bridge/ ./maps_bridge/
COPY shared/ ./shared/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

USER appuser

# Cloud Run injects $PORT at runtime. Default 8080 matches Cloud Run convention.
CMD ["sh", "-c", "uvicorn api_gateway.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
