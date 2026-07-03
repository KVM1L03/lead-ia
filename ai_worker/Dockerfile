# ── Stage 1: build venv ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --compile-bytecode

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN useradd --system --no-create-home --shell /bin/false appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

# maps_bridge/ is bundled so both transport modes work from this image:
#   MAPS_TRANSPORT=stdio  → ai_worker spawns "python -m maps_bridge.server" as subprocess
#   MAPS_TRANSPORT=inline → ai_worker imports maps_bridge.provider_factory directly
COPY ai_worker/ ./ai_worker/
COPY maps_bridge/ ./maps_bridge/
COPY shared/ ./shared/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV MAPS_TRANSPORT=stdio

USER appuser

CMD ["python", "-m", "ai_worker.worker"]
