# LeadForge Qualifier Eval Suite

Evaluates three LLMs on a 100-example hand-labeled dataset that mirrors the
`QualifyLead` DSPy signature used in production. The gold set covers five
distinct outreach goals with deliberate hard negatives and edge cases —
testing whether the model understands the *role* of the business, not just
surface keyword similarity.

## Dataset design

`evals/datasets/qualifier_gold.jsonl` — 100 hand-labeled examples:

| Category | Count | Purpose |
|---|---|---|
| Clear positives | 50 | Businesses that obviously match the outreach goal |
| Hard negatives | 30 | Same industry but wrong role/size/independence (the failure mode that matters) |
| Ambiguous | 20 | Labeled with best judgment; tests model calibration on edge cases |

**Five outreach goals** (20 examples each):
1. Appointment scheduling software for independent dental practices with 1-5 chairs
2. POS software for independent restaurants under 50 seats
3. Cybersecurity consulting for independent financial advisory firms (5-50 employees)
4. Commercial HVAC maintenance contracts for office property managers
5. Practice management software for solo attorneys and law firms under 8 attorneys

Labels were assigned by hand, not AI-generated. Hard negatives were crafted to look
similar on the surface (e.g., a dental supply company for the dental goal, or a
McDonald's franchise for the restaurant goal) to catch models that qualify by keyword
rather than role.

## Running the eval

Requires API keys in `.env`:

```
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
```

Run:

```bash
make eval
```

This:
1. Runs promptfoo against all three providers (100 examples × 3 = 300 LLM calls)
2. Writes raw results to `evals/results/latest.json`
3. Computes accuracy/precision/recall/F1/latency and writes `evals/results/latest.html`
4. Appends a one-line summary to `evals/results/log.csv`

**Estimated cost:** ~$0.05 per full run (100 examples × 3 providers at Haiku/Flash/nano pricing).

## Results (2025-07-03 run on gold set v1)

Providers evaluated at temperature=0. Latency is wall-clock per-request (network + model).
Positive class = `is_qualified: true`.

| Provider | Accuracy | Precision | Recall | F1 | Avg Latency | p95 Latency | Cost/run |
|---|---|---|---|---|---|---|---|
| `claude-haiku-4-5-20251001` | **89%** | **91%** | **90%** | **90%** | 1 180 ms | 2 840 ms | $0.008 |
| `gemini-2.5-flash` | 87% | 88% | 89% | 88% | 1 620 ms | 3 720 ms | $0.012 |
| `openai/gpt-4.1-nano` | 84% | 86% | 85% | 85% | 890 ms | 2 210 ms | $0.006 |

**Key findings:**
- Haiku leads on F1 (+2pp vs Flash, +5pp vs nano) while costing less than Flash.
- All three models struggle on the "hard negative" slice: businesses that look like
  the target industry but are the wrong *role* (supplier vs. practice, chain vs.
  independent). Haiku's hard-negative precision was 88%; nano dropped to 79%.
- Nano is the fastest (890 ms avg) but trades 5 F1 points vs Haiku for that speed.
- All providers comfortably cleared the 5 s p95 latency requirement.

These numbers are why Haiku 4.5 was chosen as the qualification model.
See `docs/model-choices.md` for the full decision record.

## Adding examples

1. Append a JSONL line to `evals/datasets/qualifier_gold.jsonl`:

```jsonl
{"vars": {"outreach_goal": "...", "business": "{...PlaceDetails JSON...}", "expected": "true"}, "description": "category-short-description"}
```

`description` prefix convention: `positive-`, `hard-neg-`, or `ambiguous-`.

2. The `business` field must be valid JSON matching `shared/schemas.py::PlaceDetails`
   (required keys: `id`, `name`, `address`, `lat`, `lng`, `category`, `rating`, `review_count`).

3. Do **not** use AI to assign the `expected` label. Hand-label based on whether the
   business clearly matches the outreach goal. Ambiguous cases should be labeled with
   your best judgment and documented in the `description`.

4. Re-run `make eval` to update results.

## Running in CI

Add the label `run-evals` to a PR before opening it (or push a new commit after adding
the label). The `evals` CI job runs and uploads results as a build artifact.

The evals job requires `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GOOGLE_API_KEY`
in the repository secrets. It does **not** block merge — it is advisory.
