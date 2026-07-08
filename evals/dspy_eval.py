"""DSPy-path qualifier eval — runs the ACTUAL production qualification path.

Loads the same 100-example gold set used by the plain-text promptfoo eval
and runs each example through qualify_lead() — the real production function —
using the chosen model at temperature=0 for reproducibility.

Usage:
    make eval-dspy                                      # Haiku (default)
    make eval-dspy ARGS="--model gemini/gemini-2.5-flash"
    QUALIFIER_MODEL=gemini/gemini-2.5-flash make eval-dspy

Estimated cost per 100-call run:
    anthropic/claude-haiku-4-5-20251001  ~$0.05-$0.10
    gemini/gemini-2.5-flash              ~$0.01-$0.04

Run from repo root so ai_worker/ and shared/ are importable:
    PYTHONPATH=. uv run python evals/dspy_eval.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import dspy

REPO_ROOT = Path(__file__).parent.parent
GOLD_PATH = REPO_ROOT / "evals" / "datasets" / "qualifier_gold.jsonl"
RESULTS_DIR = REPO_ROOT / "evals" / "results"

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--model",
        default=os.environ.get("QUALIFIER_MODEL", _DEFAULT_MODEL),
        help="LiteLLM model string (default: %(default)s)",
    )
    return p.parse_args()


class _Metrics:
    def __init__(self) -> None:
        self.tp = self.fp = self.tn = self.fn = 0
        self.errors = 0
        self.latencies: list[float] = []
        self.total_cost: float = 0.0

    def add(
        self,
        expected: bool,
        predicted: bool | None,
        latency_ms: float,
        cost: float,
    ) -> None:
        self.latencies.append(latency_ms)
        self.total_cost += cost
        if predicted is None:
            self.errors += 1
            if expected:
                self.fn += 1
            else:
                self.tn += 1
            return
        if expected and predicted:
            self.tp += 1
        elif expected and not predicted:
            self.fn += 1
        elif not expected and predicted:
            self.fp += 1
        else:
            self.tn += 1

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.n if self.n else 0.0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def latency_avg(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    @property
    def latency_p95(self) -> float:
        if not self.latencies:
            return 0.0
        s = sorted(self.latencies)
        idx = math.ceil(0.95 * len(s)) - 1
        return s[max(0, idx)]


def _lm_cost_since(lm: dspy.LM, before_len: int) -> float:
    """Sum cost of LM history entries added since before_len."""
    history: list[dict[str, object]] = getattr(lm, "history", None) or []
    total = 0.0
    for entry in history[before_len:]:
        c = entry.get("cost") or 0.0
        if isinstance(c, (int, float)) and c > 0:
            total += float(c)
    return total


def main() -> None:
    args = _parse_args()
    model: str = args.model

    # Import production code — must be on PYTHONPATH (repo root).
    try:
        from ai_worker.dspy_engine import qualify_lead
        from shared.schemas import PlaceDetails
    except ImportError as exc:
        sys.exit(
            f"Import error: {exc}\n"
            "Run from repo root: PYTHONPATH=. uv run python evals/dspy_eval.py"
        )

    examples = [json.loads(line) for line in GOLD_PATH.read_text().splitlines() if line.strip()]

    print("DSPy-path qualifier eval")
    print(f"Model   : {model}")
    print(f"Dataset : evals/datasets/qualifier_gold.jsonl  ({len(examples)} examples)")
    print()

    lm = dspy.LM(model=model, temperature=0)
    metrics = _Metrics()
    raw_rows: list[dict[str, object]] = []
    run_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    for i, ex in enumerate(examples, 1):
        vars_ = ex["vars"]
        outreach_goal: str = vars_["outreach_goal"]
        place = PlaceDetails.model_validate_json(vars_["business"])
        expected = vars_["expected"].lower() == "true"

        history_before = len(getattr(lm, "history", None) or [])
        t0 = time.perf_counter()
        predicted: bool | None
        try:
            verdict = qualify_lead(outreach_goal=outreach_goal, place=place, lm=lm)
            predicted = verdict.is_qualified
        except Exception as exc:
            print(f"  [{i:3d}] ERROR: {exc}", file=sys.stderr)
            predicted = None

        latency_ms = (time.perf_counter() - t0) * 1000
        cost = _lm_cost_since(lm, history_before)

        metrics.add(expected, predicted, latency_ms, cost)
        raw_rows.append(
            {
                "description": ex.get("description", ""),
                "outreach_goal": outreach_goal,
                "business_id": json.loads(vars_["business"]).get("id", ""),
                "expected": expected,
                "predicted": predicted,
                "latency_ms": round(latency_ms, 1),
                "cost_usd": round(cost, 6),
            }
        )

        if i % 10 == 0:
            print(
                f"  {i:3d}/100  acc={metrics.accuracy:.1%}  "
                f"f1={metrics.f1:.1%}  avg={metrics.latency_avg:.0f}ms"
            )

    # --- Summary table ---
    short = model.split("/", 1)[-1] if "/" in model else model
    print()
    print(
        f"{'Model':<42} {'Acc':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} "
        f"{'AvgMs':>7} {'p95Ms':>7} {'Cost':>9} {'Err':>4}"
    )
    print("-" * 97)
    print(
        f"{short:<42} {metrics.accuracy:>6.1%} {metrics.precision:>6.1%} "
        f"{metrics.recall:>6.1%} {metrics.f1:>6.1%} {metrics.latency_avg:>7.0f} "
        f"{metrics.latency_p95:>7.0f} ${metrics.total_cost:>8.4f} {metrics.errors:>4}"
    )
    print()

    # --- Write results ---
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    safe_model = model.replace("/", "-").replace(":", "-")
    json_path = RESULTS_DIR / f"dspy-path-{safe_model}-{run_ts[:10]}.json"
    json_path.write_text(
        json.dumps(
            {
                "eval_type": "dspy-path",
                "model": model,
                "run_ts": run_ts,
                "n": metrics.n,
                "accuracy": round(metrics.accuracy, 4),
                "precision": round(metrics.precision, 4),
                "recall": round(metrics.recall, 4),
                "f1": round(metrics.f1, 4),
                "latency_avg_ms": round(metrics.latency_avg, 1),
                "latency_p95_ms": round(metrics.latency_p95, 1),
                "cost_usd": round(metrics.total_cost, 6),
                "errors": metrics.errors,
                "rows": raw_rows,
            },
            indent=2,
        )
    )
    print(f"Results  → {json_path.relative_to(REPO_ROOT)}")

    # Append to DSPy-specific log (separate from promptfoo log.csv format).
    log_path = RESULTS_DIR / "log-dspy.csv"
    write_header = not log_path.exists()
    with log_path.open("a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(
                [
                    "timestamp",
                    "eval_type",
                    "model",
                    "n",
                    "accuracy",
                    "precision",
                    "recall",
                    "f1",
                    "latency_avg_ms",
                    "latency_p95_ms",
                    "cost_usd",
                    "errors",
                ]
            )
        w.writerow(
            [
                run_ts,
                "dspy-path",
                model,
                metrics.n,
                f"{metrics.accuracy:.4f}",
                f"{metrics.precision:.4f}",
                f"{metrics.recall:.4f}",
                f"{metrics.f1:.4f}",
                f"{metrics.latency_avg:.1f}",
                f"{metrics.latency_p95:.1f}",
                f"{metrics.total_cost:.6f}",
                metrics.errors,
            ]
        )
    print(f"CSV log  → {log_path.relative_to(REPO_ROOT)}")

    # Markdown summary (overwritten each run; raw JSON has the full history).
    md_path = RESULTS_DIR / "dspy-path-latest.md"
    md_path.write_text(
        f"# DSPy-path qualifier eval — latest run\n\n"
        f"**Run:** {run_ts}  \n"
        f"**Model:** `{model}`  \n"
        f"**Dataset:** `evals/datasets/qualifier_gold.jsonl` "
        f"(100 hand-labeled examples, 5 outreach goals)  \n"
        f"**Eval type:** DSPy-path — production `qualify_lead()` function, "
        f"not the plain-text `qualify.txt` prompt used by `make eval`\n\n"
        f"| Model | Accuracy | Precision | Recall | F1 | Avg latency | p95 latency | Cost/100 |\n"
        f"|---|---|---|---|---|---|---|---|\n"
        f"| `{model}` | {metrics.accuracy:.1%} | {metrics.precision:.1%} "
        f"| {metrics.recall:.1%} | {metrics.f1:.1%} "
        f"| {metrics.latency_avg:.0f} ms | {metrics.latency_p95:.0f} ms "
        f"| ${metrics.total_cost:.4f} |\n\n"
        f"Temperature=0 for reproducibility.  \n"
        f"Errors (parse/API failures counted as false predictions): {metrics.errors}\n"
    )
    print(f"MD summary → {md_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
