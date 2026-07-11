# LeadIA — cost guardrails

Defense-in-depth against runaway spend. Three independent layers: application
limits → API-tier quotas → billing alerts. Each layer can fail independently;
only hard quotas are guaranteed to stop spend.

---

## Layer 1: Application-level caps

Controlled by env vars; applies to every maps provider.

| Guard | Env var | Default | Mechanism |
|---|---|---|---|
| Daily run cap | `DEMO_MAX_RUNS_PER_DAY` | 20 | Redis atomic INCR (or in-process counter when `RATE_LIMIT_BACKEND=memory`). Returns HTTP 429 before any LLM or Maps API calls are made. |
| Per-request lead cap | `DEMO_MAX_LEADS_SYNC` | 25 | Enforced in `pipeline.py` before the fan-out loop — limits Maps + LLM calls per run. |
| Per-IP rate limit | `DEMO_MAX_REQUESTS_PER_MINUTE` | 30 | Fixed-window middleware; only active when `DEMO_MODE=true`. |
| Search pagination ceiling | `MAPS_MAX_PAGES` | 5 | Hard cap on pages fetched per search call (5 × 20 = 100 results max), enforced inside both `GooglePlacesProvider` and `SerpAPIMapsProvider` regardless of the requested `limit`. Active in all modes, not just `DEMO_MODE`. |

These are active only when `DEMO_MODE=true`. In local development (`DEMO_MODE=false`) there are no application-level caps — the assumption is that you control the session.

---

## Layer 2: API quotas and FieldMask discipline

### SerpAPI

SerpAPI enforces hard monthly and per-minute limits at the account level. The
free tier is 250 searches/month; exceeding it returns a 429 that `SerpAPIMapsProvider`
catches as `RateLimitError` (no retry — rate limit errors are not transient).
A 24 h SQLite cache (`maps_bridge/cache.py`) reduces live call volume; evals
run against cached responses by default.

### Google Places API (New)

Google Places has no default hard cap. **Without a manually-configured quota,
a bug or unexpected traffic can spend an unbounded amount.** The three-layer
defense below addresses this.

#### 2a. FieldMask discipline — SKU tier control

Places API (New) bills at the **highest SKU tier among all requested fields in
the FieldMask**. The tiers that matter:

| Tier | Free calls/month | Triggered by |
|---|---|---|
| Pro | 5,000 | `id`, `displayName`, `formattedAddress`, `location`, `primaryType`, `types`, … |
| Enterprise | 1,000 | `rating`, `userRatingCount`, `reviews`, `currentOpeningHours`, `websiteUri`, … |

One forbidden field in the FieldMask silently upgrades **every** call in that
request type to Enterprise — 5× smaller free quota with no warning.

`GooglePlacesProvider` uses two explicit masks:

- **Text Search** (`_SEARCH_MASK`): `places.id`, `places.displayName`,
  `places.formattedAddress`, `places.location`, `places.primaryType`,
  `places.types` → **Pro tier** (5,000 free/month).
- **Place Details** (`_DETAILS_MASK`): adds `websiteUri`, `nationalPhoneNumber`,
  `regularOpeningHours` → **Advanced tier** (1,000 free/month for Details).
  `websiteUri` is required by the qualifier's `has_website` ICP criterion.
  `rating` is in the same Advanced tier for Details, but is still excluded to
  satisfy the schema invariant (`rating=None` on the google_places path).

Two sync tests in `maps_bridge/tests/test_google_places_provider.py` assert
the masks never contain `rating`, `userRatingCount`, `reviews`, or atmosphere
fields. These tests are treated as cost invariants; CI fails if they break.

#### 2b. Per-API quota (hard cap — requests fail, don't bill)

Set in **GCP Console → APIs & Services → Google Maps Platform → Quotas**:

1. Navigate to the "Places API (New)" quota page.
2. Set a daily or per-minute limit low enough to cap monthly spend at an
   acceptable level. For 200 free Text Search calls/day (≈ 6,000/month, just
   above the 5,000 free threshold): set `Text Search Requests Per Day` → 200.
