"""Tests for PII redaction in span attributes.

Covers:
- redact_pii() — pure regex function (no Langfuse needed)
- _apply_pii_mask() — Langfuse mask_otel_spans hook
- _workflow_trace_context() — deterministic trace-ID derivation
- setup_telemetry() — no-op when LANGFUSE_DISABLED=1
"""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ai_worker.observability import (
    _apply_pii_mask,
    _workflow_trace_context,
    redact_pii,
    setup_telemetry,
)

_REDACTED = "[REDACTED]"

# ── redact_pii ────────────────────────────────────────────────────────────────


def test_email_is_redacted() -> None:
    assert redact_pii("contact us at hello@example.com today") == (
        f"contact us at {_REDACTED} today"
    )


def test_email_at_string_start() -> None:
    assert redact_pii("user@domain.org") == _REDACTED


def test_email_subdomain() -> None:
    result = redact_pii("send to support@mail.dental-clinic.pl")
    assert _REDACTED in result
    assert "support@" not in result


def test_international_phone_redacted() -> None:
    assert redact_pii("call +48 22 826 1234 now") == f"call {_REDACTED} now"


def test_us_phone_dash_format_redacted() -> None:
    assert redact_pii("reach us at 555-867-5309 anytime") == (f"reach us at {_REDACTED} anytime")


def test_us_phone_dot_format_redacted() -> None:
    assert redact_pii("ph 555.867.5309") == f"ph {_REDACTED}"


def test_float_score_not_redacted() -> None:
    # Qualification scores like "0.92" must survive
    assert redact_pii("confidence: 0.92, score: 4.8") == "confidence: 0.92, score: 4.8"


def test_plain_text_unchanged() -> None:
    text = "Strong ICP fit — B2B dental clinic with website."
    assert redact_pii(text) == text


def test_empty_string() -> None:
    assert redact_pii("") == ""


def test_multiple_pii_in_one_string() -> None:
    result = redact_pii("email john@clinic.pl or call +48 22 826 1234")
    assert "john@clinic.pl" not in result
    assert "+48 22 826" not in result
    assert result.count(_REDACTED) == 2


# ── _apply_pii_mask ───────────────────────────────────────────────────────────


def _make_params(spans_dict: dict[str, dict[str, Any]]) -> Any:
    """Build a minimal MaskOtelSpansParams-like object from plain dicts."""
    from langfuse.types import MaskOtelSpansParams, OtelSpanData, OtelSpanIdentifier

    spans = {}
    for span_id, attrs in spans_dict.items():
        identifier = OtelSpanIdentifier(trace_id="a" * 32, span_id=span_id)
        span_data = OtelSpanData(
            trace_id="a" * 32,
            span_id=span_id,
            parent_span_id=None,
            name="test-span",
            instrumentation_scope_name=None,
            instrumentation_scope_version=None,
            attributes=attrs,
            resource_attributes={},
        )
        spans[identifier] = span_data
    return MaskOtelSpansParams(spans=spans)


def test_pii_mask_redacts_email_in_attribute() -> None:
    params = _make_params({"aabbccdd11223344": {"output": "reply to ceo@company.com"}})
    result = _apply_pii_mask(params=params)
    assert result is not None
    patches = result.span_patches  # type: ignore[union-attr]
    assert len(patches) == 1
    patch_val = next(iter(patches.values()))
    assert _REDACTED in patch_val.set_attributes["output"]


def test_pii_mask_redacts_phone_in_attribute() -> None:
    params = _make_params({"aabbccdd11223344": {"body": "call us: +48 22 826 1234"}})
    result = _apply_pii_mask(params=params)
    patches = result.span_patches  # type: ignore[union-attr]
    assert patches, "expected a patch for phone redaction"
    patch_val = next(iter(patches.values()))
    assert _REDACTED in patch_val.set_attributes["body"]


def test_pii_mask_clean_span_produces_no_patch() -> None:
    params = _make_params({"aabbccdd11223344": {"reasoning": "Strong ICP fit."}})
    result = _apply_pii_mask(params=params)
    assert result is not None
    assert result.span_patches == {}  # type: ignore[union-attr]


def test_pii_mask_non_string_attributes_skipped() -> None:
    params = _make_params({"aabbccdd11223344": {"score": 0.92, "count": 5}})
    result = _apply_pii_mask(params=params)
    assert result is not None
    assert result.span_patches == {}  # type: ignore[union-attr]


def test_pii_mask_multiple_spans() -> None:
    params = _make_params(
        {
            "aabb000011110000": {"info": "contact ceo@corp.io"},
            "ccdd222233330000": {"notes": "no PII here"},
        }
    )
    result = _apply_pii_mask(params=params)
    patches = result.span_patches  # type: ignore[union-attr]
    assert len(patches) == 1  # only the span with PII is patched


# ── _workflow_trace_context ───────────────────────────────────────────────────


def test_same_workflow_id_gives_same_trace_id() -> None:
    ctx1 = _workflow_trace_context("wf-abc-123")
    ctx2 = _workflow_trace_context("wf-abc-123")
    from opentelemetry import trace

    span1 = trace.get_current_span(ctx1)
    span2 = trace.get_current_span(ctx2)
    assert span1.get_span_context().trace_id == span2.get_span_context().trace_id


def test_different_workflow_ids_give_different_trace_ids() -> None:
    ctx1 = _workflow_trace_context("workflow-A")
    ctx2 = _workflow_trace_context("workflow-B")
    from opentelemetry import trace

    id1 = trace.get_current_span(ctx1).get_span_context().trace_id
    id2 = trace.get_current_span(ctx2).get_span_context().trace_id
    assert id1 != id2


def test_trace_id_matches_sha256_of_workflow_id() -> None:
    wf_id = "my-workflow-999"
    ctx = _workflow_trace_context(wf_id)
    from opentelemetry import trace

    span = trace.get_current_span(ctx)
    digest = hashlib.sha256(wf_id.encode()).digest()
    expected_trace_id = int.from_bytes(digest[:16], "big")
    assert span.get_span_context().trace_id == expected_trace_id


# ── setup_telemetry ───────────────────────────────────────────────────────────


def test_setup_telemetry_is_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_DISABLED", "1")
    # Should not import or call anything from langfuse/openinference
    with patch("ai_worker.observability.Langfuse", side_effect=AssertionError("should not call")):
        with patch(
            "ai_worker.observability.DSPyInstrumentor",
            side_effect=AssertionError("should not call"),
        ):
            setup_telemetry()  # must not raise


def test_setup_telemetry_not_disabled_calls_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_DISABLED", raising=False)
    mock_lf = MagicMock()
    mock_instr = MagicMock()
    with patch("ai_worker.observability.Langfuse", return_value=mock_lf) as lf_cls:
        with patch("ai_worker.observability.DSPyInstrumentor", return_value=mock_instr):
            setup_telemetry()
    lf_cls.assert_called_once()
    mock_instr.instrument.assert_called_once()
