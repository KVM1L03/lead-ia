# Architecture Context

## Stack

Minimal reference table — full stack detail, invariants, and anti-patterns
live in root `AGENTS.md` (source of truth, don't duplicate further here).

| Layer | Technology | Role |
|---|---|---|
| Backend | Python 3.12, FastAPI | HTTP entry, health, workflow triggers |
| Orchestration | Temporal | Durable batch orchestrator — search, fan-out, per-step retry, persistence |
| Agent state machine | LangGraph | Per-lead graph: `qualify → decide → email` |
| LLM extraction | DSPy | Typed signatures for qualify/email — no raw prompt strings |
| Frontend | Next.js 16, React 19, Tailwind v4, Prisma 7 | Approval UI |
| Data | Postgres 16 (`app` schema) + SQLite | App state + SerpAPI/Places cache |
| LLMs | Anthropic Haiku 4.5 (qualify), Sonnet 4.6 (email) | Via `llm_router`; OpenAI/Gemini fallback only |
| Observability | Langfuse (self-hosted, port 3030) | Tracing across both execution paths |
| Tool boundary | MCP bridge (`maps_bridge`) | Only process that calls SerpAPI/Google Places |

## System Boundaries

- `api_gateway/` — FastAPI HTTP entry, health checks, workflow triggers
- `maps_bridge/` — MCP server; the only process that imports `httpx` or
  calls SerpAPI/Google Places
- `ai_worker/` — Temporal worker + LangGraph per-lead graph (`qualify →
  decide → email`); each Temporal activity delegates to one graph node for
  step-level retry granularity
- `frontend/` — Next.js approval UI (Prisma, Server Actions)
- `shared/` — Pydantic schemas consumed by all backend services

## Two Orchestration Paths

The business flow is one: search → enrich → qualify → email. The leaf logic
runs once, in `qualify_node` and `email_node` (`agent_graph.py`). The
orchestration shell is two, by necessity:

| Path | Orchestrator | Trigger / constraints |
|---|---|---|
| `EXECUTION_MODE=sync` | `run_pipeline()` (`pipeline.py`) — direct `asyncio.gather`, no Temporal persistence | Cloud Run public demo; capped at 25 leads to stay under the 60s request timeout |
| `EXECUTION_MODE=temporal` | `LeadGenerationWorkflow.run()` (`workflows.py`) — 5 activities, explicit timeout + typed retry policy per step | Local full stack via Docker Compose |

Temporal workflows must stay 100% deterministic — no direct HTTP, LLM, or
MCP calls; every external operation goes through an activity. The sync path
has no such constraint. A shared `orchestrate(steps, executor)` abstraction
across both paths was considered and rejected: it would be a leaky
abstraction over two genuinely different execution models, harder to read
and defend than explicit duplication. See README "Engineering decisions —
Why two orchestration paths" for the full rationale.

## Storage Model

- **Postgres 16** (`app` schema, shared container): lead runs and approval
  state — written via Prisma (frontend) and SQLAlchemy (backend)
- **SQLite** (`maps_bridge`): SerpAPI/Google Places response cache, avoids
  redundant paid API calls on repeated searches
- No blob/file storage in this project — CSV export is generated on demand,
  not persisted server-side

## Auth and Access Model

- **No authentication.** This is a local-first, BYOK, single-user demo — not
  a multi-tenant SaaS (see `project-overview.md` — Out of Scope).
- API keys (Anthropic, SerpAPI, etc.) are supplied by whoever runs the tool,
  via `.env` — never committed, never per-user.
- Approval Server Actions are unauthenticated by design: there is no
  multi-user state to protect.

## Invariants

The six non-negotiable architecture invariants (microservices only, durable
execution in Temporal, no raw prompt strings for extraction/qualification,
strict typing, MCP zero-trust boundary, schemas in `shared/`) are defined
once in root `AGENTS.md` §Invariants and enforced by the automated LLM diff
review — see there, not here, for the authoritative list.
