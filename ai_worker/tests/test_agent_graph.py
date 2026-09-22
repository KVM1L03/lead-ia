"""Tests for the LangGraph lead-processing pipeline.

All tests use DummyLM — no real API calls.
Node-level unit tests inject DummyLM via the `lm` parameter.
Integration tests run the compiled graph end-to-end with injected LMs.
"""

from typing import Any

import pytest
from dspy.utils import DummyLM

import ai_worker.agent_graph as ag
from ai_worker.agent_graph import (
    LeadProcessingState,
    _decide_node,
    _route,
    build_lead_state,
    email_node,
    process_one_lead,
    qualify_node,
    should_generate_email,
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

_REASONING_GOOD = {"reasoning": "Dental clinic with website — fits outreach goal."}


def _noul_qualified(_outreach_goal: str, _place: PlaceDetails) -> float:
    return 0.85


def _noul_not_qualified(_outreach_goal: str, _place: PlaceDetails) -> float:
    return 0.15


_EMAIL_GOOD = {
    "subject": "Quick question about recalls at Klinika Centrum",
    "body": "Hi, saw your 4.8-star rating — impressive. We help dental clinics automate patient recalls. Worth a quick call?",
    "personalization_hooks": '["4.8-star rating", "Warsaw", "dental clinic"]',
}


def _base_state(**overrides: Any) -> LeadProcessingState:
    state = build_lead_state(
        outreach_goal="B2B dental software",
        place=_PLACE,
        sender_context="I run a SaaS that automates patient recalls.",
    )
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


# ---------------------------------------------------------------------------
# build_lead_state
# ---------------------------------------------------------------------------


def test_build_lead_state_fills_optional_fields_with_defaults() -> None:
    state = build_lead_state(outreach_goal="B2B dental software", place=_PLACE)
    assert state == {
        "outreach_goal": "B2B dental software",
        "sender_context": "",
        "place": _PLACE,
        "verdict": None,
        "email": None,
        "error": None,
    }


def test_build_lead_state_preserves_verdict_email_and_error() -> None:
    from shared.schemas import GeneratedEmail, QualifierVerdict

    verdict = QualifierVerdict(is_qualified=True, score=0.9, reasoning="fit", icp_fit={"x": True})
    email = GeneratedEmail(
        subject="Hello",
        body="Body",
        personalization_hooks=["hook"],
        model_used="mock",
    )
    state = build_lead_state(
        outreach_goal="goal",
        place=_PLACE,
        sender_context="sender",
        verdict=verdict,
        email=email,
        error="boom",
    )
    assert state["verdict"] is verdict
    assert state["email"] is email
    assert state["error"] == "boom"
    assert state["sender_context"] == "sender"


# ---------------------------------------------------------------------------
# Node unit tests — qualify
# ---------------------------------------------------------------------------


def test_qualify_node_sets_verdict_on_success() -> None:
    lm = DummyLM(answers=[_REASONING_GOOD])

    result = qualify_node(_base_state(), lm=lm, noul_for=_noul_qualified)

    assert "verdict" in result
    assert result["verdict"].is_qualified is True
    assert "error" not in result
    assert len(lm.history) == 1


def test_qualify_node_sets_error_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def _bad_qualify(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("LLM rate limit")

    monkeypatch.setattr(ag, "qualify_lead", _bad_qualify)

    result = qualify_node(_base_state(), lm=DummyLM(answers=[]), noul_for=_noul_qualified)

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
# should_generate_email
# ---------------------------------------------------------------------------


def test_should_generate_email_returns_true_for_qualified() -> None:
    from shared.schemas import QualifierVerdict

    verdict = QualifierVerdict(is_qualified=True, score=0.9, reasoning="fit", icp_fit={"x": True})
    assert should_generate_email(_base_state(verdict=verdict, error=None)) is True


def test_should_generate_email_returns_false_for_not_qualified() -> None:
    from shared.schemas import QualifierVerdict

    verdict = QualifierVerdict(is_qualified=False, score=0.1, reasoning="no", icp_fit={"x": False})
    assert should_generate_email(_base_state(verdict=verdict, error=None)) is False


def test_should_generate_email_returns_false_when_error_set() -> None:
    assert should_generate_email(_base_state(error="something broke", verdict=None)) is False


def test_should_generate_email_returns_false_when_verdict_none() -> None:
    assert should_generate_email(_base_state(verdict=None, error=None)) is False


# ---------------------------------------------------------------------------
# Node unit tests — email
# ---------------------------------------------------------------------------


def test_email_node_sets_email_on_success() -> None:
    from shared.schemas import QualifierVerdict

    lm = DummyLM(answers=[_EMAIL_GOOD])

    verdict = QualifierVerdict(
        is_qualified=True, score=0.9, reasoning="fits ICP", icp_fit={"x": True}
    )
    state = _base_state(verdict=verdict)
    result = email_node(state, lm=lm)

    assert "email" in result
    assert len(result["email"].subject) > 0
    assert len(lm.history) == 1


def test_email_node_sets_error_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    from shared.schemas import QualifierVerdict

    def _bad_email(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("LLM rate limit")

    monkeypatch.setattr(ag, "generate_email", _bad_email)

    verdict = QualifierVerdict(
        is_qualified=True, score=0.9, reasoning="fits ICP", icp_fit={"x": True}
    )
    result = email_node(_base_state(verdict=verdict), lm=DummyLM(answers=[]))

    assert result.get("email") is None
    assert "LLM rate limit" in result["error"]


# ---------------------------------------------------------------------------
# Integration tests — full graph via process_one_lead
# ---------------------------------------------------------------------------


def test_integration_qualified_lead_returns_lead_with_verdict_and_email() -> None:
    qualifier_lm = DummyLM(answers=[_REASONING_GOOD])
    email_lm = DummyLM(answers=[_EMAIL_GOOD])

    lead = process_one_lead(
        _base_state(), qualifier_lm=qualifier_lm, email_lm=email_lm, noul_for=_noul_qualified
    )

    assert isinstance(lead, Lead)
    assert lead.verdict is not None
    assert lead.verdict.is_qualified is True
    assert lead.email is not None
    assert lead.error is None
    assert len(qualifier_lm.history) == 1
    assert len(email_lm.history) == 1


def test_integration_not_qualified_returns_lead_without_email() -> None:
    lead = process_one_lead(
        _base_state(),
        qualifier_lm=DummyLM(answers=[]),
        email_lm=DummyLM(answers=[_EMAIL_GOOD]),
        noul_for=_noul_not_qualified,
    )

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

    lead = process_one_lead(
        _base_state(),
        qualifier_lm=DummyLM(answers=[]),
        email_lm=DummyLM(answers=[]),
        noul_for=_noul_qualified,
    )

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
