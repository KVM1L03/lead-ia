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
- **LLMs:** Anthropic (Haiku 4.5 for qualify, Sonnet 4.6 for email). OpenAI/Gemini behind a router for fallback only.
- **Observability:** Langfuse (self-hosted, port 3030)
- **Tool boundary:** MCP bridge for Google Places — agent never calls SerpAPI directly
- **Package mgmt:** `uv` for Python, `npm` for Node
- **Dev infra:** Docker Compose for the full stack, `Makefile` for shortcuts

**AI flow (post-PR1):** LangGraph is the per-lead state machine (`qualify → decide → email`), wired on both the sync and Temporal hot paths. Temporal is the outer batch orchestrator (search, fan-out, per-step retry, persistence, replay). Each graph node maps to one Temporal activity for step-level retry granularity. DSPy typed signatures handle all LLM extraction — no raw prompt strings.

When editing the frontend, also read `frontend/CLAUDE.md` and `frontend/AGENTS.md` (Next.js 16 breaking changes).

---

## 3. Repo layout

```
api_gateway/     FastAPI HTTP entry, health, workflow triggers
maps_bridge/     MCP server — the ONLY process that calls SerpAPI
ai_worker/       Temporal worker + LangGraph per-lead graph (qualify→decide→email).
                 Temporal activities delegate to graph nodes for step-level retry.
frontend/        Next.js approval UI (Prisma, Server Actions)
shared/          Pydantic schemas consumed by all backend services
tests/           pytest (backend)
evals/           Promptfoo eval configs + results
docs/            model choices, deployment audit, roadmap
.github/         CI workflows, LLM review prompt, PR template
```

---

## 4. Architecture invariants (NEVER violate)

These are checked by the automated LLM diff review (`.github/prompts/llm-review-prompt.txt`) and must be listed in every PR template checklist.

1. **Microservices only.** `api_gateway/`, `maps_bridge/`, `ai_worker/`, `frontend/` are separate processes. Never collapse them.
2. **Durable execution.** All business logic lives in Temporal workflows + activities. Workflows are 100% deterministic — no `datetime.now()`, no raw HTTP, no random.
3. **No raw prompt strings for extraction/qualification.** Use DSPy signatures. Email generation may use templated prompts but must be traced in Langfuse.
4. **Strict typing.** Pydantic v2 strict mode on Python. `strict: true` on TypeScript. Zero `Any`, zero `as unknown as X`.
5. **Zero trust.** MCP bridge is the only thing that talks to SerpAPI. The agent calls MCP tools, never the network directly.
6. **Schemas live in `shared/`.** Both backend and frontend (via codegen or hand-mirror) consume the same Pydantic contracts.

---

## 5. Commands (source of truth — don't re-state style rules elsewhere)

This section is canonical. If a `Makefile` target is missing, implement it to match — don't document a different command set elsewhere.

```bash
make bootstrap   # fresh clone: install deps + copy .env.example → .env
make install     # uv sync + npm ci
make up-build    # docker compose up --build -d
make up          # docker compose up -d (no rebuild)
make down        # stop, volumes preserved
make logs        # tail compose logs
make frontend    # next dev only (cd frontend && npm run dev)
make db-push     # prisma generate + db push
make format      # ruff format (auto-fix)
make lint        # ruff check + ruff format --check + mypy + eslint
make test        # pytest + vitest
make eval        # promptfoo eval suite (cost ~$0.10; uses real API)
```

**CI parity** — GitHub Actions runs the same checks as `make lint` + `make test`, plus `prisma generate`:

| Check | CI job | Local |
|---|---|---|
| ruff check + format --check | `python` | `make lint` |
| mypy (`api_gateway ai_worker maps_bridge shared`) | `python` | `make lint` |
| pytest (`MAPS_PROVIDER=mock`) | `python` | `make test` |
| eslint + tsc + vitest | `frontend` | `make lint` + `make test` |
| prisma generate | `frontend` | `make db-push` |
| promptfoo evals | `evals` (label only) | `make eval` |

Lint is enforced in CI. Don't lecture me about style — run `make lint` and let the linter speak.

---

## 6. Environment variables

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

Use `MAPS_PROVIDER=mock` locally to skip SerpAPI calls (fixtures from `maps_bridge` mock adapter). LLM mock is test-level via `DummyLM`/`monkeypatch` — there is no `LLM_PROVIDER` env var in production code.

---

## 7. Testing

- **Backend unit/integration:** `tests/` — run with `uv run pytest` or `make test`. CI sets `MAPS_PROVIDER=mock` — no real Maps API calls. LLM calls are mocked at test level via `DummyLM` / `monkeypatch` (no `LLM_PROVIDER` env var; that var is not read by production code).
- **Frontend unit:** `frontend/` — vitest, run via `make test` or `cd frontend && npm test -- --run`.
- **New logic needs tests.** If you add a function with branching, side effects, or parsing, add a pytest or vitest case. CI pytest covers this; LLM review does not check test coverage.
- **Evals (optional, costs money):** `make eval` locally, or add label `run-evals` on a PR to trigger the `evals` CI job. Only run when changing DSPy signatures or prompt behavior — not on every PR.
- **Manual smoke:** describe what you clicked/ran in the PR template. Required for UI or end-to-end flow changes.

