# Twelve-Factor App Audit

> Checked 2026-07-03 before Cloud Run deployment.
> Services audited: `api_gateway`, `ai_worker`, `maps_bridge`, `frontend`.

---

## Summary of violations found and fixed

| # | Violation | File | Fix |
|---|---|---|---|
| 7 | Port hardcoded to `8000` | `api_gateway/Dockerfile` | CMD now uses `${PORT:-8080}` |
| 6 | SQLite cache written to `./cache.db` (CWD) | `maps_bridge/config.py` | Default changed to `/tmp/cache.db` |

---

## Factor-by-factor verdict

### I. Codebase — ✅ Pass

Single git repository, multiple deployments via environment variables. No per-environment branches.

### II. Dependencies — ✅ Pass

All Python dependencies declared in `pyproject.toml` and pinned in `uv.lock`. Node dependencies in `frontend/package.json` + `package-lock.json`. No implicit system dependency assumptions; base images are explicit tags.

### III. Config — ✅ Pass (after fix)

All secrets and environment-specific values come from environment variables at runtime:

- `ANTHROPIC_API_KEY`, `SERPAPI_API_KEY` — injected by Cloud Run Secret Manager / docker-compose `.env`
- `TEMPORAL_ADDRESS`, `APP_DATABASE_URL`, `REDIS_URL` — backing service URLs
- `LANGFUSE_*` — observability endpoints and keys
- `MAPS_PROVIDER`, `MAPS_TRANSPORT` — behaviour flags
- `DEMO_MODE`, `DEMO_MAX_RUNS_PER_DAY` — demo abuse-protection tuning

No hardcoded URLs, IPs, or secrets found in source code. `pydantic-settings` (`BaseSettings`) is used for all settings classes — reads from environment with typed defaults.

**Fixed:** `maps_bridge/config.py` `CACHE_DB_PATH` default was `"./cache.db"` (relative to CWD, not an env var). Changed to `"/tmp/cache.db"` so it is explicitly in the ephemeral scratch area and still overridable via `CACHE_DB_PATH` env var.

### IV. Backing services — ✅ Pass

All backing services are attached via URL environment variables:

| Service | Env var |
|---|---|
| PostgreSQL | `APP_DATABASE_URL` (asyncpg), `PRISMA_DATABASE_URL` (Prisma) |
| Redis | `REDIS_URL` |
| Temporal | `TEMPORAL_ADDRESS` |
| Langfuse | `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` |
| SerpAPI | `SERPAPI_API_KEY` (URL is internal to `maps_bridge/providers/serpapi.py`) |

Swapping any backing service requires only an env var change — no code change.

### V. Build, release, run — ✅ Pass

Multi-stage Dockerfiles separate the build phase (uv dep install, bytecode compile) from the runtime image. No secrets are baked into images. The `--frozen` flag on `uv sync` ensures bit-for-bit reproducible builds from `uv.lock`.

Release = image tag. Run = `docker run` / Cloud Run revision deployment.

### VI. Processes — ✅ Pass (after fix)

All three backend services are stateless:

