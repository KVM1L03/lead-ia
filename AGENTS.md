# LeadIA (LeadForge) — Agent Rules

> Production-grade, AI-powered lead generation pipeline.
> Prompt → Google Places (via SerpAPI) → cheap-model qualifier → email draft → human approval.

Canonical instructions for any AI coding agent (Claude Code, Codex, Cursor,
etc.) working in this repo. This is the single source of truth — `CLAUDE.md`
is a one-line pointer to this file; put nothing else there.

`frontend/AGENTS.md` layers Next.js 16 / React 19 / Tailwind v4 / Prisma 7
gotchas on top of everything here — read it before touching anything under
`frontend/`.

---

## 1. What this project is (and is not)

**IS:** Portfolio-grade demo. Local-first. BYOK. Showcases durable workflows
(Temporal), LLM observability (Langfuse), evaluations (Promptfoo + DSPy),
zero-trust tool access (MCP).

**IS NOT:** Multi-tenant SaaS. No auth, no payments, no email-sending, no
warming, no CRM. Resist scope creep — if a feature isn't on the milestone
board (`docs/roadmap.md`), it doesn't exist.

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

**AI flow:** LangGraph is the per-lead state machine (`qualify → decide →
email`), wired on both the sync and Temporal hot paths. Temporal is the
outer batch orchestrator (search, fan-out, per-step retry, persistence,
replay). Each graph node maps to one Temporal activity for step-level retry
granularity. DSPy typed signatures handle all LLM extraction — no raw
prompt strings.

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
docs/            model choices, deployment audit, roadmap, ADRs, specs & plans
context/         spec-driven "constitution" — product, architecture, UI, code
                 standards, workflow rules — read before implementing
.github/         CI workflows, PR template
```

---

## 4. Architecture invariants (NEVER violate)

There is no automated check for these (see [ADR 0007](docs/adr/0007-remove-automated-llm-diff-review.md)
for why) — they must be listed in every PR template checklist and verified
by a human reviewer.

1. **Microservices only.** `api_gateway/`, `maps_bridge/`, `ai_worker/`, `frontend/` are separate processes. Never collapse them.
2. **Durable execution.** All business logic lives in Temporal workflows + activities. Workflows are 100% deterministic — no `datetime.now()`, no raw HTTP, no random.
3. **No raw prompt strings for extraction, or for anything an LLM decides.** Use DSPy signatures. Email generation may use templated prompts but must be traced in Langfuse. Exception: the qualifier's `is_qualified` yes/no call is a TypeSafe Jev noul (`ai_worker/jev_qualifier.py`, pinned `jev-1.13.0`), not a DSPy signature — see [ADR 0006](docs/adr/0006-jev-for-qualification-decision.md). DSPy still owns the qualifier's `reasoning` text and every other LLM task.
4. **Strict typing.** Pydantic v2 strict mode on Python. `strict: true` on TypeScript. Zero `Any`, zero `as unknown as X`.
5. **Zero trust.** MCP bridge is the only thing that talks to SerpAPI. The agent calls MCP tools, never the network directly.
6. **Schemas live in `shared/`.** Both backend and frontend (via codegen or hand-mirror) consume the same Pydantic contracts.

---

## 5. Environment variables

Copy `.env.example` → `.env` on first clone (`make bootstrap` does this). Never commit `.env`.

| Variable | Purpose | Local default | CI |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Haiku/Sonnet calls | required for real LLM | GitHub secret (evals) |
| `SERPAPI_API_KEY` | Google Places via maps_bridge | required for live maps | not used (mock) |
| `LANGFUSE_*` | Tracing | optional locally | not used |
| `TEMPORAL_ADDRESS` | Worker connection | `localhost:7233` | not used in unit CI |
| `DATABASE_URL` | App + cache DB | `sqlite:///./lead-forge.db` | not used in unit CI |
| `MAPS_PROVIDER` | Maps adapter | `mock` | `mock` (set in CI) |
| `QUALIFIER_MODEL` | Override qualifier LM (optional) | unset → uses `llm_router` default | — |
| `EMAIL_MODEL` | Override email LM (optional) | unset → uses `llm_router` default | — |
| `TYPESAFE_API_KEY` | Jev qualifier decision (`score_noul`, pinned `jev-1.13.0`) + `make eval-jev` | required for `qualify_lead()` | not used (unit LLM calls mocked) |

Use `MAPS_PROVIDER=mock` locally to skip SerpAPI calls (fixtures from
`maps_bridge` mock adapter). LLM mock is test-level via
`DummyLM`/`monkeypatch` — there is no `LLM_PROVIDER` env var in production
code.

---

## 6. Development workflow (ticket → branch → spec → plan → code)

