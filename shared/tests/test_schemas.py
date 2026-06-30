"""Tests for shared Pydantic schemas — happy paths, extra-field rejection, validators."""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from shared.schemas import (
    GeneratedEmail,
    Lead,
    PlaceDetails,
    PlaceSearchResult,
    QualifierVerdict,
    Run,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_PLACE_SEARCH = {
    "id": "dental-warsaw-001",
    "name": "Klinika Stomatologiczna",
    "address": "ul. Nowy Świat 28, Warszawa",
    "lat": 52.233,
    "lng": 21.021,
    "category": "dental",
    "rating": 4.8,
    "review_count": 187,
}

_PLACE_DETAILS = {
    **_PLACE_SEARCH,
    "website": "https://example.pl",
    "phone": "+48 22 826 1234",
    "hours": ["Mon-Fri 8:00-20:00"],
    "photos": [],
}

_VERDICT = {
    "is_qualified": True,
    "score": 0.85,
    "reasoning": "Fits ICP on all axes.",
    "icp_fit": {"is_b2b": True, "has_website": True, "size_match": False},
}

_EMAIL = {
    "subject": "Quick question about your patients",
    "body": "Hi, we help dental clinics automate recalls...",
    "personalization_hooks": ["dental clinic", "Warsaw location"],
    "model_used": "claude-sonnet-4-6",
}

_PLACE_DETAILS_OBJ = PlaceDetails.model_validate(_PLACE_DETAILS)
_VERDICT_OBJ = QualifierVerdict.model_validate(_VERDICT)
_EMAIL_OBJ = GeneratedEmail.model_validate(_EMAIL)


# ---------------------------------------------------------------------------
# PlaceSearchResult
# ---------------------------------------------------------------------------


def test_place_search_result_happy_path() -> None:
    r = PlaceSearchResult.model_validate(_PLACE_SEARCH)
    assert r.id == "dental-warsaw-001"
    assert r.rating == 4.8
    assert r.review_count == 187


def test_place_search_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PlaceSearchResult.model_validate({**_PLACE_SEARCH, "unknown_field": "oops"})


def test_place_search_result_rejects_string_for_float() -> None:
    with pytest.raises(ValidationError):
        PlaceSearchResult.model_validate({**_PLACE_SEARCH, "lat": "52.233"})


def test_place_search_result_rejects_string_for_int() -> None:
    with pytest.raises(ValidationError):
        PlaceSearchResult.model_validate({**_PLACE_SEARCH, "review_count": "187"})


# ---------------------------------------------------------------------------
# PlaceDetails
# ---------------------------------------------------------------------------


def test_place_details_happy_path() -> None:
    d = PlaceDetails.model_validate(_PLACE_DETAILS)
    assert d.website == "https://example.pl"
    assert d.hours == ["Mon-Fri 8:00-20:00"]
    assert d.photos == []


def test_place_details_optional_fields_default_to_none_or_empty() -> None:
    d = PlaceDetails.model_validate(_PLACE_SEARCH)
    assert d.website is None
    assert d.phone is None
    assert d.hours == []
    assert d.photos == []


def test_place_details_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PlaceDetails.model_validate({**_PLACE_DETAILS, "surprise": True})


# ---------------------------------------------------------------------------
# QualifierVerdict
# ---------------------------------------------------------------------------


def test_qualifier_verdict_happy_path() -> None:
    v = QualifierVerdict.model_validate(_VERDICT)
    assert v.is_qualified is True
    assert v.score == 0.85
    assert v.icp_fit["is_b2b"] is True


def test_qualifier_verdict_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        QualifierVerdict.model_validate({**_VERDICT, "extra": "nope"})


def test_qualifier_verdict_rejects_string_score() -> None:
    with pytest.raises(ValidationError):
        QualifierVerdict.model_validate({**_VERDICT, "score": "0.85"})


def test_qualifier_verdict_rejects_score_out_of_range() -> None:
    with pytest.raises(ValidationError):
        QualifierVerdict.model_validate({**_VERDICT, "score": 1.5})


def test_qualifier_verdict_rejects_int_for_bool_in_icp_fit() -> None:
    with pytest.raises(ValidationError):
        QualifierVerdict.model_validate({**_VERDICT, "icp_fit": {"is_b2b": 1}})


def test_qualifier_verdict_rejects_string_for_bool() -> None:
    with pytest.raises(ValidationError):
        QualifierVerdict.model_validate({**_VERDICT, "is_qualified": "true"})


# ---------------------------------------------------------------------------
# GeneratedEmail
# ---------------------------------------------------------------------------


def test_generated_email_happy_path() -> None:
    e = GeneratedEmail.model_validate(_EMAIL)
    assert e.model_used == "claude-sonnet-4-6"
    assert len(e.personalization_hooks) == 2


def test_generated_email_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GeneratedEmail.model_validate({**_EMAIL, "tone": "friendly"})


def test_generated_email_rejects_subject_over_100_chars() -> None:
    with pytest.raises(ValidationError):
        GeneratedEmail.model_validate({**_EMAIL, "subject": "x" * 101})


def test_generated_email_accepts_subject_exactly_100_chars() -> None:
    e = GeneratedEmail.model_validate({**_EMAIL, "subject": "x" * 100})
    assert len(e.subject) == 100


def test_generated_email_rejects_body_over_1500_chars() -> None:
    with pytest.raises(ValidationError):
        GeneratedEmail.model_validate({**_EMAIL, "body": "x" * 1501})


def test_generated_email_accepts_body_exactly_1500_chars() -> None:
    e = GeneratedEmail.model_validate({**_EMAIL, "body": "x" * 1500})
    assert len(e.body) == 1500


# ---------------------------------------------------------------------------
# Lead
# ---------------------------------------------------------------------------


def test_lead_pending_no_verdict_or_email() -> None:
    lead = Lead(place=_PLACE_DETAILS_OBJ)
    assert lead.verdict is None
    assert lead.email is None
    assert lead.decision == "pending"


def test_lead_qualified_with_verdict_and_email() -> None:
    lead = Lead(
        place=_PLACE_DETAILS_OBJ,
        verdict=_VERDICT_OBJ,
        email=_EMAIL_OBJ,
        decision="approved",
    )
    assert lead.verdict is not None
    assert lead.verdict.is_qualified is True
    assert lead.decision == "approved"


def test_lead_rejects_invalid_decision() -> None:
    with pytest.raises(ValidationError):
        Lead.model_validate(
            {
                "place": _PLACE_DETAILS,
                "decision": "maybe",
            }
        )


def test_lead_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Lead.model_validate({"place": _PLACE_DETAILS, "unknown": "x"})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

_RUN_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")
_NOW = datetime(2024, 6, 1, 12, 0, 0)


def test_run_happy_path_no_leads() -> None:
    run = Run(
        id=_RUN_ID,
        prompt="dental clinics in Warsaw",
        target_query="dental Warsaw",
        limit=20,
        leads=[],
        created_at=_NOW,
        status="scraping",
    )
    assert run.id == _RUN_ID
    assert run.status == "scraping"
    assert run.leads == []


def test_run_with_leads() -> None:
    lead = Lead(place=_PLACE_DETAILS_OBJ, verdict=_VERDICT_OBJ)
    run = Run(
        id=_RUN_ID,
        prompt="dental clinics in Warsaw",
        target_query="dental Warsaw",
        limit=20,
        leads=[lead],
        created_at=_NOW,
        status="completed",
    )
    assert len(run.leads) == 1
    assert run.leads[0].verdict is not None


def test_run_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        Run.model_validate(
            {
                "id": str(_RUN_ID),
                "prompt": "test",
                "target_query": "test",
                "limit": 10,
                "leads": [],
                "created_at": _NOW.isoformat(),
                "status": "unknown",
            }
        )


def test_run_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Run.model_validate(
            {
                "id": _RUN_ID,
                "prompt": "test",
                "target_query": "test",
                "limit": 10,
                "leads": [],
                "created_at": _NOW,
                "status": "scraping",
                "extra": "oops",
            }
        )


def test_run_rejects_string_for_uuid() -> None:
    with pytest.raises(ValidationError):
        Run.model_validate(
            {
                "id": "not-a-uuid",
                "prompt": "test",
                "target_query": "test",
                "limit": 10,
                "leads": [],
                "created_at": _NOW,
                "status": "scraping",
            }
        )


def test_run_rejects_string_for_datetime() -> None:
    with pytest.raises(ValidationError):
        Run.model_validate(
            {
                "id": _RUN_ID,
                "prompt": "test",
                "target_query": "test",
                "limit": 10,
                "leads": [],
                "created_at": "2024-06-01T12:00:00",
                "status": "scraping",
            }
        )
