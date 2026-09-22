"""Tests for the DSPy lead-qualification engine.

All tests use DummyLM — no real LLM calls are made. The yes/no decision comes
from an injected ``noul_for`` stub — no real Jev/TypeSafe calls are made either.
"""

import pytest
from dspy.utils import DummyLM
from dspy.utils.exceptions import AdapterParseError

from ai_worker.dspy_engine import qualify_lead
from shared.schemas import PlaceDetails, QualifierVerdict

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

_REASONING_ANSWER = {"reasoning": "Dental clinic with website — fits the outreach goal."}

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_qualify_lead_yes_comes_from_jev_noul_and_haiku_writes_reasoning() -> None:
    """is_qualified and score are the noul; Haiku only explains a pass."""
    lm = DummyLM(answers=[{"reasoning": "Independent dental practice with a website."}])
    result = qualify_lead(
        "B2B dental software",
        _PLACE,
        lm=lm,
        noul_for=lambda _goal, _place: 0.62,
    )
    assert result.is_qualified is True
    assert result.score == pytest.approx(0.62)
    assert result.reasoning == "Independent dental practice with a website."
    assert result.icp_fit == {}
    assert len(lm.history) == 1


def test_qualify_lead_below_cutoff_skips_haiku() -> None:
    """A noul under 0.5 is a no, even if the LM answer would have said yes."""
    lm = DummyLM(
        answers=[
            {
                "is_qualified": "True",
                "score": "0.99",
                "reasoning": "Haiku would have qualified this.",
            }
        ]
    )
    result = qualify_lead(
        "B2B dental software",
        _PLACE,
        lm=lm,
        noul_for=lambda _goal, _place: 0.49,
    )
    assert result.is_qualified is False
    assert result.score == pytest.approx(0.49)
    assert result.reasoning == ""
    assert result.icp_fit == {}
    assert len(lm.history) == 0


def test_qualify_lead_returns_qualifier_verdict() -> None:
    lm = DummyLM(answers=[_REASONING_ANSWER])
    result = qualify_lead("B2B dental software", _PLACE, lm=lm, noul_for=lambda _goal, _place: 0.85)
    assert isinstance(result, QualifierVerdict)


def test_qualify_lead_maps_score_from_noul() -> None:
    lm = DummyLM(answers=[_REASONING_ANSWER])
    result = qualify_lead("B2B dental software", _PLACE, lm=lm, noul_for=lambda _goal, _place: 0.85)
    assert result.score == pytest.approx(0.85)
    assert 0.0 <= result.score <= 1.0


def test_qualify_lead_maps_reasoning() -> None:
    lm = DummyLM(answers=[_REASONING_ANSWER])
    result = qualify_lead("B2B dental software", _PLACE, lm=lm, noul_for=lambda _goal, _place: 0.85)
    assert isinstance(result.reasoning, str)
    assert len(result.reasoning) > 0


def test_qualify_lead_not_qualified_has_empty_reasoning_and_icp_fit() -> None:
    lm = DummyLM(answers=[])
    result = qualify_lead("B2B dental software", _PLACE, lm=lm, noul_for=lambda _goal, _place: 0.15)
    assert result.is_qualified is False
    assert result.score == pytest.approx(0.15)
    assert result.reasoning == ""
    assert result.icp_fit == {}


# ---------------------------------------------------------------------------
# Malformed LLM output — only reachable when the noul says "qualified"
# ---------------------------------------------------------------------------


def test_malformed_output_raises_adapter_parse_error() -> None:
    # Empty answers force DSPy to exhaust its retry budget (2 attempts)
    lm = DummyLM(answers=[{}, {}])
    with pytest.raises(AdapterParseError):
        qualify_lead("B2B dental software", _PLACE, lm=lm, noul_for=lambda _g, _p: 0.85)


def test_malformed_output_retries_before_failing() -> None:
    # DSPy retries once on parse failure — 2 LM calls total before raising
    lm = DummyLM(answers=[{}, {}])
    with pytest.raises(AdapterParseError):
        qualify_lead("B2B dental software", _PLACE, lm=lm, noul_for=lambda _g, _p: 0.85)
    assert len(lm.history) == 2  # 1 initial attempt + 1 retry


# ---------------------------------------------------------------------------
# dspy.context per-call (not dspy.configure at module scope)
# ---------------------------------------------------------------------------


def test_dspy_context_used_per_call_not_global_configure() -> None:
    # qualify_lead must work even when no global LM is configured.
    # If it called dspy.configure() at module scope or relied on a global LM,
    # this would raise. Passing lm= via dspy.context inside the function
    # is the only way this can succeed.
    import dspy

    lm = DummyLM(answers=[_REASONING_ANSWER])
    # Ensure there is no global LM set (reset to None / unset state)
    original = dspy.settings.lm
    dspy.settings.configure(lm=None)
    try:
        result = qualify_lead("B2B dental software", _PLACE, lm=lm, noul_for=lambda _g, _p: 0.85)
        assert result.is_qualified is True
    finally:
        dspy.settings.configure(lm=original)


def test_provided_lm_is_the_one_called() -> None:
    # Verify the DummyLM we pass is the one actually called (history populated).
    lm = DummyLM(answers=[_REASONING_ANSWER])
    assert len(lm.history) == 0
    qualify_lead("B2B dental software", _PLACE, lm=lm, noul_for=lambda _g, _p: 0.85)
    assert len(lm.history) == 1
