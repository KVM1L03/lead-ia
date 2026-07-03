"""Unit tests for evals/scripts/metrics.py cost estimation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_METRICS_PATH = Path(__file__).resolve().parents[1] / "evals" / "scripts" / "metrics.py"
_spec = importlib.util.spec_from_file_location("eval_metrics", _METRICS_PATH)
assert _spec and _spec.loader
metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(metrics)


def test_gemini_cost_estimated_from_tokens_when_promptfoo_reports_zero() -> None:
    provider = {"id": "google:gemini-2.5-flash", "label": "gemini-2.5-flash"}
    response = {"cost": 0, "tokenUsage": {"prompt": 37_016, "completion": 8_338}}
    cost, estimated = metrics._response_cost(provider, response)

    assert estimated is True
    expected = 37_016 * 0.30 / 1_000_000 + 8_338 * 2.50 / 1_000_000
    assert cost == pytest.approx(expected)


def test_reported_cost_used_when_promptfoo_provides_it() -> None:
    provider = {"id": "anthropic:messages:claude-haiku-4-5-20251001", "label": "haiku-4-5"}
    response = {"cost": 0.0947, "tokenUsage": {"prompt": 100, "completion": 10}}

    cost, estimated = metrics._response_cost(provider, response)

    assert estimated is False
    assert cost == pytest.approx(0.0947)


def test_non_gemini_zero_cost_stays_zero() -> None:
    provider = {"id": "openai:gpt-4.1-nano", "label": "gpt-4.1-nano"}
    response = {"cost": 0, "tokenUsage": {"prompt": 1000, "completion": 100}}

    cost, estimated = metrics._response_cost(provider, response)

    assert estimated is False
    assert cost == 0.0
