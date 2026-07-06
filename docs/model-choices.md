# Model Choices

Decisions are backed by `evals/` — run `make eval` to reproduce numbers.

---

## Lead Qualification — `claude-haiku-4-5-20251001`

**Task:** `QualifyLead` DSPy signature: given an outreach goal and a serialized
`PlaceDetails`, return `is_qualified` (bool), `score` (0–1), `reasoning` (str),
`icp_fit` (dict of bool criteria).

**Candidates evaluated** on `evals/datasets/qualifier_gold.jsonl`
(100 hand-labeled examples, five outreach goals). Eval uses the plain-text prompt
in `evals/prompts/qualify.txt` (mirrors the DSPy signature, not DSPy itself).

**Latest run:** 2026-07-03 (`eval-4DM`), `--no-cache`, temperature=0.
Gemini requires `thinkingBudget: 0` in `evals/promptfooconfig.yaml` — otherwise
2.5 Flash burns the output token budget on internal reasoning and returns
truncated JSON.

| Provider | Accuracy | Precision | Recall | F1 | p95 Latency | Cost/100 calls |
|---|---|---|---|---|---|---|
| `gemini-2.5-flash` | **82%** | **94%** | **75%** | **83%** | 1 212 ms | **~$0.032** ‡ |
| `claude-haiku-4-5-20251001` ✅ | 77% | 89% | 70% | 78% | 2 492 ms | $0.095 |
| `openai/gpt-4.1-nano` | 42% | 100% | 2% | 3% | 1 726 ms | $0.007 |

‡ Promptfoo reports `$0` for the Google provider — cost estimated from token counts in
the 2026-07-03 full run (`eval-4DM`, 100 calls: 37 016 input + 8 279 output tokens)
and confirmed by a 10-call sample (`eval-0Yz`: 3 747 + 848 tokens, ×10 ≈ $0.032).
Google list price for `gemini-2.5-flash`: **$0.30 / 1M input**, **$2.50 / 1M output**
([Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)). With
`thinkingBudget: 0`, no reasoning tokens are billed.

**Decision (today): Haiku 4.5 (primary), Gemini 2.5 Flash (first fallback).**

**Target (planned):** Gemini 2.5 Flash primary for **both** qualifier and email.
See [Migration plan: Gemini primary](#migration-plan-gemini-primary) — not implemented yet.

Gemini leads the 2026-07-03 qualifier eval on F1 (+5 pp), precision (+5 pp), recall
(+5 pp), latency, and **cost** (~$0.032 vs Haiku ~$0.095 per 100 calls). Haiku
remains primary **for now** because:

- **Anthropic-first stack** — qualifier (Haiku) and email (Sonnet) share one
  vendor, one API key, and one Langfuse trace family; switching primary would
  split the pipeline across providers for a ~5 pp F1 gain on a plain prompt eval.
- **Eval ≠ production path** — production uses DSPy `QualifyLead`; these numbers
  benchmark a text prompt only. Revisit primary if a DSPy-backed eval shows the
  same gap.
- **Conservative prompt shaves recall for all models** — the rule *"is_qualified
  is true ONLY if clearly and unambiguously matches"* plus missing size fields in
  `PlaceDetails` drives false negatives across providers (Haiku recall 70%,
  Gemini 75%). Absolute F1 is lower than the initial 2025-07-03 benchmark (~90%);
  relative ranking matters more than the old absolute targets.

**Why not nano:** GPT-4.1 nano is extremely conservative (recall 2%, F1 3%) —
it almost never emits `is_qualified: true`. Unusable as qualifier; keep only as
last-resort circuit breaker.

**JSON compliance:** All three providers emit valid JSON at temperature=0 after
the eval config fixes (markdown fence strip for Haiku, `thinkingBudget: 0` for
Gemini). Zero parse failures in the 2026-07-03 run.

**Trade-off accepted (interim):** Keep Haiku primary until the migration checklist
below is complete. Do not flip `llm_router.py` on promptfoo numbers alone.

---

## Email Generation — `claude-sonnet-4-6`

**Task:** `GenerateEmail` DSPy signature: produce `subject`, `body`, and
`personalization_hooks` for a qualified lead.

**Decision (today):** Sonnet 4.6 primary, Gemini 2.5 Flash first fallback.

**Target (planned):** Gemini 2.5 Flash primary for email as well (same migration
plan). Sonnet was chosen before any Gemini email benchmark existed.

No quantitative eval yet (email quality requires human evaluation). Sonnet 4.6
was chosen because:

- Email body quality is the primary impression for the human approver. Sonnet
  produces noticeably more specific, less generic outreach copy than Haiku at
  this task.
- Cost amortizes over the pipeline: only qualified leads reach this step, so
  volume is capped by the qualifier's recall (~10–20% of scraped businesses
  in practice).
