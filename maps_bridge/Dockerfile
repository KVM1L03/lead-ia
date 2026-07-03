# Local dev only — not deployed to Cloud Run.
# In Cloud Run, maps_bridge runs inline inside ai_worker (MAPS_TRANSPORT=inline).
#
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
COPY maps_bridge/ ./maps_bridge/
COPY shared/ ./shared/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

USER appuser

CMD ["python", "-m", "maps_bridge.server"]
