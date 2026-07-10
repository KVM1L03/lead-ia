"""Tests for the DSPy email generation engine.

All tests use DummyLM — no real LLM calls are made.
"""

import pytest
from dspy.utils import DummyLM
from dspy.utils.exceptions import AdapterParseError

from ai_worker.dspy_engine import generate_email
from shared.schemas import GeneratedEmail, PlaceDetails

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

_GOOD_ANSWER = {
    "subject": "Quick question about patient recall at Klinika Centrum",
    "body": (
        "Hi, I noticed Klinika Stomatologiczna Centrum has a 4.8 rating on Google "
        "with nearly 200 reviews — clearly a well-run practice. We help dental "
        "clinics in Warsaw automate patient recall so you spend less time on admin. "
        "Would a 15-minute call make sense?"
    ),
    "personalization_hooks": '["4.8-star rating", "187 reviews", "Warsaw location"]',
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_generate_email_returns_generated_email() -> None:
    lm = DummyLM(answers=[_GOOD_ANSWER])
    result = generate_email(
        "dental practice software",
        _PLACE,
        "Dental clinic with website, fits ICP.",
        "I run a SaaS that automates patient recalls for dental practices.",
        lm=lm,
    )
    assert isinstance(result, GeneratedEmail)


def test_generate_email_subject_is_string() -> None:
    lm = DummyLM(answers=[_GOOD_ANSWER])
    result = generate_email(
        "dental practice software",
        _PLACE,
        "Dental clinic with website, fits ICP.",
        "I run a SaaS that automates patient recalls for dental practices.",
        lm=lm,
    )
    assert isinstance(result.subject, str)
    assert len(result.subject) > 0


def test_generate_email_body_is_string() -> None:
    lm = DummyLM(answers=[_GOOD_ANSWER])
    result = generate_email(
        "dental practice software",
        _PLACE,
        "Dental clinic with website, fits ICP.",
        "I run a SaaS that automates patient recalls for dental practices.",
        lm=lm,
    )
    assert isinstance(result.body, str)
    assert len(result.body) > 0


def test_generate_email_personalization_hooks_non_empty() -> None:
    lm = DummyLM(answers=[_GOOD_ANSWER])
    result = generate_email(
        "dental practice software",
        _PLACE,
        "Dental clinic with website, fits ICP.",
        "I run a SaaS that automates patient recalls for dental practices.",
        lm=lm,
    )
    assert isinstance(result.personalization_hooks, list)
    assert len(result.personalization_hooks) > 0


def test_generate_email_model_used_set() -> None:
    lm = DummyLM(answers=[_GOOD_ANSWER])
    result = generate_email(
        "dental practice software",
        _PLACE,
        "Dental clinic with website, fits ICP.",
        "I run a SaaS that automates patient recalls for dental practices.",
        lm=lm,
    )
    assert isinstance(result.model_used, str)
    assert len(result.model_used) > 0


# ---------------------------------------------------------------------------
# Schema validation via GeneratedEmail
# ---------------------------------------------------------------------------


def test_body_over_1500_chars_rejected_by_schema() -> None:
    # GeneratedEmail.body has max_length=1500; build a too-long answer and
    # confirm Pydantic rejects it (the validation happens inside generate_email).
    import pydantic

    long_body = "x" * 1501
    answer = {**_GOOD_ANSWER, "body": long_body}
    lm = DummyLM(answers=[answer])
    with pytest.raises(pydantic.ValidationError):
        generate_email(
            "dental practice software",
            _PLACE,
            "Dental clinic with website, fits ICP.",
            "I run a SaaS that automates patient recalls for dental practices.",
            lm=lm,
        )


def test_subject_exactly_80_chars_accepted() -> None:
    answer = {**_GOOD_ANSWER, "subject": "s" * 80}
    lm = DummyLM(answers=[answer])
    result = generate_email(
        "dental practice software",
        _PLACE,
        "Dental clinic with website, fits ICP.",
        "I run a SaaS that automates patient recalls for dental practices.",
        lm=lm,
    )
    assert len(result.subject) == 80


# ---------------------------------------------------------------------------
# Malformed LLM output
# ---------------------------------------------------------------------------


def test_malformed_output_raises_adapter_parse_error() -> None:
    lm = DummyLM(answers=[{}, {}])
    with pytest.raises(AdapterParseError):
        generate_email(
            "dental practice software",
            _PLACE,
            "Dental clinic with website, fits ICP.",
            "I run a SaaS that automates patient recalls for dental practices.",
            lm=lm,
        )


def test_malformed_output_retries_before_failing() -> None:
    lm = DummyLM(answers=[{}, {}])
    with pytest.raises(AdapterParseError):
        generate_email(
            "dental practice software",
            _PLACE,
            "Dental clinic with website, fits ICP.",
            "I run a SaaS that automates patient recalls for dental practices.",
            lm=lm,
        )
    assert len(lm.history) == 2


# ---------------------------------------------------------------------------
# dspy.context per-call
# ---------------------------------------------------------------------------


def test_dspy_context_used_per_call_not_global_configure() -> None:
    import dspy

    lm = DummyLM(answers=[_GOOD_ANSWER])
    original = dspy.settings.lm
    dspy.settings.configure(lm=None)
    try:
        result = generate_email(
            "dental practice software",
            _PLACE,
            "Dental clinic with website, fits ICP.",
            "I run a SaaS that automates patient recalls for dental practices.",
            lm=lm,
        )
        assert isinstance(result, GeneratedEmail)
    finally:
        dspy.settings.configure(lm=original)


def test_provided_lm_is_the_one_called() -> None:
    lm = DummyLM(answers=[_GOOD_ANSWER])
    assert len(lm.history) == 0
    generate_email(
        "dental practice software",
        _PLACE,
        "Dental clinic with website, fits ICP.",
        "I run a SaaS that automates patient recalls for dental practices.",
        lm=lm,
    )
    assert len(lm.history) == 1


# ---------------------------------------------------------------------------
# Rating-less place
# ---------------------------------------------------------------------------

_PLACE_NO_RATING = PlaceDetails(
    id="dental-warsaw-002",
    name="Gabinet Bez Oceny",
    address="ul. Marszałkowska 10, Warszawa",
    lat=52.234,
    lng=21.022,
    category="dental",
    rating=None,
    review_count=None,
    website="https://gabinet.pl",
    phone="+48 22 111 2222",
    hours=[],
    photos=[],
)

_GOOD_ANSWER_NO_RATING = {
    "subject": "Quick question for Gabinet Bez Oceny",
    "body": (
        "Hi, I noticed Gabinet Bez Oceny in Warsaw. "
        "We help dental clinics automate patient recall. "
        "Would a 15-minute call make sense?"
    ),
    "personalization_hooks": '["Warsaw location", "dental clinic"]',
}


def test_generate_email_rating_less_place_succeeds() -> None:
    lm = DummyLM(answers=[_GOOD_ANSWER_NO_RATING])
    result = generate_email(
        "dental practice software",
        _PLACE_NO_RATING,
        "Dental clinic with website, fits ICP.",
        "I run a SaaS that automates patient recalls for dental practices.",
        lm=lm,
    )
    assert isinstance(result, GeneratedEmail)


def test_generate_email_rating_less_place_no_null_in_prompt() -> None:
    """exclude_none=True — 'rating' key must not appear in the serialized business JSON."""
    lm = DummyLM(answers=[_GOOD_ANSWER_NO_RATING])
    generate_email(
        "dental practice software",
        _PLACE_NO_RATING,
        "Dental clinic with website, fits ICP.",
        "I run a SaaS that automates patient recalls for dental practices.",
        lm=lm,
    )
    prompt_text = str(lm.history[0]["messages"])
    assert '"rating"' not in prompt_text
    assert '"review_count"' not in prompt_text
