# Engineering decisions

The trade-offs behind LeadIA — what each choice gained and what it **traded away**.
Back to the [README](../README.md).

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

**Traded away in the demo:** crash recovery, per-step retry, replay, real-time workflow visibility, and Backfill ([ADR 0001](./adr/0001-backfill-temporal-only.md)).

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
<summary><b>⚖️ Three-way split: Jev decides, Haiku explains, Sonnet writes</b></summary>

Qualification runs on every scraped place; email generation runs only on qualified leads (~40–70% of results). As of [#105](https://github.com/KVM1L03/lead-ia/issues/105), the qualify step itself is two-stage: TypeSafe Jev (`jev-1.13.0`) makes the `is_qualified` yes/no call, and Haiku 4.5 is only invoked — on leads Jev passes — to write the one-sentence `reasoning` that the email draft and CSV export read. See [ADR 0006](adr/0006-jev-for-qualification-decision.md).

**Traded away:** simplicity (one model everywhere), cost predictability, and a single vendor for the qualify step (Jev is a second API key, `TYPESAFE_API_KEY`).

**Why:** Jev beat the production DSPy-path Haiku qualifier on the gold set — 88.5% F1 at 310 ms vs 82.9% F1 at 1936 ms — and rejected all 30 hard negatives, so it now owns the decision. Haiku stays for reasoning quality; Sonnet still writes email copy, and only runs on the qualified subset. GPT-4.1-nano stays as a last-resort circuit breaker only (2% recall makes it useless for qualification in practice).

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

Full suite, gold dataset, and metric scripts: [`evals/`](../evals/).

---

## What I'd do differently at production scale

- **Always-on Temporal worker.** The sync/Temporal duality exists purely because scale-to-zero economics conflict with a persistent task-queue poller. A real deployment keeps one worker up and drops the sync path — which also gives the demo Backfill.
- **Real auth.** No identity layer today. Multi-tenant use needs accounts, per-user encrypted key storage, and billing.
- **Postgres + Redis in the demo too.** In-memory rate limiting and stateless results are fine for a showcase but break across deploys and instances.
- **Close the Gemini eval gate.** The proxy promptfoo eval isn't sufficient; the DSPy-path numbers for Gemini are still missing.
- **Email sending + warming.** Approval produces a CSV; production needs an ESP integration, domain warming, deliverability monitoring, and unsubscribe handling.
- **Multi-region.** Cloud Run is single-region. Global prospecting has latency and data-residency implications worth planning early.

## Deployment

Live demo: **Vercel** (frontend) + **Cloud Run** (backend). The backend is one service (`lead-api`) running `EXECUTION_MODE=sync`, `MAPS_TRANSPORT=inline`, and in-process rate limiting — `maps_bridge` inlined in the same container, no sidecar. [`infra/terraform/`](../infra/terraform/) codifies the IaC foundation (VPC, Artifact Registry, API enablement); the live service ships via `gcloud`. The VPC connector, Cloud SQL, and Redis are defined but not provisioned — the demo runs without them. Full audit: [`docs/twelve-factor-audit.md`](./twelve-factor-audit.md).
