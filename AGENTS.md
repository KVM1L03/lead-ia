# LeadIA (LeadForge) — Agent Rules

Tool-agnostic technical facts for any AI coding agent (Claude Code, Codex,
Cursor, etc.) working in this repo. Product scope, UI tokens, and workflow
process live in `context/*.md` — read this file for the stack, boundaries,
and invariants that don't change per feature.

`frontend/AGENTS.md` has the Next.js 16 / React 19 / Tailwind v4 / Prisma 7
gotchas — read it before touching anything under `frontend/`.

---

## Stack (don't add new frameworks without explicit ask)

- **Backend:** Python 3.12, FastAPI, Pydantic v2 (`ConfigDict(strict=True)`), Temporal, DSPy, LangGraph
- **Frontend:** Next.js 16, React 19, Tailwind v4, Prisma 7, Server Actions
- **Data:** Postgres 16 (shared container, dedicated `app` schema), SQLite for SerpAPI cache
- **LLMs:** Anthropic (Haiku 4.5 for qualify, Sonnet 4.6 for email). OpenAI/Gemini behind a router for fallback only.
- **Observability:** Langfuse (self-hosted, port 3030)
- **Tool boundary:** MCP bridge for Google Places — agent never calls SerpAPI directly
- **Package mgmt:** `uv` for Python, `npm` for Node
- **Dev infra:** Docker Compose for the full stack, `Makefile` for shortcuts

**AI flow:** LangGraph is the per-lead state machine (`qualify → decide →
email`), wired on both the sync and Temporal hot paths. Temporal is the
outer batch orchestrator (search, fan-out, per-step retry, persistence,
replay). Each graph node maps to one Temporal activity for step-level retry
granularity. DSPy typed signatures handle all LLM extraction — no raw
prompt strings.

---

## Repo layout

```
api_gateway/     FastAPI HTTP entry, health, workflow triggers
maps_bridge/     MCP server — the ONLY process that calls SerpAPI
ai_worker/       Temporal worker + LangGraph per-lead graph (qualify→decide→email).
                 Temporal activities delegate to graph nodes for step-level retry.
frontend/        Next.js approval UI (Prisma, Server Actions)
shared/          Pydantic schemas consumed by all backend services
tests/           pytest (backend)
evals/           Promptfoo eval configs + results
docs/            model choices, deployment audit, roadmap, specs & plans
context/         spec-driven "constitution" — product, architecture, UI, code
                 standards, workflow rules — read before implementing
.github/         CI workflows, LLM review prompt, PR template
```

---

## Architecture invariants (NEVER violate)

These are checked by the automated LLM diff review
(`.github/prompts/llm-review-prompt.txt`) and must be listed in every PR
template checklist.

1. **Microservices only.** `api_gateway/`, `maps_bridge/`, `ai_worker/`, `frontend/` are separate processes. Never collapse them.
2. **Durable execution.** All business logic lives in Temporal workflows + activities. Workflows are 100% deterministic — no `datetime.now()`, no raw HTTP, no random.
3. **No raw prompt strings for extraction/qualification.** Use DSPy signatures. Email generation may use templated prompts but must be traced in Langfuse.
4. **Strict typing.** Pydantic v2 strict mode on Python. `strict: true` on TypeScript. Zero `Any`, zero `as unknown as X`.
5. **Zero trust.** MCP bridge is the only thing that talks to SerpAPI. The agent calls MCP tools, never the network directly.
6. **Schemas live in `shared/`.** Both backend and frontend (via codegen or hand-mirror) consume the same Pydantic contracts.

---

## Environment variables

Copy `.env.example` → `.env` on first clone (`make bootstrap` does this). Never commit `.env`.

| Variable | Purpose | Local default | CI |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Haiku/Sonnet calls, LLM review workflow | required for real LLM | GitHub secret (evals + LLM review) |
| `SERPAPI_API_KEY` | Google Places via maps_bridge | required for live maps | not used (mock) |
| `LANGFUSE_*` | Tracing | optional locally | not used |
| `TEMPORAL_ADDRESS` | Worker connection | `localhost:7233` | not used in unit CI |
| `DATABASE_URL` | App + cache DB | `sqlite:///./lead-forge.db` | not used in unit CI |
| `MAPS_PROVIDER` | Maps adapter | `mock` | `mock` (set in CI) |
| `QUALIFIER_MODEL` | Override qualifier LM (optional) | unset → uses `llm_router` default | — |
| `EMAIL_MODEL` | Override email LM (optional) | unset → uses `llm_router` default | — |

Use `MAPS_PROVIDER=mock` locally to skip SerpAPI calls (fixtures from
`maps_bridge` mock adapter). LLM mock is test-level via
`DummyLM`/`monkeypatch` — there is no `LLM_PROVIDER` env var in production
code.

---

## Anti-patterns (mistakes made before — don't repeat)

- ❌ Calling `dspy.configure(lm=...)` inside an activity (race condition under parallel execution). Use `dspy.context(lm=...)` per-call.
- ❌ `datetime.now()` inside a workflow (breaks replay). Use `workflow.now()`.
- ❌ Wrapping the whole LangGraph call inside one Temporal activity (no retry granularity). One activity per graph node.
- ❌ Adding a new ORM. Prisma + SQLAlchemy already split the load.
- ❌ Calling blocking/sync code (e.g. DSPy calls) directly inside a coroutine instead of `await asyncio.to_thread(...)`. See `context/code-standards.md` § Async / Concurrency.
- ❌ Re-explaining style rules here. The linter is the source of truth.
- ❌ Pushing directly to `main` or opening a 1000-line PR. CI will pass (maybe), but LLM review won't run and human review becomes painful.
