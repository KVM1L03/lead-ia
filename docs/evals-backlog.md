# Evals — backlog & checklist

Living checklist of eval-suite and model-validation work **not yet implemented**.
Check items off as they land; link PRs inline when useful.

**Current baseline (2026-07-03):** plain-prompt qualifier eval via promptfoo
(`make eval`), 100-example gold set, three providers, post-processing in
`evals/scripts/metrics.py`. Decision record: [`model-choices.md`](model-choices.md).

---

## Eval quality & coverage

These close the gap between “good portfolio demo” and “production-faithful
benchmark.”

- [ ] **Sync `evals/README.md`** — results table and findings must match
  [`model-choices.md`](model-choices.md) (stale ~89% Haiku run vs latest ~78% /
  Gemini 83% F1).
- [ ] **Slice metrics in `metrics.py`** — F1 / precision / recall broken down by:
  - [ ] category: clear positive / hard negative / ambiguous (`description` prefix
        in gold set)
  - [ ] outreach goal (5 goals × 20 examples)
  - [ ] provider comparison per slice (surface where nano/Haiku/Gemini diverge)
- [ ] **DSPy qualifier eval** — run `QualifyLead` via `dspy.Predict` +
  `get_lm("qualifier")` on `qualifier_gold.jsonl`; compare to promptfoo baseline.
  Production path, not plain `qualify.txt`.
- [ ] **Multi-run stability** — document or automate 3× `--no-cache` runs; report
  mean ± std for F1 (nano showed 0–3% F1 variance between runs).
- [ ] **Regression thresholds** — optional CI fail (or PR comment) when F1 drops
  > N pp vs committed baseline JSON; today `run-evals` is advisory only.
- [ ] **Email eval (automated)** — `evals/datasets/email_gold.jsonl` + promptfoo
  rubric: schema, max length, mentions business name, no spam phrases.
- [ ] **Email eval (human)** — blind Sonnet vs Gemini on ~20 leads; approval
  rate, edit distance, “would send as-is” score. See email section in
  [`model-choices.md` § Migration plan](model-choices.md#migration-plan-gemini-primary).

---

## Cost & metrics tooling

Gemini cost is token-estimated today; other gaps below.

- [ ] **Centralize pricing** — single source (e.g. `evals/pricing.yaml` or
  constants module) with model id → input/output $/M and effective date; used by
  `metrics.py` instead of hardcoded Flash rates.
- [ ] **Fixture test for total cost** — load a trimmed `latest.json` snippet;
  assert aggregated Gemini cost matches expected sum (no live API).
- [ ] **Cached-token handling** — if promptfoo exposes cache read tokens separately,
  apply discounted rate or document exclusion.
- [ ] **Cost column consistency** — ensure Haiku/OpenAI use promptfoo `cost` when
  present; document when each provider is estimated vs reported in HTML footnote.

---

## CI & ops

- [ ] **CI eval env parity** — `.github/workflows/ci.yml` evals job should mirror
  local `make eval` (`--env-file` / secrets injection pattern).
- [ ] **Committed baseline artifact** — pin `evals/results/baseline.json` (or
  metrics summary only) updated intentionally on gold-set or prompt changes.
- [ ] **PR template smoke** — checklist row for “model router / eval config changed”.
- [ ] **Eval cost budget note** — document expected ~$0.15/run (3×100 calls) in
  README and when to use `run-evals` label.

---

## Production alignment (Gemini migration)

Router and env flips are **blocked** until the relevant boxes are checked.
Full detail and rollback env vars: [`model-choices.md` § Migration plan](model-choices.md#migration-plan-gemini-primary).

### Preconditions

- [ ] `GOOGLE_API_KEY` required in `.env.example`, bootstrap, CI secrets docs
- [ ] Gemini `thinkingBudget: 0` in LiteLLM/DSPy production config
- [ ] Haiku fallback: confirm DSPy tolerates occasional ` ```json ` fences

### Qualifier flip

- [ ] DSPy eval shows Gemini ≥ Haiku (+ agreed margin)
- [ ] End-to-end Temporal smoke + Langfuse trace review
- [ ] Swap `_DEFAULTS["qualifier"]` in `ai_worker/llm_router.py`
- [ ] Fix `test_llm_router.py` env isolation (keys in `.env` widen fallback chain)

### Email flip

- [ ] Human eval complete (Sonnet vs Gemini)
- [ ] Langfuse token/cost sample on 10+ real drafts
- [ ] Swap `_DEFAULTS["email"]`
- [ ] Approval UI smoke (5 drafts)

### After both validated

- [ ] Update `model-choices.md` — Gemini primary, Anthropic fallback
- [ ] Update `CLAUDE.md` env table

---

## Suggested order

1. Docs sync + slice metrics (cheap, high signal for reviewers).
2. DSPy qualifier eval + pricing centralization.
3. Regression baseline + optional CI threshold.
4. Gemini production preconditions → qualifier router flip → email human eval → email flip.

---

## Out of scope (explicit)

Not planned for this milestone board — resist unless requirements change:

- Multi-tenant eval isolation
- Online / continuous eval in production
- Auto-labeling gold set with LLM
- Promptfoo cloud sharing (gold set stays local: `sharing: false`)