- Latency is not critical here — the email sits in the approval queue until
  a human acts on it.

**When to revisit:** Covered by the migration plan below — human approval-rate
eval comparing Sonnet vs Gemini before promoting Gemini for email.

---

## Fallback / Router

`ai_worker/llm_router.py` routes to alternate providers if the primary is
unavailable (5xx or rate limit).

**Today** — chain for `qualifier`:

1. `anthropic/claude-haiku-4-5-20251001` (primary)
2. `gemini/gemini-2.5-flash` (first fallback — 83% F1 in latest eval)
3. `openai/gpt-4.1-nano` (last resort — 3% F1; JSON-valid but over-rejects)

**Today** — chain for `email`:

1. `anthropic/claude-sonnet-4-6` (primary)
2. `gemini/gemini-2.5-flash`
3. `openai/gpt-4.1-nano`

**Target** — both roles: Gemini 2.5 Flash primary, Anthropic models first
fallback, nano last resort. See migration plan.

Fallback is never preferred — it is strictly a circuit-breaker path. After the
2026-07-03 eval, Gemini is the only fallback with qualification quality close to
Haiku; nano should not be relied on for qualification accuracy.

---

## Migration plan: Gemini primary

**Goal:** Make `gemini/gemini-2.5-flash` the primary model for **qualifier** and
**email** in `ai_worker/llm_router.py`, with Anthropic (Haiku / Sonnet) as first
fallback. Motivation: lower cost (~3× vs Haiku on qualifier eval), lower latency,
and higher F1/precision on the plain-prompt gold set (2026-07-03).

**Status:** Planned — **no router or env changes merged yet.**

### Preconditions (before any code flip)

- [ ] **`GOOGLE_API_KEY` required** — add to `.env.example`, bootstrap docs, and
  CI secrets notes; today it is optional (fallback only).
- [ ] **Gemini `thinkingBudget: 0` in production** — mirror
  `evals/promptfooconfig.yaml` in LiteLLM/DSPy kwargs for `gemini/gemini-2.5-flash`
  so JSON is not truncated (same bug as pre-fix eval).
