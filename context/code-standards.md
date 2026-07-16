# Code Standards

Cross-cutting invariants and anti-patterns are defined once in root
`AGENTS.md` and `frontend/AGENTS.md` — this file adds what those don't
already cover, and points to them rather than repeating them.

## General

- Microservices only — keep `api_gateway/`, `maps_bridge/`, `ai_worker/`,
  `frontend/` as separate processes (root `AGENTS.md` invariant #1)
- Fix root causes, do not layer workarounds — see root `AGENTS.md`
  anti-patterns
- Do not mix unrelated concerns in one activity or component — one Temporal
  activity per LangGraph node, not one activity wrapping the whole graph

## Python (backend)

- Pydantic v2 with `ConfigDict(strict=True)` everywhere — zero implicit
  coercion
- No raw prompt strings for extraction/qualification — DSPy typed
  signatures only (`dspy.Predict` classes with field-level descriptions).
  Email generation may use templated prompts but must be traced in Langfuse.
- Call `dspy.context(lm=...)` per-call inside activities, never
  `dspy.configure(lm=...)` — the latter races under parallel execution
- Temporal workflows are 100% deterministic: no `datetime.now()` (use
  `workflow.now()`), no raw HTTP, no `random`
- ruff + mypy are the source of truth for style — `make lint` is the only
  place style rules are enforced; don't hand-enforce beyond what it checks

## Async / Concurrency (Python)

The event loop is shared by every in-flight request/activity — a single
blocking call inside a coroutine stalls all of them, not just the caller.
This bit the project once (`fix(pipeline): avoid blocking and reuse MCP
sessions`, `ai_worker/pipeline.py`) — these rules exist to stop it recurring.

- **Never call a blocking/sync function directly inside an `async def`.**
  DSPy calls (`qualify_node`, `email_node`, `translate_prompt`,
  `process_one_lead`) are synchronous under the hood — offload them with
  `await asyncio.to_thread(fn, ...)`, the pattern already used in
  `activities.py`, `pipeline.py`, and `api_gateway/routes/leads.py`. Never
  reach for a raw `ThreadPoolExecutor`/`run_in_executor` unless
  `asyncio.to_thread` genuinely doesn't fit.
- **`asyncio.to_thread` propagates contextvars** — this is why Langfuse/OTel
  spans created inside the thread nest correctly under the parent activity
  span (see `observability.py`). Don't work around it by manually passing
  context; let propagation do it.
- **Reuse expensive resources instead of recreating them per call.** Spawning
  a new stdio MCP subprocess (or DB connection, or HTTP client) per request
  is the mistake `MapsMcpSession` was introduced to fix — one session per
  pipeline run, entered once via `AsyncExitStack`, not per tool call.
- **Bound fan-out concurrency with `asyncio.Semaphore`.** Per-lead
  enrich/qualify/email work runs via `asyncio.gather`, gated by a semaphore
  sized from `max_concurrency` — never fan out unbounded concurrent MCP or
  LLM calls.
- **Don't let one failed task cancel the whole batch.** `asyncio.gather`
  cancels sibling tasks on the first unhandled exception; this project wraps
  each per-item coroutine in its own `try/except` and returns a `Lead` with
  an `error` field instead, so one bad place/lead doesn't sink the run. Keep
  following that convention rather than relying on `return_exceptions=True`
  and post-hoc filtering.
- **Never `time.sleep()` in async code** — it blocks the whole event loop.
  Use `await asyncio.sleep(...)`.
- **Never call `asyncio.run()` from inside code that's already running in an
  event loop** (e.g. inside a FastAPI route or Temporal activity) — it will
  raise. If you need to bridge sync code that itself needs an event loop,
  that's a sign the call belongs behind `asyncio.to_thread`, not a nested
  `asyncio.run()`.
- **This rule does not apply inside Temporal workflow code.** Workflows run
  single-threaded and must stay deterministic and replay-safe — no
  `asyncio.to_thread`, no real threads, no raw `asyncio.Semaphore` (use the
  workflow-safe primitives Temporal provides). `asyncio.to_thread` is an
  **activity-only** pattern; see `AGENTS.md` invariant #2 ("Durable
  execution") for the workflow-side rules.

## TypeScript (frontend)

- `strict: true`, zero `any`, zero `as unknown as X`
- Default to Server Components; add `"use client"` only at the interactive
  leaf
- Full Next.js 16 / React 19 / Tailwind v4 / Prisma 7 rule set:
  `frontend/AGENTS.md`

## Styling

- Use the CSS custom property tokens defined in `ui-context.md` /
  `frontend/app/globals.css` — no hardcoded hex values
- Follow the border-radius scale defined in `ui-context.md`

## Data and Storage

- Metadata (leads, approval state) belongs in Postgres — via Prisma
  (frontend) or SQLAlchemy (backend)
- SerpAPI/Google Places responses cache in SQLite (`maps_bridge`) — do not
  re-fetch on every run
- No blob storage in this project — CSV export is generated on demand, not
  persisted server-side

## File Organization

- `api_gateway/` — FastAPI HTTP entry, health, workflow triggers
- `maps_bridge/` — MCP server, the only SerpAPI/Google Places caller
- `ai_worker/` — Temporal worker + LangGraph per-lead graph
- `frontend/` — Next.js approval UI
- `shared/` — Pydantic schemas consumed by all backend services
- `tests/` — pytest (backend)
