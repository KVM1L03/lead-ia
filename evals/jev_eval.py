"""Jev qualifier spike — score jev-latest on the hand-labeled gold set.

Does not call production ``qualify_lead``. One noul per example; the headline
decision is noul >= 0.5. A threshold sweep is written beside the result and
is not used to choose the headline.

Usage:
    make eval-jev
    PYTHONPATH=. uv run python evals/jev_eval.py --limit 5

Requires TYPESAFE_API_KEY in the environment or in .env.
Issue: https://github.com/KVM1L03/lead-ia/issues/103
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jev_qualify import (  # noqa: E402
    DEFAULT_THRESHOLD,
    QUESTION_NAME,
    Confusion,
    api_key_from,
    apply_env_file,
    format_rate,
    outcome,
    percentile_95,
    qualification_question,
    qualification_state,
    qualifies,
    slice_name,
    threshold_sweep,
)
from typesafe_sdk import TypeSafeClient  # noqa: E402

from shared.schemas import PlaceDetails  # noqa: E402

GOLD_PATH = REPO_ROOT / "evals" / "datasets" / "qualifier_gold.jsonl"
RESULTS_DIR = REPO_ROOT / "evals" / "results"
_DEFAULT_MODEL = "jev-latest"


@dataclass(frozen=True)
class Row:
    description: str
    outreach_goal: str
    business_id: str
    expected: bool
    noul: float | None
    predicted: bool | None
    latency_ms: float
    input_tokens: int
    output_tokens: int
    model: str
    error: str | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", default=os.environ.get("TYPESAFE_DEFAULT_MODEL", _DEFAULT_MODEL))
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="Headline yes/no cutoff (default: %(default)s). The sweep still covers 0.5-0.9.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Score only the first N examples.")
    return parser.parse_args()


def _load_examples(limit: int | None) -> list[dict[str, object]]:
    examples = [json.loads(line) for line in GOLD_PATH.read_text().splitlines() if line.strip()]
    if limit is None:
        return examples
    if limit < 1:
        sys.exit("--limit must be at least 1")
    return examples[:limit]


def _score(
    client: TypeSafeClient, example: dict[str, object], *, model: str, threshold: float
) -> Row:
    vars_ = example["vars"]
    if not isinstance(vars_, dict):
        raise TypeError("gold example vars must be an object")
    outreach_goal = str(vars_["outreach_goal"])
    business_raw = vars_["business"]
    if not isinstance(business_raw, str):
        raise TypeError("gold example business must be a JSON string")
    description = str(example.get("description", ""))
    expected = str(vars_["expected"]).lower() == "true"
    place = PlaceDetails.model_validate_json(business_raw)

    started = time.perf_counter()
    try:
        response = client.system_one(
            qualification_state(outreach_goal, place),
            {QUESTION_NAME: qualification_question()},
            model=model,
        )
        noul = response.nouls[QUESTION_NAME].noul
        predicted = qualifies(noul, threshold=threshold)
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return Row(
            description=description,
            outreach_goal=outreach_goal,
            business_id=place.id,
            expected=expected,
            noul=None,
            predicted=None,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            model=model,
            error=f"{type(exc).__name__}: {exc}",
        )

    latency_ms = (time.perf_counter() - started) * 1000
    usage = response.usage
    return Row(
        description=description,
        outreach_goal=outreach_goal,
        business_id=place.id,
        expected=expected,
        noul=noul,
        predicted=predicted,
        latency_ms=latency_ms,
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        model=response.model,
        error=None,
    )


def _confusion(rows: list[Row]) -> Confusion:
    total = Confusion()
    for row in rows:
        total += outcome(row.expected, row.predicted)
    return total


def _pct(value: float) -> str:
    return format_rate(value, defined=True)


def _precision(confusion: Confusion) -> str:
    return format_rate(confusion.precision, defined=(confusion.tp + confusion.fp) > 0)


def _recall(confusion: Confusion) -> str:
    return format_rate(confusion.recall, defined=(confusion.tp + confusion.fn) > 0)


def _f1(confusion: Confusion) -> str:
    defined = (confusion.tp + confusion.fp) > 0 and (confusion.tp + confusion.fn) > 0
    return format_rate(confusion.f1, defined=defined)


def _write_reports(rows: list[Row], *, requested_model: str, threshold: float, run_ts: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    headline = _confusion(rows)
    latencies = [row.latency_ms for row in rows]
    scored = [(row.expected, row.noul) for row in rows if row.noul is not None]
    sweep = threshold_sweep(scored)
    resolved = sorted({row.model for row in rows if row.error is None})
    resolved_label = ", ".join(resolved) if resolved else requested_model
    input_tokens = sum(row.input_tokens for row in rows)
    output_tokens = sum(row.output_tokens for row in rows)
    errors = sum(1 for row in rows if row.error is not None)

    safe_model = requested_model.replace("/", "-").replace(":", "-")
    json_path = RESULTS_DIR / f"jev-gold-{safe_model}-{run_ts[:10]}.json"
    json_path.write_text(
        json.dumps(
            {
                "eval_type": "jev-gold",
                "issue": 103,
                "requested_model": requested_model,
                "resolved_models": resolved,
                "threshold": threshold,
                "run_ts": run_ts,
                "n": headline.n,
                "accuracy": round(headline.accuracy, 4),
                "precision": round(headline.precision, 4),
                "recall": round(headline.recall, 4),
                "f1": round(headline.f1, 4),
                "latency_avg_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
                "latency_p95_ms": round(percentile_95(latencies), 1),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "errors": errors,
                "sweep": [
                    {
                        "threshold": cutoff,
                        "accuracy": round(confusion.accuracy, 4),
                        "precision": round(confusion.precision, 4),
                        "recall": round(confusion.recall, 4),
                        "f1": round(confusion.f1, 4),
                    }
                    for cutoff, confusion in sweep
                ],
                "rows": [
                    {
                        "description": row.description,
                        "slice": slice_name(row.description),
                        "outreach_goal": row.outreach_goal,
                        "business_id": row.business_id,
                        "expected": row.expected,
                        "noul": row.noul,
                        "predicted": row.predicted,
                        "latency_ms": round(row.latency_ms, 1),
                        "input_tokens": row.input_tokens,
                        "output_tokens": row.output_tokens,
                        "model": row.model,
                        "error": row.error,
                    }
                    for row in rows
                ],
            },
            indent=2,
        )
    )

    log_path = RESULTS_DIR / "log-jev.csv"
    write_header = not log_path.exists()
    with log_path.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(
                [
                    "timestamp",
                    "requested_model",
                    "resolved_model",
                    "threshold",
                    "n",
                    "accuracy",
                    "precision",
                    "recall",
                    "f1",
                    "latency_avg_ms",
                    "latency_p95_ms",
                    "input_tokens",
                    "output_tokens",
                    "errors",
                ]
            )
        writer.writerow(
            [
                run_ts,
                requested_model,
                resolved_label,
                f"{threshold:.2f}",
                headline.n,
                f"{headline.accuracy:.4f}",
                f"{headline.precision:.4f}",
                f"{headline.recall:.4f}",
                f"{headline.f1:.4f}",
                f"{(sum(latencies) / len(latencies)) if latencies else 0.0:.1f}",
                f"{percentile_95(latencies):.1f}",
                input_tokens,
                output_tokens,
                errors,
            ]
        )

    slice_lines = []
    for name in ("positive", "hard", "ambiguous", "other"):
        bucket = [row for row in rows if slice_name(row.description) == name]
        if not bucket:
            continue
        confusion = _confusion(bucket)
        slice_lines.append(
            f"| `{name}` | {confusion.n} | {_pct(confusion.accuracy)} | {_precision(confusion)} "
            f"| {_recall(confusion)} | {_f1(confusion)} |"
        )

    sweep_lines = [
        f"| {cutoff:.1f} | {_pct(confusion.accuracy)} | {_precision(confusion)} "
        f"| {_recall(confusion)} | {_f1(confusion)} |"
        for cutoff, confusion in sweep
    ]
    avg_ms = (sum(latencies) / len(latencies)) if latencies else 0.0
    md_path = RESULTS_DIR / "jev-gold-latest.md"
    md_path.write_text(
        "# Jev qualifier spike — latest run\n\n"
        f"**Run:** {run_ts}  \n"
        f"**Requested model:** `{requested_model}`  \n"
        f"**Resolved model:** `{resolved_label}`  \n"
        f"**Headline threshold:** {threshold:.2f} (`noul >= threshold`)  \n"
        f"**Dataset:** `evals/datasets/qualifier_gold.jsonl` ({headline.n} examples)  \n"
        "**Eval type:** TypeSafe noul on goal + PlaceDetails. "
        "Not production `qualify_lead()`. See issue #103.\n\n"
        "| Model | Accuracy | Precision | Recall | F1 | Avg latency | p95 latency | Tokens in/out |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| `{resolved_label}` | {_pct(headline.accuracy)} | {_pct(headline.precision)} "
        f"| {_pct(headline.recall)} | {_pct(headline.f1)} "
        f"| {avg_ms:.0f} ms | {percentile_95(latencies):.0f} ms "
        f"| {input_tokens} / {output_tokens} |\n\n"
        "## Slices\n\n"
        "| Slice | N | Accuracy | Precision | Recall | F1 |\n"
        "|---|---|---|---|---|---|\n" + "\n".join(slice_lines) + "\n\n"
        "## Threshold sweep (diagnostic)\n\n"
        "Computed from the stored probabilities. The headline above stays at the "
        "precommitted threshold; this table is not a tuned result.\n\n"
        "| Threshold | Accuracy | Precision | Recall | F1 |\n"
        "|---|---|---|---|---|\n" + "\n".join(sweep_lines) + "\n\n"
        f"API errors (counted as not qualified): {errors}\n"
    )
    print(f"Results  → {json_path.relative_to(REPO_ROOT)}")
    print(f"CSV log  → {log_path.relative_to(REPO_ROOT)}")
    print(f"MD summary → {md_path.relative_to(REPO_ROOT)}")


def main() -> None:
    apply_env_file(REPO_ROOT / ".env", os.environ)
    args = _parse_args()
    api_key = api_key_from(os.environ)
    if api_key is None:
        sys.exit(
            "TYPESAFE_API_KEY is empty. Add it to .env (see .env.example) "
            "and rerun make eval-jev. Issue #103."
        )

    examples = _load_examples(args.limit)
    threshold = float(args.threshold)
    model = str(args.model)
    print("Jev qualifier spike")
    print(f"Model     : {model}")
    print(f"Threshold : {threshold:.2f}")
    print(f"Dataset   : evals/datasets/qualifier_gold.jsonl  ({len(examples)} examples)")
    print()

    rows: list[Row] = []
    run_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with TypeSafeClient(api_key=api_key, model=model) as client:
        for index, example in enumerate(examples, 1):
            row = _score(client, example, model=model, threshold=threshold)
            rows.append(row)
            if row.error is not None:
                print(f"  [{index:3d}] ERROR: {row.error}", file=sys.stderr)
            if index % 10 == 0 or index == len(examples):
                current = _confusion(rows)
                print(
                    f"  {index:3d}/{len(examples)}  acc={current.accuracy:.1%}  f1={current.f1:.1%}"
                )

    headline = _confusion(rows)
    resolved = sorted({row.model for row in rows if row.error is None})
    print()
    print(f"{'Model':<24} {'Acc':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'Err':>4}")
    print("-" * 56)
    label = resolved[0] if len(resolved) == 1 else model
    print(
        f"{label:<24} {headline.accuracy:>6.1%} {headline.precision:>6.1%} "
        f"{headline.recall:>6.1%} {headline.f1:>6.1%} {sum(1 for row in rows if row.error):>4}"
    )
    print()
    _write_reports(rows, requested_model=model, threshold=threshold, run_ts=run_ts)


if __name__ == "__main__":
    main()
