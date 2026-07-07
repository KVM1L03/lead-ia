# LeadIA

**Prompt → Google Maps → AI qualifier → personalized email → human approval**

🚀 **[Try it live](https://lead-ia-ten.vercel.app)** — first load may take 5–10 s (Cloud Run cold start).
The full durable stack (Temporal, Langfuse, PostgreSQL) runs locally via Docker Compose.




https://github.com/user-attachments/assets/bf714471-e784-45da-b5b2-55ff26b23700




---

## The problem

Manual B2B prospecting is slow: find companies, filter by fit, write personalized outreach — three separate tasks that don't scale past one rep. Teams either hire VAs, buy bloated CRMs with mediocre enrichment, or skip personalization and blast generic emails. LeadIA collapses the search–qualify–write loop into a single pipeline that a human reviews and approves before anything leaves the tool.

## What it does

**prompt → SerpAPI (Google Maps) → LLM qualifier → email draft → human approval cohort**

You describe who you're looking for ("dental practices in Warsaw with no online booking"), optionally add a line about yourself, and pick how many leads to find. The pipeline scrapes Google Maps for matching businesses, qualifies each one against your ICP using a cheap fast model, drafts a personalized cold email for qualified leads with a pricier quality model, and surfaces a cohort for review — approve, edit, or reject before anything sends.

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

### Cost-aware deploy: scale-to-zero + layered rate limits

Cloud Run (scale to zero), in-process rate limiter (`RATE_LIMIT_BACKEND=memory` in demo), hard cap of 25 leads per sync request.

Two independent rate-limit layers, both no-ops when `DEMO_MODE=false`:
- **RunLimiter** — global daily run cap. Key: `demo:runs:{YYYY-MM-DD}`, atomic INCR + conditional EXPIRE via Redis Lua script (or in-process counter in demo).
- **RequestLimiter** — per-IP per-minute fixed window as Starlette middleware. Key: `demo:reqs:{ip}:{minute}`.

**Traded away:** global rate-limit accuracy under horizontal scale — in-memory counters are per-instance, not shared across replicas.

**Why:** Redis adds ~$15/month and a VPC dependency. The in-process backend is explicitly documented as a soft guard (not a billing fence). The hard lead cap enforces a Cloud Run timeout ceiling *before* any LLM calls start — clean 429 error, not a mid-flight 504.

---

## Evaluation

100-example hand-labeled gold set (50 qualified, 30 hard negatives, 20 ambiguous; 5 outreach goals × 20 each). Run 2026-07-03 via promptfoo at temperature=0, 3 providers in parallel.

| Model | Accuracy | Precision | Recall | F1 | p95 Latency | Cost / 100 calls |
|---|---|---|---|---|---|---|
| `claude-haiku-4-5-20251001` ✅ | 77% | 89% | 70% | 78% | 2 492 ms | $0.095 |
| `gemini-2.5-flash` | 82% | 94% | 75% | 83% | 1 212 ms | $0.032 |
| `openai/gpt-4.1-nano` | 42% | 100% | 2% | 3% | 1 726 ms | $0.007 |

**Note:** this eval benchmarks plain-text prompts via promptfoo, not the `QualifyLead` DSPy signature used in production. Gemini's eval used `thinkingBudget: 0` to prevent JSON truncation. A DSPy-path eval (on the production code) is on the backlog before any model migration ships.

> **In progress:** testing `gemini-2.5-flash` with thinking in **auto mode** (adaptive budget, not `thinkingBudget: 0`) as a drop-in replacement for both Haiku (qualifier) and Sonnet (email). Migration requires a DSPy-path eval + human email comparison. Rollback via `QUALIFIER_MODEL` / `EMAIL_MODEL` env vars.

See [`evals/`](./evals/) for the full suite, gold dataset, and metrics script.

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
| `SERPAPI_API_KEY` | Google Maps via SerpAPI (skip if `MAPS_PROVIDER=mock`) |
| `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY` | Langfuse container secrets — generate **before** first boot: `openssl rand -hex 32` (×3) |

Full-stack defaults (already in `.env.example`): `EXECUTION_MODE=temporal`, `PERSISTENCE_ENABLED=true`, `DEMO_MODE=false`, `MAPS_TRANSPORT=stdio`.

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
| **Scraping** | SerpAPI via MCP bridge (FastMCP), SQLite 24 h cache |
| **Frontend** | Next.js 16, React 19, Tailwind v4, Prisma 7 |
| **Data** | PostgreSQL 16 (SQLAlchemy async + Prisma read), SQLite |
| **Infra** | Docker Compose (local), Cloud Run + Vercel (deployed), Terraform (GCP) |
| **CI** | GitHub Actions — ruff, mypy, pytest, eslint, tsc, vitest, prisma generate, promptfoo evals |

---

## What I'd do differently at production scale

- **Always-on Temporal worker.** The sync/Temporal duality exists purely because scale-to-zero economics on Cloud Run conflict with a persistent task-queue poller. A real deployment keeps one worker running and drops the sync path entirely.
- **Real auth.** The demo has no identity layer. Multi-tenant use needs user accounts, per-user API key storage, and billing.
- **PostgreSQL in demo too.** In-memory rate limiting and stateless results are fine for a showcase but break across deploys and Cloud Run instances.
- **DSPy-path eval before model migration.** The current eval benchmarks plain-text prompts, not the `QualifyLead` signature in production. Shipping the Gemini migration on promptfoo numbers alone is a gap.
- **Email sending + warming.** The approval step stops at "approved in the UI." Production needs an ESP integration, domain warming, and deliverability monitoring.
- **Multi-region.** Cloud Run is single-region. Global B2B prospecting has latency and data-residency implications worth planning early.

---

## License

Licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/).
Free for noncommercial use, study, and modification. Commercial use requires a separate license — contact klabusit@gmail.com.

© 2026 Kamil Labus