- `api_gateway` — no local state; DB writes go to PostgreSQL via SQLAlchemy
- `ai_worker` — no local state; Temporal persists workflow history
- `maps_bridge` — **was** writing SQLite cache to `./cache.db` (CWD). **Fixed** to `/tmp/cache.db`. The cache is ephemeral per-container-instance, which is acceptable (it's a performance cache, not durably required state). If cache persistence is needed in future, `CACHE_DB_PATH` can point to a Cloud Filestore mount.

No local file writes outside `/tmp` remain.

### VII. Port binding — ✅ Pass (after fix)

`api_gateway` exports its own HTTP server (uvicorn). **Was:** CMD hardcoded `--port 8000`. **Fixed:** CMD now uses `${PORT:-8080}` so Cloud Run can inject `$PORT` at runtime.

`ai_worker` and `maps_bridge` do not expose HTTP ports. `ai_worker` connects outward to Temporal; `maps_bridge` communicates over stdio (local) or is inlined (Cloud Run).

### VIII. Concurrency — ✅ Pass

Scale-out is achieved by running more container instances:

- `api_gateway` — stateless FastAPI, horizontal scaling via Cloud Run min/max instances
- `ai_worker` — Temporal workers compete on the `leads` task queue; adding instances increases throughput linearly
- `maps_bridge` — no dedicated instance in Cloud Run (inlined); scales with ai_worker

Temporal's activity concurrency is controlled internally by asyncio semaphores (default 10 parallel place-detail fetches per workflow). This is per-instance, so aggregate concurrency scales with instance count.

### IX. Disposability — ✅ Pass

- **Fast startup:** `--compile-bytecode` in the builder stage pre-compiles all `.py` files to `.pyc`, reducing cold-start import time. Cloud Run's minimum instance setting can keep warm instances for latency-sensitive paths.
- **Graceful shutdown:** `uvicorn` handles SIGTERM with in-flight request completion. Temporal workers drain pending activities before shutting down — the SDK listens for SIGTERM and stops polling the task queue.
- **No startup side effects:** All `Settings` objects are read at import time from environment; no network calls at startup.

### X. Dev/prod parity — ✅ Pass

- Same Docker images for local dev (`make up-build`) and Cloud Run — no separate dev Dockerfiles.
- `MAPS_PROVIDER=mock` (local) vs `serpapi` (prod), `MAPS_TRANSPORT=stdio` (local compose) vs `inline` (Cloud Run) — both are single env var toggles, not code branches.
- `LLM_PROVIDER=mock` for CI; `anthropic` for live — same code path.
- Langfuse self-hosted locally (port 3030) vs cloud-hosted in prod — same SDK, different `LANGFUSE_BASE_URL`.

### XI. Logs — ✅ Pass

- `PYTHONUNBUFFERED=1` is set in all Dockerfiles — ensures Python output goes directly to stdout/stderr without buffering.
- `uvicorn` writes access logs and error logs to stdout by default.
- `ai_worker` uses `logging` → stdout.
- No log files, no syslog routing.
- **Structured logging:** Langfuse captures LLM traces. For Cloud Run, stdout logs are automatically ingested by Cloud Logging and can be queried via Log Explorer.

### XII. Admin processes — ✅ Pass

One-off admin commands are run as separate processes, not inside the app container:

- `make db-push` — `prisma generate && prisma db push` for frontend schema migrations
- `make seed` — regenerate SerpAPI fixtures and mock DB
- `make eval` — promptfoo eval suite (run manually or via CI label)

No admin logic is embedded in the startup CMD of any service.

---

## maps_bridge transport decision

Cloud Run does not support stdio sidecars between containers in the same service revision. Options evaluated:

| Option | Pros | Cons | Decision |
|---|---|---|---|
| Standalone Cloud Run service | True process isolation | gRPC/HTTP overhead; sidecars need network auth | ❌ Over-engineered for a demo |
| Sidecar (Cloud Run multi-container preview) | Process boundary preserved | Experimental, limited regions, complex | ❌ Not GA |
| Inline in ai_worker | Simple, zero overhead, same image | Module boundary replaces process boundary | ✅ **Chosen** |

**Chosen:** `MAPS_TRANSPORT=inline` for Cloud Run.

**Zero-trust preserved:** SerpAPI imports (`maps_bridge/providers/serpapi.py`) never appear in `ai_worker/` code. The `activities.py` lazy-imports `maps_bridge.provider_factory.get_provider` — the module boundary enforces the same isolation rule as the process boundary did. Business logic in workflows/activities cannot reach SerpAPI directly.

**Local dev unchanged:** `MAPS_TRANSPORT=stdio` (default in `.env.example` and `docker-compose.yml`) keeps the original subprocess/stdio MCP path active. The `maps-bridge` Docker Compose service continues to exist for local stack completeness (the subprocess spawned by ai_worker uses the same `maps_bridge.server` module).