---

## 8. Workflow rules (how to behave)

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
- **PR size:** aim for ≤200–400 LOC per PR. Hard limit: automated LLM review skips backend diffs >400 lines — split before you hit that ceiling.
- **Run `make lint` and `make test` before saying "done".** "Done" = lint clean + tests green + the new behavior demonstrated.
- **Fill the PR template** (`.github/pull_request_template.md`): one-sentence summary, invariants checked, verification checklist.
- **Never commit secrets.** `.env` is git-ignored; use `.env.example` for shape.
- **Use the MCP bridge** for any SerpAPI call. If you find yourself importing `requests` in the worker, stop — you're about to violate invariant #5.

---

## 9. Git & CI pipeline

Every change merges to `main` through a pull request. Nothing runs on push until a PR is opened (except post-merge CI on `main`).

### Developer flow

```bash
git checkout main && git pull
git checkout -b feat/my-change
# ... edit ...
make lint && make test
git add -A && git commit -m "describe the why"
git push -u origin feat/my-change
gh pr create --base main   # or via GitHub UI
```

### What runs automatically on PR → `main`

| Automation | Trigger | What it does |
|---|---|---|
| **CI `python`** | PR open / new commits / reopen | ruff, mypy, pytest (mock providers) |
| **CI `frontend`** | same | eslint, tsc, vitest, prisma generate |
| **LLM diff review** | same | Claude Haiku reviews the diff, posts a comment on the PR |
| **CI `evals`** | same, only if PR has label `run-evals` | promptfoo evals (~$0.10, real Anthropic API) |

New commits on the PR re-trigger CI (previous runs are cancelled). LLM review runs only on PR open/reopen, not on every push.

### Merge requirements

Configured in **GitHub → Settings → Branches → main** (cannot be stored in the repo; apply manually):

| Setting | Value |
|---|---|
| Require a pull request before merging | ✅ |
| Required approving reviews | 1 |
| Required status checks | `python`, `frontend` |
| Require branch up to date | ✅ |
| Allow force pushes | ❌ |

`evals` and LLM review do **not** block merge. LLM review is a fast first pass, not a substitute for human review.

### LLM review behavior

- Runs on PR **open/reopen** only (not every push). Backend paths only (`ai_worker/`, `api_gateway/`, `maps_bridge/`, `shared/`); test files excluded from diff.
- Reviews **diff only** (not full files), using `.github/prompts/llm-review-prompt.txt`.
- Skips lockfiles, migrations, snapshots, generated code.
- Posts a comment with verdict: `APPROVE | NEEDS CHANGES | BLOCKING ISSUE`.
- If verdict is `BLOCKING ISSUE` or findings look real: fix before merge, don't ignore.
- If backend diff >400 lines: review is skipped with a comment — split the PR.

### Optional: run evals on a PR

Add label `run-evals` **before** opening the PR, or push a new commit after adding the label (label alone does not re-trigger CI). Requires `ANTHROPIC_API_KEY` in GitHub repo secrets.

---

## 10. When you're confused

- Architecture overview → README §Architecture and §Engineering decisions
- Why a model was picked, eval backlog, migration plan → `docs/model-choices.md`
- Branch protection / merge gates → §9 above ("Merge requirements" table)
- Deployment + twelve-factor audit → `docs/twelve-factor-audit.md`
- Project roadmap → `docs/roadmap.md`
- Eval results → `evals/results/`
- How to add a new tool to the MCP bridge → `maps_bridge/README.md`
- Frontend-specific rules → `frontend/CLAUDE.md`, `frontend/AGENTS.md`
- What the LLM reviewer checks → `.github/prompts/llm-review-prompt.txt`

If those don't answer it, ask me before guessing. Don't invent a function, library, or env var.

---

## 11. Anti-patterns (I've made these mistakes — don't repeat)

- ❌ Calling `dspy.configure(lm=...)` inside an activity (race condition under parallel execution). Use `dspy.context(lm=...)` per-call.
- ❌ `datetime.now()` inside a workflow (breaks replay). Use `workflow.now()`.
- ❌ Wrapping the whole LangGraph call inside one Temporal activity (no retry granularity). One activity per graph node.
- ❌ Adding a new ORM. Prisma + SQLAlchemy already split the load.
- ❌ Re-explaining style rules here. The linter is the source of truth.
- ❌ Pushing directly to `main` or opening a 1000-line PR. CI will pass (maybe), but LLM review won't run and human review becomes painful.
