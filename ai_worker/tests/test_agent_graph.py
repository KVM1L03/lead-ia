"""Tests for the LangGraph lead-processing pipeline.

All tests use DummyLM — no real API calls.
Node-level unit tests patch get_lm directly.
Integration tests run the compiled graph end-to-end.
"""

from typing import Any

import pytest
from dspy.utils import DummyLM

import ai_worker.agent_graph as ag
from ai_worker.agent_graph import (
    LeadProcessingState,
    _decide_node,
    _email_node,
    _qualify_node,
    _route,
    process_one_lead,
)
from shared.schemas import Lead, PlaceDetails

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PLACE = PlaceDetails(
    id="dental-warsaw-001",
    name="Klinika Stomatologiczna Centrum",
    address="ul. Nowy Swiat 28, Warszawa",
    lat=52.233,
    lng=21.021,
    category="dental",
    rating=4.8,
    review_count=187,
    website="https://dental-centrum.pl",
    phone="+48 22 826 1234",
    hours=["Mon-Fri 8:00-20:00"],
    photos=[],
)

_QUALIFY_GOOD = {
    "is_qualified": "True",
    "score": "0.85",
    "reasoning": "Dental clinic with website — fits outreach goal.",
    "icp_fit": '{"is_b2b": true, "has_website": true, "size_match": false}',
}

_QUALIFY_BAD = {
    "is_qualified": "False",
    "score": "0.15",
    "reasoning": "Coffee shop — not a dental target.",
    "icp_fit": '{"is_b2b": false, "has_website": false, "size_match": false}',
}

_EMAIL_GOOD = {
    "subject": "Quick question about recalls at Klinika Centrum",
    "body": "Hi, saw your 4.8-star rating — impressive. We help dental clinics automate patient recalls. Worth a quick call?",
    "personalization_hooks": '["4.8-star rating", "Warsaw", "dental clinic"]',
}


def _base_state(**overrides: Any) -> LeadProcessingState:
    state: LeadProcessingState = {
        "outreach_goal": "B2B dental software",
        "sender_context": "I run a SaaS that automates patient recalls.",
        "place": _PLACE,
        "verdict": None,
        "email": None,
        "error": None,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


# ---------------------------------------------------------------------------
# Node unit tests — qualify
# ---------------------------------------------------------------------------


def test_qualify_node_sets_verdict_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    lm = DummyLM(answers=[_QUALIFY_GOOD])
    monkeypatch.setattr(ag, "get_lm", lambda _role: lm)

    result = _qualify_node(_base_state())

    assert "verdict" in result
    assert result["verdict"].is_qualified is True
    assert "error" not in result


def test_qualify_node_sets_error_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def _bad_qualify(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("LLM rate limit")

    monkeypatch.setattr(ag, "qualify_lead", _bad_qualify)
    monkeypatch.setattr(ag, "get_lm", lambda _role: DummyLM(answers=[]))

    result = _qualify_node(_base_state())

    assert result.get("verdict") is None
    assert "LLM rate limit" in result["error"]


# ---------------------------------------------------------------------------
# Node unit tests — decide (no-op)
# ---------------------------------------------------------------------------


def test_decide_node_returns_empty_dict() -> None:
    result = _decide_node(_base_state())
    assert result == {}


# ---------------------------------------------------------------------------
# Node unit tests — routing function
# ---------------------------------------------------------------------------


def test_route_returns_email_when_qualified(monkeypatch: pytest.MonkeyPatch) -> None:
    from shared.schemas import QualifierVerdict

    verdict = QualifierVerdict(is_qualified=True, score=0.9, reasoning="fits", icp_fit={"x": True})
    state = _base_state(verdict=verdict, error=None)
    assert _route(state) == "email"


def test_route_returns_end_when_not_qualified(monkeypatch: pytest.MonkeyPatch) -> None:
    from langgraph.graph import END

    from shared.schemas import QualifierVerdict

    verdict = QualifierVerdict(
        is_qualified=False, score=0.1, reasoning="no fit", icp_fit={"x": False}
    )
    state = _base_state(verdict=verdict, error=None)
    assert _route(state) == END


def test_route_returns_end_when_error_set() -> None:
    from langgraph.graph import END

    state = _base_state(error="something broke")
    assert _route(state) == END


def test_route_returns_end_when_verdict_none() -> None:
    from langgraph.graph import END

    state = _base_state(verdict=None, error=None)
    assert _route(state) == END


# ---------------------------------------------------------------------------
# Node unit tests — email
# ---------------------------------------------------------------------------


def test_email_node_sets_email_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from shared.schemas import QualifierVerdict

    lm = DummyLM(answers=[_EMAIL_GOOD])
    monkeypatch.setattr(ag, "get_lm", lambda _role: lm)

    verdict = QualifierVerdict(
        is_qualified=True, score=0.9, reasoning="fits ICP", icp_fit={"x": True}
    )
    state = _base_state(verdict=verdict)
    result = _email_node(state)

    assert "email" in result
    assert len(result["email"].subject) > 0


# ---------------------------------------------------------------------------
# Integration tests — full graph via process_one_lead
# ---------------------------------------------------------------------------


def test_integration_qualified_lead_returns_lead_with_verdict_and_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_log: list[str] = []

    def _mock_get_lm(role: str) -> DummyLM:
        call_log.append(role)
        if role == "qualifier":
            return DummyLM(answers=[_QUALIFY_GOOD])
        return DummyLM(answers=[_EMAIL_GOOD])

    monkeypatch.setattr(ag, "get_lm", _mock_get_lm)

    lead = process_one_lead(_base_state())

    assert isinstance(lead, Lead)
    assert lead.verdict is not None
    assert lead.verdict.is_qualified is True
    assert lead.email is not None
    assert lead.error is None
    assert "qualifier" in call_log
    assert "email" in call_log


def test_integration_not_qualified_returns_lead_without_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _mock_get_lm(role: str) -> DummyLM:
        return DummyLM(answers=[_QUALIFY_BAD])

    monkeypatch.setattr(ag, "get_lm", _mock_get_lm)

    lead = process_one_lead(_base_state())

    assert lead.verdict is not None
    assert lead.verdict.is_qualified is False
    assert lead.email is None
    assert lead.error is None


def test_integration_qualify_error_returns_lead_with_error_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _bad_qualify(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("provider down")

    monkeypatch.setattr(ag, "qualify_lead", _bad_qualify)
    monkeypatch.setattr(ag, "get_lm", lambda _role: DummyLM(answers=[]))

    lead = process_one_lead(_base_state())

    assert lead.verdict is None
    assert lead.email is None
    assert lead.error is not None
    assert "provider down" in lead.error


def test_integration_graph_import_makes_no_lm_calls() -> None:
    # process_lead_graph is built at import time — verify no LM was called
    # (if get_lm() were called at module level it would've tried to build dspy.LM
    # with a real model string, which is fine, but no *network* call should happen).
    # This test just confirms the compiled graph object exists without error.
    from ai_worker.agent_graph import process_lead_graph

    assert process_lead_graph is not None
