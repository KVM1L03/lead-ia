# DSPy-path qualifier eval — latest run

**Run:** 2026-07-08T09:52:38Z  
**Model:** `anthropic/claude-haiku-4-5-20251001`  
**Dataset:** `evals/datasets/qualifier_gold.jsonl` (100 hand-labeled examples, 5 outreach goals)  
**Eval type:** DSPy-path — production `qualify_lead()` function, not the plain-text `qualify.txt` prompt used by `make eval`

| Model | Accuracy | Precision | Recall | F1 | Avg latency | p95 latency | Cost/100 |
|---|---|---|---|---|---|---|---|
| `anthropic/claude-haiku-4-5-20251001` | 81.0% | 88.5% | 78.0% | 82.9% | 1936 ms | 2810 ms | $0.1339 |

Temperature=0 for reproducibility.  
Errors (parse/API failures counted as false predictions): 0
