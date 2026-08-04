"""Tests for the ExpandSearchQuery DSPy signature (Backfill decision engine).

All tests use DummyLM — no real LLM calls are made.
"""

import pytest
from dspy.utils import DummyLM
from dspy.utils.exceptions import AdapterParseError

from ai_worker.dspy_engine import expand_search_query
from shared.schemas import ExpansionDecision

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PROMPT = "B2B SaaS selling to dental practices"
_TARGET_QUERY = "dentist Warsaw"

_CITY_ANSWER = {
    "new_target_query": "dentist Krakow",
    "strategy": "city",
    "axis_value": "Krakow",
}

_INDUSTRY_ANSWER = {
    "new_target_query": "orthodontist Warsaw",
    "strategy": "industry",
    "axis_value": "orthodontist",
}

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_expand_search_query_returns_expansion_decision() -> None:
    lm = DummyLM(answers=[_CITY_ANSWER])
    result = expand_search_query(_PROMPT, _TARGET_QUERY, [], [], 5, lm=lm)
    assert isinstance(result, ExpansionDecision)


def test_expand_search_query_maps_target_query() -> None:
    lm = DummyLM(answers=[_CITY_ANSWER])
    result = expand_search_query(_PROMPT, _TARGET_QUERY, [], [], 5, lm=lm)
    assert result.target_query == "dentist Krakow"


def test_expand_search_query_maps_city_strategy() -> None:
    lm = DummyLM(answers=[_CITY_ANSWER])
    result = expand_search_query(_PROMPT, _TARGET_QUERY, [], [], 5, lm=lm)
    assert result.strategy == "city"
    assert result.axis_value == "Krakow"


def test_expand_search_query_maps_industry_strategy() -> None:
    lm = DummyLM(answers=[_INDUSTRY_ANSWER])
    result = expand_search_query(_PROMPT, _TARGET_QUERY, [], [], 5, lm=lm)
    assert result.strategy == "industry"
    assert result.axis_value == "orthodontist"


# ---------------------------------------------------------------------------
# Previously-tried axis values are never returned as the new value
# ---------------------------------------------------------------------------


def test_new_city_is_not_in_tried_cities() -> None:
    tried_cities = ["Warsaw", "Krakow"]
    lm = DummyLM(
        answers=[
            {"new_target_query": "dentist Wroclaw", "strategy": "city", "axis_value": "Wroclaw"}
        ]
    )
    result = expand_search_query(_PROMPT, _TARGET_QUERY, tried_cities, [], 5, lm=lm)
    assert result.strategy == "city"
    assert result.axis_value not in tried_cities


def test_new_industry_is_not_in_tried_industries() -> None:
    tried_industries = ["orthodontist"]
    lm = DummyLM(
        answers=[
            {
                "new_target_query": "dental lab Warsaw",
                "strategy": "industry",
                "axis_value": "dental lab",
            }
        ]
    )
    result = expand_search_query(_PROMPT, _TARGET_QUERY, [], tried_industries, 5, lm=lm)
    assert result.strategy == "industry"
    assert result.axis_value not in tried_industries


# ---------------------------------------------------------------------------
# Malformed LLM output
# ---------------------------------------------------------------------------


def test_malformed_output_raises_adapter_parse_error() -> None:
    # Empty answers force DSPy to exhaust its retry budget (2 attempts)
    lm = DummyLM(answers=[{}, {}])
    with pytest.raises(AdapterParseError):
        expand_search_query(_PROMPT, _TARGET_QUERY, [], [], 5, lm=lm)


# ---------------------------------------------------------------------------
# dspy.context per-call (not dspy.configure at module scope)
# ---------------------------------------------------------------------------


def test_dspy_context_used_per_call_not_global_configure() -> None:
    import dspy

    lm = DummyLM(answers=[_CITY_ANSWER])
    original = dspy.settings.lm
    dspy.settings.configure(lm=None)
    try:
        result = expand_search_query(_PROMPT, _TARGET_QUERY, [], [], 5, lm=lm)
        assert result.strategy == "city"
    finally:
        dspy.settings.configure(lm=original)


def test_provided_lm_is_the_one_called() -> None:
    lm = DummyLM(answers=[_CITY_ANSWER])
    assert len(lm.history) == 0
    expand_search_query(_PROMPT, _TARGET_QUERY, [], [], 5, lm=lm)
    assert len(lm.history) == 1
