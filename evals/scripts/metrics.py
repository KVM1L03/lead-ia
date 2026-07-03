"""Post-process promptfoo JSON output into precision/recall/F1 per provider.

Usage:
    uv run python evals/scripts/metrics.py evals/results/latest.json

Writes:
    evals/results/latest.html  — human-readable report
    evals/results/log.csv      — one-line append per run (timestamp, provider, metrics)
"""

from __future__ import annotations

import csv
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent.parent / "results"

# Google list pricing for gemini-2.5-flash (promptfoo reports $0 for google: provider).
_GEMINI_FLASH_INPUT_PER_TOKEN = 0.30 / 1_000_000
_GEMINI_FLASH_OUTPUT_PER_TOKEN = 2.50 / 1_000_000


def _extract_results(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Handle both promptfoo v1 and v2 output shapes."""
    top = data.get("results", data)
    if isinstance(top, dict):
        rows = top.get("results", [])
    elif isinstance(top, list):
        rows = top
    else:
        rows = []
    return rows  # type: ignore[return-value]


def _strip_markdown_fences(output: str) -> str:
    """Remove optional ```json fences (Haiku wraps JSON despite the prompt)."""
    text = output.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        if text.endswith("```"):
            text = text[: text.rfind("```")].strip()
    return text


def _is_gemini_provider(provider_info: dict[str, Any]) -> bool:
    provider_id = str(provider_info.get("id") or "").lower()
    label = str(provider_info.get("label") or "").lower()
    return "gemini" in provider_id or "gemini" in label or provider_id.startswith("google:")


def _cost_from_tokens(token_usage: dict[str, Any]) -> float:
    prompt = int(token_usage.get("prompt") or token_usage.get("input") or 0)
    completion = int(token_usage.get("completion") or token_usage.get("output") or 0)
    return prompt * _GEMINI_FLASH_INPUT_PER_TOKEN + completion * _GEMINI_FLASH_OUTPUT_PER_TOKEN


def _response_cost(provider_info: dict[str, Any], response: dict[str, Any]) -> tuple[float, bool]:
    """Return (cost_usd, estimated_from_tokens). Promptfoo omits Google provider cost."""
    reported_raw = response.get("cost")
    if reported_raw is not None:
        reported = float(reported_raw)
        if reported > 0:
            return reported, False
    if _is_gemini_provider(provider_info):
        token_usage = response.get("tokenUsage")
        if isinstance(token_usage, dict):
            estimated = _cost_from_tokens(token_usage)
            if estimated > 0:
                return estimated, True
    return float(reported_raw or 0), False


def _get_is_qualified(output: str) -> bool | None:
    """Parse LLM output and extract is_qualified. Returns None on parse failure."""
    try:
        obj = json.loads(_strip_markdown_fences(output))
        val = obj.get("is_qualified")
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() == "true"
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = math.ceil(0.95 * len(sorted_v)) - 1
    return sorted_v[max(0, idx)]


class ProviderMetrics:
    def __init__(self, label: str) -> None:
        self.label = label
        self.tp = self.fp = self.tn = self.fn = self.parse_failures = 0
        self.latencies: list[float] = []
        self.total_cost: float = 0.0
        self.cost_estimated: bool = False

    def add(
        self,
        expected: bool,
        actual: bool | None,
        latency_ms: float,
        cost: float,
        *,
        cost_estimated: bool = False,
    ) -> None:
        self.latencies.append(latency_ms)
        self.total_cost += cost
        if cost_estimated:
            self.cost_estimated = True
        if actual is None:
            self.parse_failures += 1
            if expected:
                self.fn += 1
            else:
                self.tn += 1
            return
        if expected and actual:
            self.tp += 1
        elif expected and not actual:
            self.fn += 1
        elif not expected and actual:
            self.fp += 1
        else:
            self.tn += 1

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.total if self.total else 0.0

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
    def latency_p95(self) -> float:
        return _p95(self.latencies)

    @property
    def latency_avg(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0


def compute_metrics(results: list[dict[str, Any]]) -> dict[str, ProviderMetrics]:
    providers: dict[str, ProviderMetrics] = {}

    for row in results:
        provider_info = row.get("provider", {})
        label: str = provider_info.get("label") or provider_info.get("id") or "unknown"

        if label not in providers:
            providers[label] = ProviderMetrics(label)

        vars_ = row.get("vars", {})
        expected_raw = vars_.get("expected", "false")
        expected = str(expected_raw).lower() == "true"

        response = row.get("response", {})
        output: str = response.get("output", "") or ""
        latency_ms: float = float(row.get("latencyMs") or response.get("latencyMs") or 0)
        cost, cost_estimated = _response_cost(provider_info, response)

        actual = _get_is_qualified(output)
        providers[label].add(expected, actual, latency_ms, cost, cost_estimated=cost_estimated)

    return providers


def _format_cost(m: ProviderMetrics) -> str:
    suffix = "‡" if m.cost_estimated else ""
    return f"${m.total_cost:.4f}{suffix}"


def render_html(providers: dict[str, ProviderMetrics], run_ts: str) -> str:
    rows_html = ""
    any_estimated = False
    for m in sorted(providers.values(), key=lambda x: -x.f1):
        if m.cost_estimated:
            any_estimated = True
        rows_html += f"""
        <tr>
          <td><strong>{m.label}</strong></td>
          <td>{m.accuracy:.1%}</td>
          <td>{m.precision:.1%}</td>
          <td>{m.recall:.1%}</td>
          <td>{m.f1:.1%}</td>
          <td>{m.latency_avg:.0f} ms</td>
          <td>{m.latency_p95:.0f} ms</td>
          <td>{_format_cost(m)}</td>
          <td>{m.parse_failures}</td>
          <td>{m.total}</td>
        </tr>"""

    cost_footnote = ""
    if any_estimated:
        cost_footnote = (
            "<br>‡ Gemini cost estimated from tokenUsage "
            "($0.30/M input, $2.50/M output) — promptfoo reports $0 for Google."
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LeadForge Qualifier Eval — {run_ts}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 40px auto; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: right; }}
  th {{ background: #f4f4f4; text-align: center; }}
  td:first-child {{ text-align: left; }}
  .winner {{ background: #e8f5e9; }}
</style>
</head>
<body>
<h1>LeadForge Qualifier Eval Results</h1>
<p>Run: {run_ts} UTC &nbsp;|&nbsp; Dataset: <code>evals/datasets/qualifier_gold.jsonl</code> (100 hand-labeled examples)</p>
<table>
  <tr>
    <th>Provider</th>
    <th>Accuracy</th>
    <th>Precision</th>
    <th>Recall</th>
    <th>F1</th>
    <th>Avg Latency</th>
    <th>p95 Latency</th>
    <th>Est. Cost</th>
    <th>Parse Errors</th>
    <th>N</th>
  </tr>
  {rows_html}
</table>
<p style="font-size:0.8rem;color:#666">
  Latency = wall-clock per-request (network + model time).<br>
  Positive class = is_qualified true. Precision/recall computed on the positive class.<br>
  50 clear positives, 30 hard negatives, 20 ambiguous (labeled) in gold set.{cost_footnote}
</p>
</body>
</html>"""


def append_csv(providers: dict[str, ProviderMetrics], run_ts: str, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(
                [
                    "timestamp",
                    "provider",
                    "n",
                    "accuracy",
                    "precision",
                    "recall",
                    "f1",
                    "latency_avg_ms",
                    "latency_p95_ms",
                    "cost_usd",
                    "parse_errors",
                ]
            )
        for m in sorted(providers.values(), key=lambda x: x.label):
            writer.writerow(
                [
                    run_ts,
                    m.label,
                    m.total,
                    f"{m.accuracy:.4f}",
                    f"{m.precision:.4f}",
                    f"{m.recall:.4f}",
                    f"{m.f1:.4f}",
                    f"{m.latency_avg:.1f}",
                    f"{m.latency_p95:.1f}",
                    f"{m.total_cost:.6f}",
                    m.parse_failures,
                ]
            )


def print_table(providers: dict[str, ProviderMetrics]) -> None:
    print(
        f"\n{'Provider':<30} {'Acc':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} "
        f"{'AvgMs':>7} {'p95Ms':>7} {'Cost':>8} {'Errs':>5}"
    )
    print("-" * 90)
    for m in sorted(providers.values(), key=lambda x: -x.f1):
        print(
            f"{m.label:<30} {m.accuracy:>6.1%} {m.precision:>6.1%} {m.recall:>6.1%} "
            f"{m.f1:>6.1%} {m.latency_avg:>7.0f} {m.latency_p95:>7.0f} "
            f"${m.total_cost:>7.4f}{'‡' if m.cost_estimated else ''} {m.parse_failures:>5}"
        )
    print()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: metrics.py <path-to-latest.json>", file=sys.stderr)
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"File not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(json_path.read_text())
    results = _extract_results(data)
    providers = compute_metrics(results)

    if not providers:
        print("No results found in JSON. Check promptfoo output format.", file=sys.stderr)
        sys.exit(1)

    run_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    html = render_html(providers, run_ts)
    html_path = RESULTS_DIR / "latest.html"
    html_path.write_text(html)
    print(f"HTML report → {html_path}")

    csv_path = RESULTS_DIR / "log.csv"
    append_csv(providers, run_ts, csv_path)
    print(f"CSV log     → {csv_path}")

    print_table(providers)


if __name__ == "__main__":
    main()
