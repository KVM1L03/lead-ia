# LeadForge — Claude Code project memory

> Production-grade, AI-powered lead generation pipeline.
> Prompt → Google Places (via SerpAPI) → cheap-model qualifier → email draft → human approval.

---

## 1. What this project is (and is not)

**IS:** Portfolio-grade demo. Local-first. BYOK. Showcases durable workflows (Temporal), LLM observability (Langfuse), evaluations (Promptfoo + DSPy), zero-trust tool access (MCP).

**IS NOT:** Multi-tenant SaaS. No auth, no payments, no email-sending, no warming, no CRM. Resist scope creep — if a feature isn't on the milestone board, it doesn't exist.

---

## 2. Stack (don't add new frameworks without explicit ask)

- **Backend:** Python 3.12, FastAPI, Pydantic v2 (`ConfigDict(strict=True)`), Temporal, DSPy, LangGraph
- **Frontend:** Next.js 16, React 19, Tailwind v4, Prisma 7, Server Actions
- **Data:** Postgres 16 (shared container, dedicated `app` schema), SQLite for SerpAPI cache
- **LLMs:** Anthropic (Haiku 4.5 for filter, Sonnet 4.6 for emails). OpenAI/Gemini behind a router for fallback only.
- **Observability:** Langfuse (self-hosted, port 3030)
- **Tool boundary:** MCP bridge for Google Places — agent never calls SerpAPI directly
- **Package mgmt:** `uv` for Python, `npm` for Node
- **Dev infra:** Docker Compose for the full stack, `Makefile` for shortcuts

---

## 3. Architecture invariants (NEVER violate)

1. **Microservices only.** `api_gateway/`, `maps_bridge/`, `ai_worker/`, `frontend/` are separate processes. Never collapse them.
2. **Durable execution.** All business logic lives in Temporal workflows + activities. Workflows are 100% deterministic — no `datetime.now()`, no raw HTTP, no random.
3. **No raw prompt strings for extraction/qualification.** Use DSPy signatures. Email generation may use templated prompts but must be traced in Langfuse.
4. **Strict typing.** Pydantic v2 strict mode on Python. `strict: true` on TypeScript. Zero `Any`, zero `as unknown as X`.
5. **Zero trust.** MCP bridge is the only thing that talks to SerpAPI. The agent calls MCP tools, never the network directly.
6. **Schemas live in `shared/`.** Both backend and frontend (via codegen or hand-mirror) consume the same Pydantic contracts.

---

## 4. Commands (source of truth — don't re-state style rules elsewhere)

```bash
make bootstrap   # fresh clone: install + seed + up-build + frontend dev
make dev         # daily use
make install     # uv sync + npm ci
make seed        # regenerate SerpAPI fixtures + mock DB
make up-build    # docker compose up --build -d
make down        # stop, volumes preserved
make logs        # tail compose logs
make frontend    # next dev only
make db-push     # prisma generate + db push
make lint        # ruff + mypy + eslint + tsc
make test        # pytest + vitest
make eval        # promptfoo eval suite (cost ~$0.10)
```

Lint is enforced in CI. Don't lecture me about style — run `make lint` and let the linter speak.

---

## 5. Workflow rules (how to behave)

### Git: branch → PR → review (default for real work)

**Before writing code**, decide if the task needs a branch. If yes, create it **first** — never commit on `main`.

| Trigger | Branch? | Prefix | Example |
|---|---|---|---|
| New feature, endpoint, UI screen, workflow, tool | ✅ | `feat/` | `feat/maps-mcp-search` |
| Bug fix | ✅ | `fix/` | `fix/temporal-replay-date` |
| Refactor (behavior unchanged) | ✅ | `refactor/` | `refactor/extract-qualifier` |
| CI, Docker, Makefile, deps | ✅ | `chore/` or `ci/` | `ci/add-mypy-job` |
| Docs-only typo, answer a question, read-only exploration | ❌ | — | stay on current branch or don't commit |
| User explicitly says "commit straight to main" | ❌ | — | only then skip branching |

**Branch names:** lowercase kebab-case, max ~5 words, no issue numbers unless user asks.

**End-of-task checklist** (required when you created a branch):

1. `make lint && make test` — both green
2. Commit with a clear message (what + why, not file list)
3. `git push -u origin <branch>`
4. Open PR to `main` via `gh pr create` — template in `.github/pull_request_template.md` fills automatically
5. Report PR URL. **Do not merge** — wait for CI (`python`, `frontend`) + human approval
6. LLM review (`llm-review.yml`) is advisory only; human review is required (`docs/branch-protection.md`)

**Never:** push to `main`, force-push, merge your own PR without explicit user ask, open 600 LOC PRs when 3×200 LOC would work.

### General

- **Plan before writing code** for any change touching >1 file. Use plan mode (`Shift+Tab` twice in Claude Code).
- **Diffs stay small.** Prefer 3 PRs of 200 LOC over 1 PR of 600 LOC.
- **Run `make lint` and `make test` before saying "done"**. "Done" = lint clean + tests green + the new behavior demonstrated.
- **Never commit secrets.** `.env` is git-ignored; use `.env.example` for shape.
- **Use the MCP bridge** for any SerpAPI call. If you find yourself importing `requests` in the worker, stop — you're about to violate invariant #5.

---

## 6. When you're confused

- Architecture questions → `docs/architecture.md`
- Why a model was picked → `docs/model-choices.md`
- Eval results → `evals/results/`
- How to add a new tool to the MCP bridge → `maps_bridge/README.md`

If those don't answer it, ask me before guessing. Don't invent a function, library, or env var.

---

## 7. Anti-patterns (I've made these mistakes — don't repeat)

- ❌ Calling `dspy.configure(lm=...)` inside an activity (race condition under parallel execution). Use `dspy.context(lm=...)` per-call.
- ❌ `datetime.now()` inside a workflow (breaks replay). Use `workflow.now()`.
- ❌ Wrapping the whole LangGraph call inside one Temporal activity (no retry granularity). One activity per graph node.
- ❌ Adding a new ORM. Prisma + SQLAlchemy already split the load.
- ❌ Re-explaining style rules here. The linter is the source of truth.