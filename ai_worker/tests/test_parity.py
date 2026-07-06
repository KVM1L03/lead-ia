"""Parity tests: verify that graph nodes and Temporal activities yield identical results.

These guarantee that routing the same input through qualify_node / email_node directly
(as the sync path does via process_one_lead) or through the Temporal activity wrapper
(as the Temporal path does) produces identical outputs.
"""

from typing import Any

import pytest
from dspy.utils import DummyLM
from temporalio.testing import ActivityEnvironment

import ai_worker.agent_graph as ag
from ai_worker.activities import generate_email_activity, qualify_lead_activity
from ai_worker.agent_graph import (
    LeadProcessingState,
    email_node,
    qualify_node,
    should_generate_email,
)
from shared.schemas import PlaceDetails, QualifierVerdict

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
# Qualify parity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qualify_node_and_activity_return_same_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """qualify_lead_activity and qualify_node produce identical verdicts for same input."""
    # Node path
    lm1 = DummyLM(answers=[_QUALIFY_GOOD])
    monkeypatch.setattr(ag, "get_lm", lambda _role: lm1)
    node_patch = qualify_node(_base_state())
    node_verdict = node_patch.get("verdict")
    assert node_verdict is not None, "qualify_node should return a verdict"

    # Activity path — fresh LM so DummyLM cursor resets
    lm2 = DummyLM(answers=[_QUALIFY_GOOD])
    monkeypatch.setattr(ag, "get_lm", lambda _role: lm2)
    env = ActivityEnvironment()
    activity_verdict = await env.run(qualify_lead_activity, "B2B dental software", _PLACE)

    assert activity_verdict.is_qualified == node_verdict.is_qualified
    assert activity_verdict.reasoning == node_verdict.reasoning
    assert activity_verdict.icp_fit == node_verdict.icp_fit
    assert abs(activity_verdict.score - node_verdict.score) < 0.001


# ---------------------------------------------------------------------------
# Email parity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_node_and_activity_return_same_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_email_activity and email_node produce identical emails for same input."""
    verdict = QualifierVerdict(
        is_qualified=True, score=0.85, reasoning="fits ICP", icp_fit={"x": True}
    )

    # Node path
    lm1 = DummyLM(answers=[_EMAIL_GOOD])
    monkeypatch.setattr(ag, "get_lm", lambda _role: lm1)
    state = _base_state(verdict=verdict)
    node_patch = email_node(state)
    node_email = node_patch.get("email")
    assert node_email is not None, "email_node should return an email"

    # Activity path — fresh LM
    lm2 = DummyLM(answers=[_EMAIL_GOOD])
    monkeypatch.setattr(ag, "get_lm", lambda _role: lm2)
    env = ActivityEnvironment()
    activity_email = await env.run(
        generate_email_activity,
        "B2B dental software",
        _PLACE,
        verdict,
        "I run a SaaS that automates patient recalls.",
    )

    assert activity_email.subject == node_email.subject
    assert activity_email.body == node_email.body
    assert activity_email.personalization_hooks == node_email.personalization_hooks


# ---------------------------------------------------------------------------
# should_generate_email matches workflow routing logic
# ---------------------------------------------------------------------------


def test_should_generate_email_true_for_qualified_no_error() -> None:
    """should_generate_email returns True when verdict is qualified and error is None."""
    verdict = QualifierVerdict(
        is_qualified=True, score=0.9, reasoning="good fit", icp_fit={"x": True}
    )
    assert should_generate_email(_base_state(verdict=verdict, error=None)) is True


def test_should_generate_email_false_for_not_qualified() -> None:
    """should_generate_email returns False for unqualified leads (workflow skips email)."""
    verdict = QualifierVerdict(
        is_qualified=False, score=0.1, reasoning="no fit", icp_fit={"x": False}
    )
    assert should_generate_email(_base_state(verdict=verdict, error=None)) is False


def test_should_generate_email_false_when_error_set() -> None:
    """should_generate_email returns False when qualify failed (workflow skips email)."""
    assert should_generate_email(_base_state(error="LLM rate limited", verdict=None)) is False


def test_should_generate_email_false_when_verdict_none() -> None:
    """should_generate_email returns False when verdict not yet computed."""
    assert should_generate_email(_base_state(verdict=None, error=None)) is False