This project builds via a spec-driven cycle using the **`mattpocock-skills`**
plugin (https://github.com/mattpocock/skills). Do **not** use the
`superpowers` plugin or any `superpowers:*` skill — it is not installed in
this environment and must not be referenced anywhere in this repo.

**0. New ticket → new branch, immediately.** The moment work starts on a
ticket, ask, or ambiguous ask, create its branch first — before reading
context files, before invoking any skill, before writing a line of code.
Never let two tickets share a branch, and never accumulate unrelated work on
one branch while "just quickly" fixing something else. See §9 for naming.

For anything touching more than one file, once the branch exists:

1. Read `context/project-overview.md` → `architecture.md` → `ui-context.md`
   (frontend changes only) → `code-standards.md` → `ai-workflow-rules.md` →
   `progress-tracker.md`, in that order. These are the project's
   "constitution" — product scope, architecture narrative, UI tokens, code
   standards, and workflow rules that don't change per feature. Do not
   infer or invent behavior from scratch — ground implementation in these
   files, `docs/roadmap.md`, and `docs/model-choices.md`.
2. Explore and pin down the design before writing code:
   - `mattpocock-skills:domain-modeling` to pin terminology, record an
     architectural decision, or write the design doc for the change (lands
     in `docs/specs/YYYY-MM-DD-<topic>-design.md`).
   - `mattpocock-skills:prototype` to sanity-check a state model or UI
     direction with a throwaway prototype before committing to it.
   - `mattpocock-skills:codebase-design` when the change adds or reshapes a
     module boundary/interface.
   - `mattpocock-skills:grilling` to stress-test a non-obvious plan or
     decision before it's locked in.
   - `mattpocock-skills:research` when the change depends on facts about an
     external API, library, or doc that should be verified against primary
     sources rather than assumed.
3. Once the approach is settled, write (or update) the implementation plan
   in `docs/plans/YYYY-MM-DD-<topic>.md`, then execute it using
   `mattpocock-skills:tdd` (red-green-refactor, tests before implementation).
4. Hit a bug or unexpected failure mid-implementation → use
   `mattpocock-skills:diagnosing-bugs` rather than guessing at a fix.
5. Before opening the PR, run `mattpocock-skills:code-review` (Standards +
   Spec axes) against the diff and address what it finds.
6. Update `context/progress-tracker.md` after each meaningful change — it's
   a rolling index into `docs/plans/`, not a duplicate log.

If a merge/rebase lands in conflict, use
`mattpocock-skills:resolving-merge-conflicts` rather than resolving by hand.

Full scoping rules, protected files, and "when to split work" live in
`context/ai-workflow-rules.md` — don't restate them here.

---

## 7. Commands (source of truth — don't re-state style rules elsewhere)

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

## 8. Testing

- **Backend unit/integration:** `tests/` — run with `uv run pytest` or `make test`. CI sets `MAPS_PROVIDER=mock` — no real Maps API calls. LLM calls are mocked at test level via `DummyLM` / `monkeypatch` (no `LLM_PROVIDER` env var; that var is not read by production code).
- **Frontend unit:** `frontend/` — vitest, run via `make test` or `cd frontend && npm test -- --run`.
- **New logic needs tests.** If you add a function with branching, side effects, or parsing, add a pytest or vitest case (see `mattpocock-skills:tdd`). CI pytest covers this; there's no automated review pass to catch missing coverage, so `mattpocock-skills:code-review` and human review are what enforce it.
- **Evals (optional, costs money):** `make eval` locally, or add label `run-evals` on a PR to trigger the `evals` CI job. Only run when changing DSPy signatures or prompt behavior — not on every PR.
- **Manual smoke:** describe what you clicked/ran in the PR template. Required for UI or end-to-end flow changes.

---

## 9. Git workflow: branch → PR → review (default for real work)

**Before writing code**, create the ticket's branch first — never commit on
`main` (see §6 step 0).

| Trigger | Branch? | Prefix | Example |
|---|---|---|---|
| New feature, endpoint, UI screen, workflow, tool | ✅ | `feat/` | `feat/maps-mcp-search` |
| Bug fix | ✅ | `fix/` | `fix/temporal-replay-date` |
| Refactor (behavior unchanged) | ✅ | `refactor/` | `refactor/extract-qualifier` |
| CI, Docker, Makefile, deps, process/docs restructuring | ✅ | `chore/` or `ci/` | `ci/add-mypy-job` |
| Docs-only typo, answer a question, read-only exploration | ❌ | — | stay on current branch or don't commit |
| User explicitly says "commit straight to main" | ❌ | — | only then skip branching |

**Branch names:** lowercase kebab-case, max ~5 words, no issue numbers unless user asks.

**End-of-task checklist** (required when you created a branch):

1. `make lint && make test` — both green
2. Commit with a clear message (what + why, not file list)
3. `git push -u origin <branch>`
4. Open PR to `main` via `gh pr create` — template in `.github/pull_request_template.md` fills automatically
5. Report PR URL. **Do not merge** — wait for CI (`python`, `frontend`) + human approval
6. Human review is required before merge — there is no automated review pass (§10 "Merge requirements", [ADR 0007](docs/adr/0007-remove-automated-llm-diff-review.md))

**Never:** push to `main`, force-push, merge your own PR without explicit user ask, open 600 LOC PRs when 3×200 LOC would work.

### General

- **Plan before writing code** for any change touching >1 file — see §6.
- **PR size:** aim for ≤200–400 LOC per PR — keeps human review fast and thorough; split larger changes into multiple PRs.
- **Run `make lint` and `make test` before saying "done".** "Done" = lint clean + tests green + the new behavior demonstrated.
- **Fill the PR template** (`.github/pull_request_template.md`): one-sentence summary, invariants checked, verification checklist.
- **Never commit secrets.** `.env` is git-ignored; use `.env.example` for shape.
- **User-facing change → one line in `CHANGELOG.md` under `## [Unreleased]`** (Added / Changed / Fixed / Removed), linking the PR. Internal refactors and doc typos don't need an entry. Cutting a release = rename the section to `## [x.y.z] — YYYY-MM-DD`, tag it.
- **Use the MCP bridge** for any SerpAPI call. If you find yourself importing `requests` in the worker, stop — you're about to violate invariant #5.

---

## 10. Git & CI pipeline

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
| **CI `evals`** | same, only if PR has label `run-evals` | promptfoo evals (~$0.10, real Anthropic API) |

New commits on the PR re-trigger CI (previous runs are cancelled). There is no automated
diff review — see [ADR 0007](docs/adr/0007-remove-automated-llm-diff-review.md).

### Merge requirements

Configured in **GitHub → Settings → Branches → main** (cannot be stored in the repo; apply manually):

| Setting | Value |
|---|---|
| Require a pull request before merging | ✅ |
| Required approving reviews | 1 |
| Required status checks | `python`, `frontend` |
| Require branch up to date | ✅ |
| Allow force pushes | ❌ |

`evals` does **not** block merge — it's opt-in per PR (see below).

### Optional: run evals on a PR

Add label `run-evals` **before** opening the PR, or push a new commit after adding the label (label alone does not re-trigger CI). Requires `ANTHROPIC_API_KEY` in GitHub repo secrets.

---

## 11. Anti-patterns (mistakes made before — don't repeat)

- ❌ Calling `dspy.configure(lm=...)` inside an activity (race condition under parallel execution). Use `dspy.context(lm=...)` per-call.
- ❌ `datetime.now()` inside a workflow (breaks replay). Use `workflow.now()`.
- ❌ Wrapping the whole LangGraph call inside one Temporal activity (no retry granularity). One activity per graph node.
- ❌ Adding a new ORM. Prisma + SQLAlchemy already split the load.
- ❌ Calling blocking/sync code (e.g. DSPy calls) directly inside a coroutine instead of `await asyncio.to_thread(...)`. See `context/code-standards.md` § Async / Concurrency.
- ❌ Re-explaining style rules here. The linter is the source of truth.
- ❌ Pushing directly to `main` or opening a 1000-line PR. CI will pass (maybe), but human review becomes painful and slow — there's no automated first pass to lean on.
- ❌ Duplicating instructions between this file and `CLAUDE.md`, `GEMINI.md`, etc. This file is the only place project-wide rules live; tool-specific files import it (`@AGENTS.md`) and add nothing else, so there is exactly one place to keep in sync.
- ❌ Referencing the `superpowers` plugin or `superpowers:*` skills anywhere in this repo. It is not installed here; use `mattpocock-skills` (§6).
- ❌ Calling `workflow.execute_activity(some_activity, args=[...])` with fewer positional args than `some_activity`'s full signature (e.g. omitting trailing params that have defaults). Temporal's Python SDK only applies the activity's type hints when the payload count exactly matches the declared parameter count (`temporalio/worker/_activity.py`); on a mismatch it silently decodes every arg as an untyped dict/primitive instead of the annotated Pydantic model, and the mismatch is invisible until the activity body actually calls a model-specific method (`.model_dump_json()`, etc). Always pass every declared param positionally, even ones using their default value.

---

## 12. When you're confused

- Product scope, architecture narrative, UI tokens, code standards → `context/*.md` (§6 above)
- Architecture overview → README §How it works and `docs/engineering-decisions.md`
- Why a model was picked, eval backlog, migration plan → `docs/model-choices.md`
- Branch protection / merge gates → §10 above ("Merge requirements" table)
- Deployment + twelve-factor audit → `docs/twelve-factor-audit.md`
- Project roadmap → `docs/roadmap.md`
- Eval results → `evals/results/`
- How to add a new tool to the MCP bridge → `maps_bridge/README.md`
- Frontend-specific rules → `frontend/AGENTS.md` (imported by `frontend/CLAUDE.md`)
- Why there's no automated PR review → [ADR 0007](docs/adr/0007-remove-automated-llm-diff-review.md)
- Past specs and plans → `docs/specs/`, `docs/plans/`

If those don't answer it, ask me before guessing. Don't invent a function, library, or env var.
