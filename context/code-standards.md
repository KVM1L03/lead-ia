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