3. When the quota is hit, the API returns HTTP 429. `GooglePlacesProvider`
   raises `RateLimitError` (no retry). The application returns a 503 to the
   user; no additional charges accumulate.

**This is the only mechanism that is guaranteed to stop spend.** The other
layers reduce the probability of hitting it; the quota stops the bleeding when
they don't.

Google does not set any quota by default. You must set it manually after
enabling the API. A common mistake is to rely on the billing alert (layer 3)
as a cap — it is not.

#### 2c. Budget alert (tripwire — does NOT stop spend)

Set in **GCP Console → Billing → Budgets & Alerts**:

1. Create a budget scoped to the Maps Platform APIs.
2. Set alert thresholds at 50% and 90% of the monthly budget.
3. Alerts send email (and optionally a Pub/Sub message for programmatic
   response).

**A budget alert is a notification, not a hard stop.** GCP continues to
process requests and accumulate charges after a budget alert fires. It is
useful as an early-warning tripwire — if you see a 50% alert mid-month, you
investigate before the 90% alert arrives. It does not replace the per-API
quota.

The combination of quota + alert provides defense in depth: the quota stops
spend mechanically; the alert gives you advance warning before the quota is
reached.

---

## Pagination cost multiplier

Both Maps providers used to return at most one page (~20 results) regardless
of the requested `limit`. Pagination removes that ceiling — which also
removes the accidental cost cap it provided. `MAPS_MAX_PAGES` (default 5) is
the replacement hard ceiling: 5 pages × 20 results/page = 100 results max per
search call, no matter what `limit` a caller passes.

Worst case for a single `limit=100` run, after pagination:

| | Search calls | Details calls | Total |
|---|---|---|---|
| Before pagination | 1 | 20 (hard-capped) | 21 — but never actually delivered 100 leads |
| Google Places, after | 5 (⌈100/20⌉, Pro tier) | 100 (Advanced tier) | 105 |
| SerpAPI, after | 5 | 100 | 105 |

Details calls scale 1:1 with the number of leads actually returned — that's
the real cost driver, not Search. Checked against this doc's free tiers
(Layer 2, above):

- **Google Places Details (Advanced tier, 1,000 free/month):** a single
  `limit=100` run spends 100 of that 1,000 — only **10 such runs/month**
  before Details calls start billing. Search (5,000 free/month, Pro tier) is
  not the constraint.
- **SerpAPI (250 free searches/month, shared across search + details):** a
  single `limit=100` run spends 105 of 250 — **fewer than 2.5 runs/month**
  before the entire free tier (not just Details) is exhausted.

`DEMO_MAX_LEADS_SYNC=25` (Layer 1) already keeps demo-mode runs well under
this — 25 leads needs only 2 Google Places search pages and ≤25 Details
calls. The 105-call worst case only applies to manual/non-demo invocations
that pass a high `limit` directly. Don't raise `MAPS_MAX_PAGES` above 5
without re-checking this math against current provider pricing pages first.

---

## Layer 3: LLM spend

LLM costs are per-token. LeadIA does not set hard API-level quotas for LLM
providers because token spend is bounded by the lead-cap layer (25 leads/run,
20 runs/day). Rough ceiling: 20 runs × 25 leads × ($0.00134 per 100 Haiku
qualifier calls + ~$0.005 per Sonnet email call) ≈ $0.30/day. At that scale,
a Anthropic billing alert at $10/month is sufficient as a tripwire.

---

## Summary: what actually stops spend

| Mechanism | Stops spend? | Notes |
|---|---|---|
| Application run cap | Soft — can be bypassed | Requires `DEMO_MODE=true` |
| Application lead cap | Soft — per-request | Always active |
| SerpAPI account quota | Hard | Enforced by SerpAPI |
| GCP per-API quota | **Hard** | Must be set manually — no default |
| GCP budget alert | **No** | Notification only; charges continue |
| FieldMask discipline | Reduces tier, not spend | Keeps calls cheap, not capped |
