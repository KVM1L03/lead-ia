<div align="center">

# LeadIA

**Describe your ideal customer in one sentence. Get a reviewed cohort of qualified leads with personalized cold emails.**

An agentic B2B prospecting pipeline: Google Maps search → LLM qualification → email drafting → human approval.
Built on durable workflows (Temporal), typed LLM programs (DSPy), and a zero-trust MCP tool boundary.

[![CI](https://github.com/KVM1L03/lead-ia/actions/workflows/ci.yml/badge.svg)](https://github.com/KVM1L03/lead-ia/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Temporal](https://img.shields.io/badge/Temporal-000000?logo=temporal&logoColor=white)](https://temporal.io/)
[![DSPy](https://img.shields.io/badge/DSPy-FF6F00?logoColor=white)](https://dspy.ai/)
[![MCP](https://img.shields.io/badge/MCP-000000?logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-PolyForm_NC-blue)](./LICENSE)

**[▶ Live demo](https://lead-ia-ten.vercel.app)** · [Architecture](#architecture) · [Engineering decisions](#engineering-decisions) · [Evaluation](#evaluation) · [Changelog](./CHANGELOG.md) · [Roadmap](./docs/roadmap.md)

</div>

https://github.com/user-attachments/assets/bf714471-e784-45da-b5b2-55ff26b23700

> [!NOTE]
> The live demo replays **recorded** Google Places responses (real API data, cached as fixtures) and runs the pipeline synchronously on Cloud Run — first load may take 5–10 s. Both Maps integrations are production code: clone and run locally with your own key for live search. [Why fixtures →](#engineering-decisions)

---

## The problem

Manual B2B prospecting is three jobs that don't scale past one rep: find companies, filter by fit, write something personal. Teams hire VAs, buy bloated CRMs with mediocre enrichment, or skip personalization and blast generic emails.

LeadIA collapses **search → qualify → write** into one pipeline, and stops at the point where judgment matters: a human approves, edits, or rejects before anything leaves the tool.

```
"dental practices in Warsaw with no online booking"  →  25 leads found
                                                     →  14 qualified (ICP scored + reasoned)
                                                     →  14 drafted emails
                                                     →  you approve 9  →  CSV export
```

---

## How it works

One prompt in, a reviewed cohort out. Prompt-to-query translation runs in the API gateway, before anything durable starts. Inside the workflow, every external call is its own Temporal activity with an explicit timeout and retry policy — while the shortfall branch is plain workflow state, and a single Backfill round expands into four activities (expand query → search → enrich → qualify).

```mermaid
flowchart TB
    START(["👤 ICP prompt + who you are + lead target"])
    START --> PARSE["Parse prompt → Maps query · DSPy PromptToQuery<br/>api_gateway, before the workflow starts"]

    subgraph WF["LeadGenerationWorkflow — external calls run as Temporal activities"]
        direction TB
        SEARCH["① Search Google Maps<br/>MCP tool → SerpAPI / Places API"]
        ENRICH["② Enrich place details · parallel"]
        QUAL["③ Qualify against the ICP · parallel · Haiku 4.5"]
        SHORT{"④ Cohort short of target?"}
        BACKFILL["Backfill round · widen city or industry axis<br/>DSPy ExpandSearchQuery"]
        EMAIL["⑤ Draft cold emails · parallel · Sonnet 4.6<br/>one pass over the merged qualified pool"]

        SEARCH --> ENRICH --> QUAL --> SHORT
        SHORT -->|"yes · up to 2 rounds"| BACKFILL
        BACKFILL -->|"new query · search + qualify again, merge"| SEARCH
        SHORT -->|"target met · or expansion exhausted"| EMAIL
    end

    PARSE --> SEARCH
    QUAL -.->|"not a fit — kept in the run record, never emailed"| RECORD[("Run record")]
    EMAIL --> REVIEW{"Human review · approve · edit · reject"}
    REVIEW --> OUT(["📤 CSV export — send-ready drafts"])

    classDef ai fill:#fff4e6,stroke:#f59e0b,color:#111
    classDef human fill:#e6f4ff,stroke:#3b82f6,color:#111
    class PARSE,QUAL,EMAIL,BACKFILL ai
    class START,REVIEW,OUT human
```

**Backfill** (new in [v0.8](./CHANGELOG.md#080--2026-08-05), Temporal path only — [ADR 0001](./docs/adr/0001-backfill-temporal-only.md)) is the reactive loop that fires when qualification leaves the cohort short of the requested limit: an LLM picks an axis to widen — neighboring city or adjacent industry — never retrying an axis value it already tried, and stops on target met, round cap (2), or a round that adds nothing. Email generation deliberately waits for the loop to settle and then runs **once** over the merged pool, rather than emailing the first batch and the backfilled leads separately — one call site, one merge path ([ADR 0002](./docs/adr/0002-backfill-single-final-email-pass.md)). The cost is that the original leads' drafts are delayed by however long the backfill rounds take. If expansion runs out of room, the UI says so instead of silently under-delivering.

## Architecture

Four independent processes. The agent never touches the network directly — all Maps access goes through the MCP bridge.

```mermaid
flowchart LR
    subgraph client["Browser"]
        UI["Next.js 16 · React 19<br/>Server Actions, Prisma read"]
    end

    subgraph backend["Backend services"]
        API["api_gateway<br/>FastAPI"]
        WORKER["ai_worker<br/>Temporal worker + LangGraph"]
        MCP["maps_bridge<br/>MCP server — only SerpAPI caller"]
    end

    subgraph infra["Infrastructure"]
        TEMPORAL[("Temporal<br/>durable state")]
        PG[("PostgreSQL 16")]
        LF["Langfuse<br/>LLM traces"]
    end

    subgraph ext["External"]
        LLM["Anthropic<br/>LiteLLM fallback router"]
        MAPS["SerpAPI / Google Places API"]
    end

    UI -->|"POST /api/leads/search"| API
    UI -->|"poll status · approve · export"| API
    UI -.->|"run history"| PG
    API -->|"prompt → Maps query · PromptToQuery"| LLM
    API -->|start workflow| TEMPORAL
    TEMPORAL <-->|task queue| WORKER
    WORKER -->|MCP tools over stdio| MCP
    MCP --> MAPS
    WORKER -->|qualify · expand · email| LLM
    WORKER --> PG
    WORKER -.->|OTel spans| LF

    classDef svc fill:#eef2ff,stroke:#6366f1,color:#111
    classDef store fill:#f0fdf4,stroke:#22c55e,color:#111
    classDef out fill:#fef2f2,stroke:#ef4444,color:#111
    class API,WORKER,MCP,UI svc
    class TEMPORAL,PG,LF store
    class LLM,MAPS out
```

| Layer | Tech |
|---|---|
| **Backend** | Python 3.12, FastAPI, Pydantic v2 (strict), Temporal |
| **AI / LLM** | DSPy typed signatures, LangGraph per-lead graph, LiteLLM fallback router, Langfuse (OTel) |
| **Tool access** | MCP bridge (FastMCP) → SerpAPI *or* Google Places API (New), 24 h SQLite cache |
| **Frontend** | Next.js 16, React 19, Tailwind v4, Prisma 7, Server Actions |
| **Data** | PostgreSQL 16 (SQLAlchemy async write + Prisma read), SQLite cache |
| **Infra / CI** | Docker Compose · Cloud Run + Vercel · Terraform · GitHub Actions (ruff, mypy, pytest, eslint, tsc, vitest, promptfoo) |

Two orchestration paths share the same leaf logic: `EXECUTION_MODE=temporal` (local full stack, durable) and `EXECUTION_MODE=sync` (public demo, scale-to-zero). [Why both →](#engineering-decisions)

---

## Quickstart

**Prerequisites:** Docker, Python 3.12+, Node 20+ ([`uv`](https://docs.astral.sh/uv/), `npm`). Node 18 breaks Prisma and vitest — see [`frontend/CLAUDE.md`](./frontend/CLAUDE.md).

```bash
git clone https://github.com/KVM1L03/lead-ia && cd lead-ia
make bootstrap        # uv sync + npm ci + .env.example → .env
# add ANTHROPIC_API_KEY to .env  (MAPS_PROVIDER=mock needs no Maps key)
make up-build         # Temporal, Langfuse, Postgres, api-gateway, ai-worker
make db-push          # Prisma schema → Postgres
make frontend         # → http://localhost:3000
```

| Service | URL |
|---|---|
| App | http://localhost:3000 |
| API (Swagger) | http://localhost:8000/docs |
| Temporal UI | http://localhost:8085 |
| Langfuse | http://localhost:3030 |

<details>
<summary><b>Full setup — Langfuse keys, live Maps providers, frontend env</b></summary>

Canonical env reference: [`.env.example`](./.env.example). Root `.env` uses `localhost` URLs (correct for host processes and exposed compose ports); containers get internal hostnames from `docker-compose.yml`.

**1. Root `.env` — minimum for the full stack**

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | LLM calls (required for a live pipeline run) |
| `SERPAPI_API_KEY` | Maps via SerpAPI — set `MAPS_PROVIDER=serpapi` |
| `GOOGLE_MAPS_API_KEY` | Maps via Google Places API (New) — set `MAPS_PROVIDER=google_places`; needs billing enabled on the GCP project |
| `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY` | Langfuse container secrets — generate **before** first boot: `openssl rand -hex 32` (×3) |

Full-stack defaults (already in `.env.example`): `EXECUTION_MODE=temporal`, `PERSISTENCE_ENABLED=true`, `DEMO_MODE=false`, `MAPS_TRANSPORT=stdio`, `MAPS_PROVIDER=mock`.

**2. Langfuse API keys** — open http://localhost:3030, create a project, copy `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` into root `.env`, then `docker compose restart api-gateway ai-worker`.

**3. Frontend env** — Next.js does **not** read root `.env` at runtime. Create `frontend/.env.local`:

```bash
PRISMA_DATABASE_URL=postgresql://temporal:temporal@localhost:5432/temporal
NEXT_PUBLIC_API_URL=http://localhost:8000
EXECUTION_MODE=temporal
PERSISTENCE_ENABLED=true
```

**Zero-cost maps:** keep `MAPS_PROVIDER=mock` — no Maps API calls at all (fixtures from the `maps_bridge` mock adapter). LLM calls still need `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` / `GOOGLE_API_KEY` via the LiteLLM fallback router).

</details>

<details>
<summary><b>Development commands</b></summary>

```bash
make lint       # ruff + mypy + eslint (same checks as CI)
make test       # pytest + vitest
make eval       # promptfoo eval suite      (~$0.10, real API)
make eval-dspy  # production DSPy-path eval (~$0.15, real API)
make logs       # tail compose logs
make down       # stop, volumes preserved
```

26 backend test modules (pytest, `MAPS_PROVIDER=mock`) + 10 frontend suites (vitest). CI runs both on every PR, plus an advisory LLM diff review.

</details>

---

## Engineering decisions

Each one lists what was **traded away**, not just what was gained.

<details>
<summary><b>🧩 DSPy typed signatures instead of raw prompts</b></summary>

Every LLM task is a `dspy.Predict` signature — a typed Python class with field-level descriptions, not an f-string. `QualifyLead` outputs `is_qualified: bool`, `score: float`, `reasoning: str`, `icp_fit: dict[str, bool]`. `GenerateEmail` returns a subject, body, and `personalization_hooks: list[str]`. `PromptToQuery` turns the user's sentence into a Maps query; `ExpandSearchQuery` picks a Backfill axis and emits the next one.

Length is enforced in two places with different strictness: the signature *asks* for ≤80 chars of subject and ≤200 words of body (a hint the model usually respects), while the `GeneratedEmail` Pydantic model *enforces* `max_length=100` on the subject and `1500` on the body — a hard schema boundary, not a style preference.

**Traded away:** prompt-string transparency (you can't just `print()` what went to the model) and straightforward debugging.

**Why:** DSPy enforces schema compliance at the Python type level, decouples prompt format from model choice, and makes signatures optimizable (fewshot, MIPRO) without rewriting routing logic. When something breaks you're stepping through DSPy's compilation layer instead of reading a string — that's the real cost.

</details>

<details>
<summary><b>⏱️ Temporal for durable execution — and why the demo bypasses it</b></summary>

The local stack runs `LeadGenerationWorkflow` with individually-configured activities: explicit timeout per step, typed retry policies, non-retryable exception lists. Crash mid-qualification → Temporal replays from the last completed activity. Partial results surface in real time via a `@workflow.query`.

**The demo bypasses Temporal entirely.** An always-on worker needs at least one Cloud Run instance polling the task queue continuously — no scale-to-zero, ~$30/month for a portfolio showcase. Instead `EXECUTION_MODE=sync` calls `pipeline.run_pipeline()` directly on the FastAPI request thread, hard-capped at 25 leads to stay inside Cloud Run's 60 s timeout.

**Traded away in the demo:** crash recovery, per-step retry, replay, real-time workflow visibility, and Backfill ([ADR 0001](./docs/adr/0001-backfill-temporal-only.md)).

The per-lead leaf logic is identical — both paths call the same graph nodes, and the Temporal activities are thin wrappers adding timeout and retry metadata. The orchestration around it is not: the sync path has no Backfill, so a cohort that comes up short on the demo stays short.

</details>

<details>
<summary><b>🔀 Two orchestration paths, one business flow</b></summary>

The flow is **one**: search → enrich → qualify → email. The leaf logic runs once, in `qualify_node` and `email_node` (`agent_graph.py`). The orchestration shell is **two by necessity**.

Temporal workflows are 100% deterministic — no direct HTTP, LLM, or MCP calls; every external operation goes through an activity with explicit timeout and retry. The sync path has no such constraint: `run_pipeline()` calls MCP and graph nodes directly in an `asyncio.gather` loop. That difference propagates into error handling (per-activity retries vs. gather-level wrapping), concurrency primitives (replay-safe workflow semaphore vs. `asyncio.Semaphore`), and progress visibility (`@workflow.query` vs. nothing).

A shared `orchestrate(steps, executor)` adapter was considered and **rejected** — a leaky abstraction over two genuinely different execution models, harder to read and defend than explicit duplication.

| Path | Orchestrator | Leaf logic |
|---|---|---|
| `EXECUTION_MODE=sync` | `run_pipeline()` — `pipeline.py` | `process_one_lead()` → graph nodes |
| `EXECUTION_MODE=temporal` | `LeadGenerationWorkflow.run()` — `workflows.py` | `qualify_lead_activity` + `generate_email_activity` → same graph nodes |

</details>

<details>
<summary><b>⚖️ Two-model split: Haiku qualifies, Sonnet writes</b></summary>

Qualification runs on every scraped place. Email generation runs only on qualified leads (~40–70% of results). The [eval results](#evaluation) drove the split.

**Traded away:** simplicity (one model everywhere) and cost predictability.

**Why:** Haiku costs ~$0.095 / 100 calls vs ~$0.032 for Gemini Flash, but Sonnet produces noticeably better cold-email copy — and it only runs on the qualified subset. Two models keep per-search cost manageable while putting the quality budget where it's visible. GPT-4.1-nano stays as a last-resort circuit breaker only (2% recall makes it useless for qualification in practice).

</details>

<details>
<summary><b>🔒 MCP zero-trust boundary for the scraper</b></summary>

`maps_bridge` is the only process that imports `httpx` and calls SerpAPI. `ai_worker` reaches it via the MCP tool protocol — a subprocess over stdio locally, or an inlined module import on Cloud Run (avoiding experimental sidecar overhead).

**Traded away:** simplicity — a direct `httpx.get(serpapi_url)` in the worker is 5 lines.

**Why:** the agent can't accidentally hit SerpAPI, can't leak the API key into LLM context, and swapping the data source touches `maps_bridge/` only. The inline Cloud Run transport still preserves the boundary at module level — SerpAPI code never moves into the worker package.

</details>

<details>
<summary><b>💸 Three maps providers, and SKU-tier cost engineering</b></summary>

SerpAPI's free tier is 250 searches/month; a single-round run makes 25–30 calls (one Text Search + one Place Details per business), and every Backfill round adds another Text Search plus a Place Details per newly-found place — up to roughly 3× that on a run that expands twice. So ~10 runs/month free at best, or $25 for 40 — not viable for personal use of a portfolio tool.

Google Places API (New) Text Search offers 5,000 free calls/month (~200 runs at $0), but has a billing mechanic that's easy to miss: **it charges at the highest SKU tier among all fields in the FieldMask**. Adding `places.rating` or `places.userRatingCount` escalates a Text Search from Pro (5,000 free/month) to Enterprise (1,000 free/month) — a 5× smaller quota, no warning, no automatic spend cap. `GooglePlacesProvider` therefore uses a tight FieldMask that omits every rating and review field, and two tests in `test_google_places_provider.py` assert it stays that way — a **cost invariant**, not a style preference.

**Traded away:** `rating` and `review_count` are `None` on the Google Places path, so rating-based personalization ("I notice you have 4.8 stars") is unavailable there. Every consumer was checked first: the qualifier and email generator both serialize with `model_dump_json(exclude_none=True)`, so `None` never reaches the prompt; CSV export writes an empty cell. No qualification signal was lost — rating was a personalization hook, not an ICP criterion.

**The abstraction paid off:** adding the third provider required zero changes to `ai_worker`, `pipeline.py`, or `workflows.py`. The `MapsProvider` Protocol held.

| Provider | Set via | Free tier | Returns rating? | Best for |
|---|---|---|---|---|
| `mock` | default | unlimited | yes (fixture) | local dev, CI, evals |
| `serpapi` | `SERPAPI_API_KEY` | 250 calls/month | yes | small-scale live runs |
| `google_places` | `GOOGLE_MAPS_API_KEY` | 5,000 calls/month | no (FieldMask) | sustained personal use |

Direct Maps scraping was rejected outright: it violates ToS, and a portfolio project built on ToS violations is neither shareable nor publishable.

</details>

<details>
<summary><b>🚦 Cost-aware deploy: scale-to-zero + layered rate limits</b></summary>

Cloud Run (scale to zero), in-process rate limiter, hard cap of 25 leads per sync request. Two independent layers, both no-ops when `DEMO_MODE=false`:

- **RunLimiter** — global daily run cap. Key `demo:runs:{YYYY-MM-DD}`, atomic INCR + conditional EXPIRE via a Redis Lua script (or an in-process counter in the demo).
- **RequestLimiter** — per-IP per-minute fixed window, as Starlette middleware. Key `demo:reqs:{ip}:{minute}`.

**Traded away:** global accuracy under horizontal scale — in-memory counters are per-instance, not shared across replicas.

**Why:** Redis adds ~$15/month plus a VPC dependency. The in-process backend is documented as a soft guard, not a billing fence. The hard lead cap enforces the timeout ceiling *before* any LLM call starts — a clean 429 instead of a mid-flight 504.

</details>

<details>
<summary><b>🎞️ Demo data: recorded fixtures instead of live API calls</b></summary>

The live demo runs `MAPS_PROVIDER=mock` against Google Places responses recorded once and committed to `maps_bridge/fixtures/recorded/`. The mock provider replays them with exact-token, Jaccard-fuzzy, and round-robin fallback matching.

**Why:** the demo cap allows 20 runs/day (~600/month); the Places API free tier covers ~200 runs. Serving real demo traffic from a free key would burn the quota in ~10 days — a recruiter opening the link mid-month would get a quota error instead of a product.

**Traded away:** data freshness and arbitrary-category search in the demo. Unrecorded queries return a representative cross-category sample. Irrelevant for the purpose: a month-old set of Warsaw dental clinics demonstrates the pipeline identically.

**The integrations are real.** `GooglePlacesProvider` and `SerpAPIMapsProvider` are production code behind the same `MapsProvider` Protocol the mock satisfies.

</details>

---

## Evaluation

Same 100-example hand-labeled gold set throughout: 50 qualified, 30 hard negatives, 20 ambiguous; 5 outreach goals × 20 each. Temperature 0 for reproducibility.

**Production path** — `make eval-dspy` runs the real `qualify_lead()` through the `QualifyLead` DSPy signature *(2026-07-08)*:

| Model | Accuracy | Precision | Recall | F1 | p95 latency | Cost / 100 |
|---|---|---|---|---|---|---|
| `claude-haiku-4-5` ✅ **shipped** | 81% | 89% | 78% | **83%** | 2 810 ms | $0.134 |
| `gemini-2.5-flash` | *pending* | — | — | — | — | — |

**Proxy path** — `make eval` runs promptfoo against a flat prompt (`evals/prompts/qualify.txt`), *not* production code *(2026-07-03)*:

| Model | Accuracy | Precision | Recall | F1 | p95 latency | Cost / 100 |
|---|---|---|---|---|---|---|
| `gemini-2.5-flash` | 82% | 94% | 75% | 83% | 1 212 ms | $0.032 |
| `claude-haiku-4-5` ✅ | 77% | 89% | 70% | 78% | 2 492 ms | $0.095 |
| `openai/gpt-4.1-nano` | 42% | 100% | 2% | 3% | 1 726 ms | $0.007 |

**Finding:** the DSPy path beats the flat prompt for Haiku by +5 pp F1 (83% vs 78%) and +8 pp recall — structured output gives the model more guidance than a flat string. That gap is the argument for **not** using the cheap promptfoo eval as a migration gate.

> **In progress:** evaluating `gemini-2.5-flash` as a drop-in for both roles. Gate = DSPy-path eval (qualifier) + blind human comparison (email). Rollback via `QUALIFIER_MODEL` / `EMAIL_MODEL`. Gemini's DSPy numbers need `thinkingBudget: 0` wired in first to prevent JSON truncation.

Full suite, gold dataset, and metric scripts: [`evals/`](./evals/).

---

## Release history

Full log with per-release detail in [`CHANGELOG.md`](./CHANGELOG.md).

| Version | Date | Headline |
|---|---|---|
| [0.8.0](./CHANGELOG.md#080--2026-08-05) | 2026-08-05 | **Backfill** — reactive search expansion when a cohort falls short, with exhaustion surfaced in the UI |
| [0.7.0](./CHANGELOG.md#070--2026-07-29) | 2026-07-29 | Glass-morphism UI restyle, working demo prompt examples, MCP session reuse |
| [0.6.0](./CHANGELOG.md#060--2026-07-11) | 2026-07-11 | Google Places provider + FieldMask cost engineering, recorded fixtures, Maps pagination |
| [0.5.0](./CHANGELOG.md#050--2026-07-08) | 2026-07-08 | Public demo (`EXECUTION_MODE=sync`), CSV export, DSPy-path eval harness |
| [0.4.0](./CHANGELOG.md#040--2026-07-03) | 2026-07-03 | 100-example eval suite, demo rate limiting, Cloud Run images, Terraform bootstrap |
| [0.3.0](./CHANGELOG.md#030--2026-07-02) | 2026-07-02 | Approval UI — design system, live run progress, lead cohort table, run history |
| [0.2.0](./CHANGELOG.md#020--2026-07-01) | 2026-07-01 | Durable pipeline — LangGraph agent, Temporal workflow, Langfuse tracing, REST API |
| [0.1.0](./CHANGELOG.md#010--2026-06-30) | 2026-06-30 | Foundations — MCP maps bridge, DSPy qualifier + email signatures, LLM router |

---

## What I'd do differently at production scale

- **Always-on Temporal worker.** The sync/Temporal duality exists purely because scale-to-zero economics conflict with a persistent task-queue poller. A real deployment keeps one worker up and drops the sync path — which also gives the demo Backfill.
- **Real auth.** No identity layer today. Multi-tenant use needs accounts, per-user encrypted key storage, and billing.
- **Postgres + Redis in the demo too.** In-memory rate limiting and stateless results are fine for a showcase but break across deploys and instances.
- **Close the Gemini eval gate.** The proxy promptfoo eval isn't sufficient; the DSPy-path numbers for Gemini are still missing.
- **Email sending + warming.** Approval produces a CSV; production needs an ESP integration, domain warming, deliverability monitoring, and unsubscribe handling.
- **Multi-region.** Cloud Run is single-region. Global prospecting has latency and data-residency implications worth planning early.

## Deployment

Live demo: **Vercel** (frontend) + **Cloud Run** (backend). The backend is one service (`lead-api`) running `EXECUTION_MODE=sync`, `MAPS_TRANSPORT=inline`, and in-process rate limiting — `maps_bridge` inlined in the same container, no sidecar. [`infra/terraform/`](./infra/terraform/) codifies the IaC foundation (VPC, Artifact Registry, API enablement); the live service ships via `gcloud`. The VPC connector, Cloud SQL, and Redis are defined but not provisioned — the demo runs without them. Full audit: [`docs/twelve-factor-audit.md`](./docs/twelve-factor-audit.md).

## Documentation

| Doc | What's in it |
|---|---|
| [`CHANGELOG.md`](./CHANGELOG.md) | Release history |
| [`docs/roadmap.md`](./docs/roadmap.md) | What's planned, in priority order |
| [`docs/model-choices.md`](./docs/model-choices.md) | Why each model was picked; migration plan |
| [`docs/adr/`](./docs/adr/) | Architecture decision records |
| [`docs/cost-guardrails.md`](./docs/cost-guardrails.md) | API quota and spend invariants |
| [`AGENTS.md`](./AGENTS.md) · [`CLAUDE.md`](./CLAUDE.md) | Rules for AI coding agents working in this repo |
| [`context/`](./context/) | Spec-driven "constitution" — product, architecture, UI, standards |

> **LeadForge** is the internal codename you'll see in the design system, `context/`, and the compose service names. Same project.

---

## License

[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/) — free for noncommercial use, study, and modification. Commercial use requires a separate license: **klabusit@gmail.com**.

© 2026 Kamil Labus
