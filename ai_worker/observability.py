"""OpenTelemetry + Langfuse observability for the ai-worker process.

Call ``setup_telemetry()`` once at worker startup (worker.py ``main()``).

Opt-out:
  LANGFUSE_DISABLED=1          → skip all setup; OTel stays as no-op.
  LANGFUSE_TRACING_ENABLED=false → Langfuse quietly disables export even if
                                   setup runs (Langfuse's own env var).
  Missing LANGFUSE_PUBLIC_KEY  → Langfuse silently degrades to NoOpTracer.

Trace grouping:
  Temporal does not propagate OTel context across workflow/activity
  boundaries.  To make all activities from one workflow run appear under a
  single Langfuse trace, every activity span is started as a child of a
  *non-recording* parent whose trace ID is derived deterministically from
  ``workflow_id``.  The parent is never exported; only the activity span
  (and its DSPy/LLM children) are recorded.

PII redaction:
  ``redact_pii(value)`` strips email addresses and phone numbers from a
  string.  It is registered as Langfuse's ``mask_otel_spans`` hook so it
  runs on every attribute before export, without affecting local span data.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from langfuse import Langfuse
from openinference.instrumentation.dspy import DSPyInstrumentor
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

if TYPE_CHECKING:
    from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult

# ── PII patterns ──────────────────────────────────────────────────────────────

# Email: simplified RFC 5321 local-part + domain
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Phone: E.164 international (+XX …) or US/EU formatted (dashes/dots/spaces)
# Anchored with word boundary to avoid matching floats like "0.92" or IDs.
_PHONE_RE = re.compile(
    r"\+\d[\d\s()\-\.]{5,18}\d"  # +48 22 826 1234, +1-800-555-0100 (must end on digit)
    r"|\b\d{3}[\-.\s]\d{3}[\-.\s]\d{4}\b"  # 555-867-5309, 555.867.5309
)

_REDACTED = "[REDACTED]"


def redact_pii(value: str) -> str:
    """Replace email addresses and phone numbers in *value* with '[REDACTED]'."""
    value = _EMAIL_RE.sub(_REDACTED, value)
    value = _PHONE_RE.sub(_REDACTED, value)
    return value


# ── Langfuse mask_otel_spans hook ─────────────────────────────────────────────


def _apply_pii_mask(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult | None:
    """Langfuse mask_otel_spans hook — applied to every span batch before export.

    Walks all string attributes on every span in the batch and redacts any
    email addresses or phone numbers found.
    """
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches = {}
    for identifier, span in params.spans.items():
        changed: dict[str, str] = {}
        for key, val in span.attributes.items():
            if isinstance(val, str):
                cleaned = redact_pii(val)
                if cleaned != val:
                    changed[key] = cleaned
        if changed:
            patches[identifier] = OtelSpanPatch(set_attributes=changed)

    return MaskOtelSpansResult(span_patches=patches)


# ── Tracer (module-level; stays NoOp until setup_telemetry registers a provider) ──

_tracer = trace.get_tracer("ai_worker")


# ── Trace-context helpers ─────────────────────────────────────────────────────


def _workflow_trace_context(workflow_id: str) -> otel_context.Context:
    """Return an OTel Context whose trace ID is pinned to *workflow_id*.

    Converts the workflow ID to a deterministic 128-bit trace ID via SHA-256
    so that all activity spans from the same Temporal workflow run share one
    trace ID and appear together in Langfuse.
    """
    digest = hashlib.sha256(workflow_id.encode()).digest()
    trace_id = int.from_bytes(digest[:16], "big")
    span_id = int.from_bytes(digest[16:24], "big")
    parent_ctx = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    return trace.set_span_in_context(NonRecordingSpan(parent_ctx))


@contextmanager
def activity_span(
    name: str,
    *,
    workflow_id: str,
    lead_id: str | None = None,
) -> Generator[trace.Span, None, None]:
    """Sync context manager that wraps an activity body in an OTel span.

    The span is a child of the (non-recording) workflow-root span so all
    activities from one workflow run appear under a single Langfuse trace.
    ``asyncio.to_thread`` copies Python's contextvars, so any DSPy/LLM spans
    created inside a thread are automatically nested under this span.

    Args:
        name:        Span / observation name shown in Langfuse.
        workflow_id: Temporal workflow ID (available via ``activity.info()``).
        lead_id:     Google Places ``place_id`` of the lead being processed.
    """
    ctx = _workflow_trace_context(workflow_id)
    with _tracer.start_as_current_span(name, context=ctx) as span:
        span.set_attribute("workflow.id", workflow_id)
        if lead_id is not None:
            span.set_attribute("lead.id", lead_id)
        yield span


# ── Setup ─────────────────────────────────────────────────────────────────────


def setup_telemetry() -> None:
    """Register Langfuse as the global OTel TracerProvider and instrument DSPy.

    Safe to call multiple times — subsequent calls are no-ops (DSPyInstrumentor
    and Langfuse are idempotent once initialized).

    Environment variables:
        LANGFUSE_DISABLED=1          Skip this function entirely.
        LANGFUSE_PUBLIC_KEY          Required for live tracing; missing → NoOp.
        LANGFUSE_SECRET_KEY          Required for live tracing; missing → NoOp.
        LANGFUSE_BASE_URL            Langfuse host (default: localhost:3030).
        LANGFUSE_TRACING_ENABLED     Set to 'false' to disable via Langfuse's
                                     own env var instead of LANGFUSE_DISABLED.
    """
    if os.environ.get("LANGFUSE_DISABLED") == "1":
        return

    # Langfuse() → creates TracerProvider → calls otel_trace_api.set_tracer_provider()
    # so subsequent get_tracer() calls (including from DSPyInstrumentor) route to Langfuse.
    # If LANGFUSE_PUBLIC_KEY is absent, Langfuse assigns a NoOpTracer — no error raised.
    Langfuse(mask_otel_spans=_apply_pii_mask)

    # Patch dspy.Predict (and ChainOfThought etc.) to emit OTel spans for every
    # LLM call, including token counts and model name.
    DSPyInstrumentor().instrument()
