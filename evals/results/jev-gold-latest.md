# Jev qualifier spike — latest run

**Run:** 2026-09-22T08:03:59Z  
**Requested model:** `jev-latest`  
**Resolved model:** `jev-1.13.0`  
**Headline threshold:** 0.50 (`noul >= threshold`)  
**Dataset:** `evals/datasets/qualifier_gold.jsonl` (100 examples)  
**Eval type:** TypeSafe noul on goal + PlaceDetails. Not production `qualify_lead()`. See issue #103.

| Model | Accuracy | Precision | Recall | F1 | Avg latency | p95 latency | Tokens in/out |
|---|---|---|---|---|---|---|---|
| `jev-1.13.0` | 87.0% | 92.6% | 84.7% | 88.5% | 310 ms | 386 ms | 51916 / 2000 |

## Slices

| Slice | N | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|
| `positive` | 50 | 88.0% | 100.0% | 88.0% | 93.6% |
| `hard` | 30 | 100.0% | n/a | n/a | n/a |
| `ambiguous` | 20 | 65.0% | 60.0% | 66.7% | 63.2% |

## Threshold sweep (diagnostic)

Computed from the stored probabilities. The headline above stays at the precommitted threshold; this table is not a tuned result.

| Threshold | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| 0.5 | 87.0% | 92.6% | 84.7% | 88.5% |
| 0.6 | 86.0% | 92.5% | 83.1% | 87.5% |
| 0.7 | 81.0% | 93.5% | 72.9% | 81.9% |
| 0.8 | 55.0% | 88.9% | 27.1% | 41.6% |
| 0.9 | 41.0% | n/a | 0.0% | n/a |

API errors (counted as not qualified): 0