- [ ] **Haiku markdown handling** — if Anthropic stays as fallback, confirm DSPy
  adapter tolerates occasional ` ```json ` fences from Haiku on fallback path.

### Qualifier — testing TODO

Plain-prompt eval (`make eval`) favors Gemini; production uses DSPy. Do **not**
promote on promptfoo alone.

- [ ] **DSPy qualifier eval** — extend `evals/` (or a one-off script) to run
  `QualifyLead` via `dspy.Predict` + `get_lm("qualifier")` on
  `qualifier_gold.jsonl`; compare F1 to promptfoo baseline (Gemini ≥ Haiku + margin).
- [ ] **End-to-end smoke** — one full Temporal workflow with live API keys,
  Langfuse trace review (latency, JSON parse errors, qualification counts).
- [ ] **Router change** — swap primary in `_DEFAULTS["qualifier"]`:
  `gemini/gemini-2.5-flash` → `anthropic/claude-haiku-4-5-20251001` → nano.
- [ ] **Update tests** — `tests/test_llm_router.py` expects Haiku primary today;
  adjust after flip.
- [ ] **Re-run `make eval`** after router change is **not** sufficient proof;
  DSPy eval + smoke are the merge gate.

### Email — testing TODO

No automated quality benchmark exists yet. Gemini primary for email is **higher
risk** than qualifier (subjective copy quality, approver is the judge).

- [ ] **Human eval design** — e.g. 20 qualified leads × 2 providers (Sonnet vs
  Gemini), blind review: approval rate, edit distance, “would send as-is” score.
- [ ] **Promptfoo or gold set (optional)** — small `evals/datasets/email_gold.jsonl`
  with rubric assertions (length, no spam phrases, mentions business name).
- [ ] **Cost/latency check** — email volume is lower than qualify; still log token
  usage in Langfuse for 10+ real drafts before flip.
- [ ] **Router change** — swap primary in `_DEFAULTS["email"]`:
  `gemini/gemini-2.5-flash` → `anthropic/claude-sonnet-4-6` → nano.
- [ ] **UI smoke** — approval screen: read 5 Gemini-generated drafts for tone and
  factual grounding vs Sonnet baseline.

### Docs & ops (after both roles validated)

- [ ] Update this file: move “Decision (today)” → historical note; mark Gemini primary.
- [ ] Update `CLAUDE.md` env table — `GOOGLE_API_KEY` required for production.
- [ ] Update `evals/README.md` results table if numbers change under DSPy eval.
- [ ] Manual smoke checklist in PR template for model-router changes.

### Rollback

Keep `QUALIFIER_MODEL` / `EMAIL_MODEL` env overrides (already supported in
`llm_router.py`) documented so ops can revert to Anthropic primary without redeploy:

```bash
QUALIFIER_MODEL=anthropic/claude-haiku-4-5-20251001
EMAIL_MODEL=anthropic/claude-sonnet-4-6
```

### Suggested order of work

1. Production Gemini config (`thinkingBudget: 0`) + required `GOOGLE_API_KEY`.
2. DSPy qualifier eval → router flip for **qualifier only** → smoke → PR.
3. Human email eval → router flip for **email** → UI smoke → PR (separate PR).
4. Update decision record and demote Anthropic to fallback in docs.

**Do not merge router changes until the relevant checklist section is complete.**

---

## Eval backlog

> Moved from `docs/evals-backlog.md` — living checklist of eval-suite and model-validation work not yet implemented.

**Current baseline (2026-07-03):** plain-prompt qualifier eval via promptfoo (`make eval`), 100-example gold set, three providers. See [Migration plan: Gemini primary](#migration-plan-gemini-primary) for the merge gate.

### Eval quality & coverage

- [ ] **Sync `evals/README.md`** — results table must match this file (stale ~89% Haiku vs latest ~78% / Gemini 83% F1).
- [ ] **Slice metrics in `metrics.py`** — F1 / precision / recall by: category (positive / negative / ambiguous), outreach goal (5 × 20), provider comparison per slice.
- [ ] **DSPy qualifier eval** — run `QualifyLead` via `dspy.Predict` + `get_lm("qualifier")` on `qualifier_gold.jsonl`; compare to promptfoo baseline. Production path, not plain `qualify.txt`.
- [ ] **Multi-run stability** — 3× `--no-cache` runs; report mean ± std for F1 (nano showed variance).
- [ ] **Regression thresholds** — optional CI fail when F1 drops >N pp vs committed baseline JSON.
- [ ] **Email eval (automated)** — `evals/datasets/email_gold.jsonl` + rubric: schema, max length, mentions business name, no spam phrases.
- [ ] **Email eval (human)** — blind Sonnet vs Gemini on ~20 leads; approval rate, edit distance, "would send as-is" score.

### Cost & metrics tooling

- [ ] **Centralize pricing** — `evals/pricing.yaml` (model id → $/M) used by `metrics.py` instead of hardcoded Flash rates.
- [ ] **Fixture test for total cost** — load trimmed `latest.json`; assert aggregated cost matches expected sum.
- [ ] **Cached-token handling** — document or apply discounted rate for cache read tokens.

### CI & ops

- [ ] **CI eval env parity** — evals CI job should mirror local `make eval` (secrets injection pattern).
- [ ] **Committed baseline artifact** — pin `evals/results/baseline.json` updated intentionally on gold-set or prompt changes.
- [ ] **Eval cost budget note** — document expected ~$0.15/run in README and when to use `run-evals` label.
