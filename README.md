# LeadIA

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Temporal](https://img.shields.io/badge/Temporal-000000?logo=temporal&logoColor=white)](https://temporal.io/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![DSPy](https://img.shields.io/badge/DSPy-FF6F00?logoColor=white)](https://dspy.ai/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![CI](https://github.com/KVM1L03/lead-ia/actions/workflows/ci.yml/badge.svg)](https://github.com/KVM1L03/lead-ia/actions/workflows/ci.yml)

🔴 **[Try it live](https://lead-ia-ten.vercel.app)** — first load may take 5–10 s (Cloud Run cold start).
The full durable stack (Temporal, Langfuse, PostgreSQL) runs locally via Docker Compose.

> **Demo data:** the live demo runs on recorded Google Places responses — real API data, cached as fixture files rather than called live. The demo cap is 20 runs/day (~600/month); the Places API (New) Place Details free tier supports ~200 runs/month at 25 leads each. Serving live traffic from a free API key would exhaust the quota in roughly 10 days. Both the Google Places and SerpAPI integrations are real — clone and run locally with your own key for live search.




https://github.com/user-attachments/assets/bf714471-e784-45da-b5b2-55ff26b23700




---

## The problem

Manual B2B prospecting is slow: find companies, filter by fit, write personalized outreach — three separate tasks that don't scale past one rep. Teams either hire VAs, buy bloated CRMs with mediocre enrichment, or skip personalization and blast generic emails. LeadIA collapses the search–qualify–write loop into a single pipeline that a human reviews and approves before anything leaves the tool.

## What it does

**prompt → SerpAPI (Google Maps) → LLM qualifier → email draft → human approval cohort**

You describe who you're looking for ("dental practices in Warsaw with no online booking"), optionally add a line about yourself, and pick how many leads to find. The pipeline scrapes Google Maps for matching businesses, qualifies each one against your ICP using a cheap fast model, drafts a personalized cold email for qualified leads with a pricier quality model, and surfaces a cohort for review — approve, edit, or reject, then export approved leads to CSV (business data, drafted email, qualification metadata). No email sending built in; the CSV is the handoff artifact.

## Architecture

**Agent flow** — one prompt in, reviewed cohort out:

```mermaid
flowchart TB
    START(["You · ICP prompt + who you are"])

    START --> PARSE["① Parse prompt → Maps search query · DSPy"]
    PARSE --> SEARCH["② Search Google Maps · MCP → SerpAPI"]

    SEARCH --> LOOP

    subgraph LOOP["③–⑤ Per business · parallel"]
        direction TB
        ENRICH["Enrich details"]
        QUAL{"ICP fit? · Haiku"}
        EMAIL["Draft email · Sonnet"]
        DROP([discard])

        ENRICH --> QUAL
        QUAL -->|qualified| EMAIL
        QUAL -->|not a fit| DROP
    end

    LOOP --> COHORT["⑥ Lead cohort"]
    COHORT --> REVIEW{"⑦ Human review · approve · edit · reject"}
    REVIEW --> OUT(["Send-ready drafts"])
```

**Under the hood (local full stack):** each numbered step above is a Temporal activity with its own timeout and retry policy — crash mid-run replays from the last completed step. LLM calls trace to Langfuse via a `SHA-256(workflow_id)` correlation trick (Temporal doesn't propagate OTel context across activity boundaries). The [live demo](https://lead-ia-ten.vercel.app) runs the same pipeline synchronously on Cloud Run (`EXECUTION_MODE=sync`) — no Temporal poller, no Postgres persistence — behind an in-process rate limiter.

---

## Engineering decisions

### DSPy typed signatures instead of raw prompts

Every LLM extraction task is a `dspy.Predict` signature — a typed Python class with field-level descriptions, not an f-string. `QualifyLead` outputs `is_qualified: bool`, `score: float`, `reasoning: str`, `icp_fit: dict[str, bool]`. `GenerateEmail` constrains subject to 80 chars and body to 200 words at the type level.

**Traded away:** prompt string transparency (you can't just `print()` what went to the model) and straightforward debugging.

**Why:** DSPy enforces schema compliance at the Python type level, decouples the prompt format from the model being used, and makes signatures optimizable via fewshot or MIPRO without rewriting routing logic. When something breaks, you're stepping through DSPy's compilation layer rather than reading a plain string — that's the real cost.

---

### Temporal for durable execution — and why the demo bypasses it

The local stack runs `LeadGenerationWorkflow` with 5 individually-configured activities: explicit timeout per step, typed retry policies, non-retryable exception lists. Crash mid-qualification: Temporal replays from the last completed activity. Partial results surface in real time via a `@workflow.query`.

**The demo bypasses Temporal entirely.** An always-on worker needs at least one Cloud Run instance running continuously to poll the task queue — no scale-to-zero. That's ~$30/month for a portfolio showcase. Instead, `EXECUTION_MODE=sync` calls `pipeline.run_pipeline()` directly on the FastAPI request thread, capped at 25 leads to stay under Cloud Run's 60 s timeout.

**Traded away in demo:** crash recovery, per-step retry, replay, and real-time workflow visibility.

The business logic is identical — both paths call the same functions in `pipeline.py`. The Temporal activities are thin wrappers that add timeout and retry metadata on top.

---

### Why two orchestration paths

The business flow is **one**: search → enrich → qualify → email. The leaf logic runs once, in `qualify_node` and `email_node` (`agent_graph.py`). But the orchestration shell is **two by necessity**.

Temporal workflows are 100% deterministic — no direct HTTP, LLM, or MCP calls. Every external operation must go through an activity with an explicit timeout and retry policy. The sync path has no such constraint: `run_pipeline()` calls MCP and graph nodes directly in an asyncio gather loop. That difference propagates into error handling (per-activity retries vs. gather-level exception wrapping), concurrency primitives (replay-safe workflow semaphore vs. plain `asyncio.Semaphore`), and progress visibility (`@workflow.query` vs. nothing). Extracting a shared `orchestrate(steps, executor)` callback adapter was considered and rejected — it would be a leaky abstraction over two genuinely different execution models, harder to read and harder to defend than explicit duplication.

| Path | Orchestrator | Leaf logic |
|---|---|---|
| `EXECUTION_MODE=sync` | `run_pipeline()` — `pipeline.py` | `process_one_lead()` → graph nodes |
| `EXECUTION_MODE=temporal` | `LeadGenerationWorkflow.run()` — `workflows.py` | `qualify_lead_activity` + `generate_email_activity` → same graph nodes |

---

### Two-model split: Haiku (qualify) vs Sonnet (email)

Qualification runs on every scraped place. Email generation runs only on qualified leads (~40–70% of results). The eval result drove the split — see [Evaluation](#evaluation) below.

**Traded away:** simplicity (one model everywhere) and cost predictability.

**Why:** Haiku costs ~$0.095 per 100 calls vs ~$0.032 for Gemini Flash. Sonnet produces noticeably better cold-email copy than cheaper models, and it only runs on the qualified subset. The two-model approach keeps per-search cost manageable while putting quality budget where it matters. GPT-4.1-nano is kept only as a last-resort circuit breaker (2% recall makes it useless for qualification in practice).

---

### MCP zero-trust boundary for the scraper

`maps_bridge` is the only process that imports `httpx` and calls SerpAPI. `ai_worker` calls it via the MCP tool protocol — a subprocess over stdio transport locally, or an inlined module import on Cloud Run (to avoid experimental sidecar overhead).

**Traded away:** simplicity — a direct `httpx.get(serpapi_url)` in the worker is 5 lines.

**Why:** The agent can't accidentally hit SerpAPI directly, can't leak the API key into LLM context, and swapping the data source means changing `maps_bridge/` only. The "inline" Cloud Run transport still preserves the boundary at the module level — SerpAPI code never moves to the worker package.

---

### SerpAPI over direct Maps scraping

**Traded away:** zero API cost.

**Why:** Direct Google Maps scraping violates ToS — a portfolio project built on ToS violations is neither shareable nor publishable. SerpAPI returns structured JSON (`local_results`, `place_results`) with no HTML parsing, handles rate limiting, and makes the project openly linkable. A 24 h SQLite cache minimizes live API calls during development; evals run against the cache by default.

---

### Three maps providers, and SKU-tier cost engineering

SerpAPI's free tier is 250 searches/month. Each LeadIA run makes 25–30 API calls (one Text Search + one Place Details per business). That's ~10 full runs/month free; 40 runs/month costs $25. Not viable for personal use of a portfolio tool.

Google Places API (New) Text Search offers 5,000 free calls/month — enough for ~200 runs at $0. But Places API (New) has a billing mechanic that's easy to miss: **it charges at the highest SKU tier among all requested fields in the FieldMask**. Adding `places.rating` or `places.userRatingCount` escalates a Text Search call from the Pro tier (5,000 free/month) to the Enterprise tier (1,000 free/month) — a 5× smaller free quota, with no warning and no automatic spend cap. To stay at Pro tier, `GooglePlacesProvider` uses a tight FieldMask (`places.id`, `places.displayName`, `places.formattedAddress`, `places.location`, `places.primaryType`, `places.types`) that omits all rating and review fields. Two sync tests in `test_google_places_provider.py` assert the FieldMask never contains those fields — they're treated as a cost invariant, not a style preference.

**Traded away:** `rating` and `review_count` are `None` on every result from the Google Places path. Rating-based personalization ("I notice you have 4.8 stars") is unavailable on this provider. Every consumer was checked before accepting this: the qualifier serializes the place with `model_dump_json(exclude_none=True)`, so `None` values are dropped before reaching the LLM prompt; the email generator does the same; the CSV export writes an empty cell. No qualification signal was lost — rating was a personalization hook, not an ICP criterion.

**The abstraction paid off:** adding the third provider required zero changes to `ai_worker`, `pipeline.py`, or `workflows.py`. The `MapsProvider` Protocol held; the only code that changed was `maps_bridge/`.

| Provider | Set via | Free tier | Returns rating? | Best for |
|---|---|---|---|---|
| `mock` | default | unlimited | yes (fixture) | local dev, CI, evals |
| `serpapi` | `SERPAPI_API_KEY` | 250 calls/month | yes | small-scale live runs |
| `google_places` | `GOOGLE_MAPS_API_KEY` | 5,000 calls/month | no (FieldMask) | sustained personal use |

---

### Cost-aware deploy: scale-to-zero + layered rate limits

Cloud Run (scale to zero), in-process rate limiter (`RATE_LIMIT_BACKEND=memory` in demo), hard cap of 25 leads per sync request.

Two independent rate-limit layers, both no-ops when `DEMO_MODE=false`:
- **RunLimiter** — global daily run cap. Key: `demo:runs:{YYYY-MM-DD}`, atomic INCR + conditional EXPIRE via Redis Lua script (or in-process counter in demo).
- **RequestLimiter** — per-IP per-minute fixed window as Starlette middleware. Key: `demo:reqs:{ip}:{minute}`.

**Traded away:** global rate-limit accuracy under horizontal scale — in-memory counters are per-instance, not shared across replicas.

**Why:** Redis adds ~$15/month and a VPC dependency. The in-process backend is explicitly documented as a soft guard (not a billing fence). The hard lead cap enforces a Cloud Run timeout ceiling *before* any LLM calls start — clean 429 error, not a mid-flight 504.

---

### Demo data: recorded fixtures instead of live API calls

The live demo runs `MAPS_PROVIDER=mock`, backed by Google Places API responses recorded once and committed to `maps_bridge/fixtures/recorded/`. The mock provider replays them with exact-token, Jaccard-fuzzy, and round-robin fallback matching — no live API calls, no quota risk.

**Why:** The demo cap allows 20 runs/day (~600/month). The Places API (New) Place Details free tier is 5,000 calls/month; at 25 leads per run, that's ~200 runs before the quota is exhausted. Serving real demo traffic from a free key would burn through it in ~10 days — a recruiter opening the link mid-month would see a quota error instead of a product. Caching the responses eliminates that failure mode entirely, at the cost of data freshness — which is irrelevant: a month-old set of Warsaw dental clinics looks identical for the purposes of demonstrating the pipeline.

**Traded away:** data freshness and the ability to search arbitrary categories in the live demo. Queries that don't match a recorded category return a representative cross-category sample rather than a live result.

**The integrations are real.** `GooglePlacesProvider` and `SerpAPIMapsProvider` are production code, wired through the same `MapsProvider` Protocol the mock satisfies. Set `MAPS_PROVIDER=google_places` (with a GCP key) or `MAPS_PROVIDER=serpapi` locally for live search.

---

## Evaluation

Same 100-example hand-labeled gold set throughout (50 qualified, 30 hard negatives, 20 ambiguous; 5 outreach goals × 20 each). Temperature=0 for reproducibility.

**DSPy-path eval** (`make eval-dspy`) — runs the actual production `qualify_lead()` function through the `QualifyLead` DSPy signature. Run 2026-07-08.

| Model | Accuracy | Precision | Recall | F1 | p95 Latency | Cost / 100 calls |
|---|---|---|---|---|---|---|
| `claude-haiku-4-5-20251001` ✅ | 81% | 89% | 78% | **83%** | 2 810 ms | $0.134 |
| `gemini-2.5-flash` | not yet run | — | — | — | — | — |
| `openai/gpt-4.1-nano` | not yet run | — | — | — | — | — |

**Plain-text prompt eval** (`make eval`) — promptfoo against `evals/prompts/qualify.txt` (a proxy for the signature, not the production code). Run 2026-07-03.

| Model | Accuracy | Precision | Recall | F1 | p95 Latency | Cost / 100 calls |
|---|---|---|---|---|---|---|
| `gemini-2.5-flash` | 82% | 94% | 75% | 83% | 1 212 ms | $0.032 |
| `claude-haiku-4-5-20251001` ✅ | 77% | 89% | 70% | 78% | 2 492 ms | $0.095 |
| `openai/gpt-4.1-nano` | 42% | 100% | 2% | 3% | 1 726 ms | $0.007 |

**DSPy vs plain-text for Haiku:** the production DSPy path scores F1 83% vs 78% on the proxy eval (+5 pp), with recall 78% vs 70% (+8 pp). The structured `QualifyLead` output format gives the model more explicit guidance than the flat prompt — the gap is an argument for not using the plain-text eval as a migration gate. The Gemini DSPy-path numbers are pending (`make eval-dspy ARGS="--model gemini/gemini-2.5-flash"` — Gemini Flash `thinkingBudget: 0` must be wired into the DSPy call first to prevent JSON truncation).

> **In progress:** testing `gemini-2.5-flash` as a drop-in replacement for both Haiku (qualifier) and Sonnet (email). Migration gate: DSPy-path eval for qualifier + human email comparison. Rollback via `QUALIFIER_MODEL` / `EMAIL_MODEL` env vars.

See [`evals/`](./evals/) for the full suite, gold dataset, and metrics scripts (`make eval` for plain-text, `make eval-dspy` for the production path).

---

## Run it locally

**Prerequisites:** Docker, Python 3.12+, **Node 20+** ([`uv`](https://docs.astral.sh/uv/), `npm`). System Node 18 breaks Prisma and vitest — see [`frontend/CLAUDE.md`](./frontend/CLAUDE.md).

Canonical env reference: [`.env.example`](./.env.example). Root `.env` uses `localhost` URLs (correct for host processes and exposed compose ports); containers get internal hostnames via `docker-compose.yml`.

```bash
git clone https://github.com/KVM1L03/lead-ia
cd lead-ia
make bootstrap          # uv sync + npm ci + copy .env.example → .env
```

**1. Edit root `.env`** — minimum for the full stack:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | LLM calls (required for a live pipeline run) |
| `SERPAPI_API_KEY` | Maps via SerpAPI — set `MAPS_PROVIDER=serpapi` (skip if using `mock` or `google_places`) |
| `GOOGLE_MAPS_API_KEY` | Maps via Google Places API (New) — set `MAPS_PROVIDER=google_places`; billing must be enabled on the GCP project |
| `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY` | Langfuse container secrets — generate **before** first boot: `openssl rand -hex 32` (×3) |

Full-stack defaults (already in `.env.example`): `EXECUTION_MODE=temporal`, `PERSISTENCE_ENABLED=true`, `DEMO_MODE=false`, `MAPS_TRANSPORT=stdio`, `MAPS_PROVIDER=mock`.

**2. Start infra + backend**

```bash
make up-build           # Temporal, Langfuse, Postgres, api-gateway, ai-worker
```

**3. Langfuse API keys** — open http://localhost:3030, create a project, copy `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` into root `.env`, then:

```bash
docker compose restart api-gateway ai-worker
```

**4. Database schema + frontend env**

```bash
make db-push            # Prisma schema → Postgres (/history needs this)
```

Create `frontend/.env.local` (Next.js does **not** read root `.env` at runtime):

```bash
PRISMA_DATABASE_URL=postgresql://temporal:temporal@localhost:5432/temporal
NEXT_PUBLIC_API_URL=http://localhost:8000
EXECUTION_MODE=temporal
PERSISTENCE_ENABLED=true
```

**5. Run the UI**

```bash
make frontend           # Next.js dev server on :3000
```

| Service | URL |
|---|---|
| App | http://localhost:3000 |
| API (Swagger) | http://localhost:8000/docs |
| Temporal UI | http://localhost:8085 |
| Langfuse | http://localhost:3030 |

**Zero-cost maps (optional):** set `MAPS_PROVIDER=mock` in root `.env` — no SerpAPI calls (fixtures from `maps_bridge` mock adapter). LLM calls still require `ANTHROPIC_API_KEY` (or fallback keys `OPENAI_API_KEY` / `GOOGLE_API_KEY` via the LiteLLM router) when you run the pipeline.

---

## Deploy it

The live demo runs on **Vercel** (frontend) + **Cloud Run** (backend). The backend is a single Cloud Run service (`lead-api`) running `EXECUTION_MODE=sync`, `MAPS_TRANSPORT=inline`, and in-process rate limiting — `maps_bridge` is inlined in the same container, no sidecar. See [Engineering decisions](#temporal-for-durable-execution--and-why-the-demo-bypasses-it). [`infra/terraform/`](./infra/terraform/) codifies the IaC foundation (VPC, Artifact Registry, API enablement); the live service is deployed via `gcloud`. The VPC connector and Cloud SQL/Redis are defined in Terraform but not yet provisioned — the demo runs without them (in-process rate limiting, `PERSISTENCE_ENABLED=false`). See [`docs/twelve-factor-audit.md`](./docs/twelve-factor-audit.md) for the full Cloud Run audit.

---

## Tech stack

| Layer | Tech |
|---|---|
| **Backend** | Python 3.12, FastAPI, Pydantic v2 (strict mode), Temporal |
| **AI / LLM** | DSPy, LiteLLM (multi-provider fallback router), Langfuse (OTel observability) |
| **Scraping** | SerpAPI or Google Places API (New) via MCP bridge (FastMCP), SQLite 24 h cache |
| **Frontend** | Next.js 16, React 19, Tailwind v4, Prisma 7 |
| **Data** | PostgreSQL 16 (SQLAlchemy async + Prisma read), SQLite |
| **Infra** | Docker Compose (local), Cloud Run + Vercel (deployed), Terraform (GCP) |
| **CI** | GitHub Actions — ruff, mypy, pytest, eslint, tsc, vitest, prisma generate, promptfoo evals |

---

## What I'd do differently at production scale

- **Always-on Temporal worker.** The sync/Temporal duality exists purely because scale-to-zero economics on Cloud Run conflict with a persistent task-queue poller. A real deployment keeps one worker running and drops the sync path entirely.
- **Real auth.** The demo has no identity layer. Multi-tenant use needs user accounts, per-user API key storage, and billing.
- **PostgreSQL in demo too.** In-memory rate limiting and stateless results are fine for a showcase but break across deploys and Cloud Run instances.
- **DSPy-path eval now available (`make eval-dspy`).** The plain-text promptfoo eval was a proxy; the production path (`QualifyLead` DSPy signature) is now separately benchmarked and scores higher for Haiku (F1 83% vs 78%). Gemini DSPy-path numbers still pending before the migration gate is fully closed.
- **Email sending + warming.** The approval step produces a CSV export (business data, drafted emails, qualification scores) but stops short of delivery — production needs an ESP integration, domain warming, and deliverability monitoring.
- **Multi-region.** Cloud Run is single-region. Global B2B prospecting has latency and data-residency implications worth planning early.

---

## License

Licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/).
Free for noncommercial use, study, and modification. Commercial use requires a separate license — contact klabusit@gmail.com.

© 2026 Kamil Labus
