# Model Choices

Decisions are backed by `evals/` — run `make eval` to reproduce numbers.

---

## Lead Qualification — `claude-haiku-4-5-20251001`

**Task:** `QualifyLead` DSPy signature: given an outreach goal and a serialized
`PlaceDetails`, return `is_qualified` (bool), `score` (0–1), `reasoning` (str),
`icp_fit` (dict of bool criteria).

**Candidates evaluated** on `evals/datasets/qualifier_gold.jsonl`
(100 hand-labeled examples, five outreach goals):

| Provider | Accuracy | Precision | Recall | F1 | p95 Latency | Cost/100 calls |
|---|---|---|---|---|---|---|
| `claude-haiku-4-5-20251001` ✅ | **89%** | **91%** | **90%** | **90%** | 2 840 ms | $0.008 |
| `gemini-2.5-flash` | 87% | 88% | 89% | 88% | 3 720 ms | $0.012 |
| `openai/gpt-4.1-nano` | 84% | 86% | 85% | 85% | 2 210 ms | $0.006 |

**Decision: Haiku 4.5.**

- **Best F1** (+2 pp vs Flash, +5 pp vs nano). F1 matters more than raw accuracy
  here because false positives waste email generation budget and false negatives
  lose leads; we need both precision and recall.
- **Hard-negative precision** (the failure mode that costs money): Haiku 88%,
  nano 79%. Haiku correctly rejects more businesses that look like the target
  industry but are the wrong *role* — e.g., a dental supply company when looking
  for dental practices.
- **Cost vs. Flash**: Haiku is 33% cheaper per 100 calls at this task size.
- **Latency**: All three clear the 5 s p95 requirement. Nano is faster (2 210 ms)
  but the 5 F1 point gap isn't worth trading for the typical qualification batch.
- **JSON compliance**: Haiku 4.5 reliably emits valid JSON at temperature=0 for
  this schema size. No parse failures observed in the eval run.

**Trade-off accepted:** If future scale requires sub-500 ms p95, revisit nano
with a refined DSPy program (few-shot examples for the hard-negative categories).

---

## Email Generation — `claude-sonnet-4-6`

**Task:** `GenerateEmail` DSPy signature: produce `subject`, `body`, and
`personalization_hooks` for a qualified lead.

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

**When to revisit:** If email generation becomes a throughput bottleneck, run a
human eval comparing Haiku-generated vs Sonnet-generated emails using the
approval rate as the outcome metric.

---

## Fallback / Router

`ai_worker/llm_router.py` routes to OpenAI or Gemini if the Anthropic API is
unavailable (5xx or rate limit). Fallback is OpenAI GPT-4.1 for qualification
(acceptable 84% F1) and Gemini 2.5 Flash for email. Fallback is never preferred —
it is strictly a circuit-breaker path.
