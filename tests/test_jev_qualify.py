"""Unit tests for the Jev gold-set decision logic. No API calls."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from shared.schemas import PlaceDetails

_PATH = Path(__file__).resolve().parents[1] / "evals" / "jev_qualify.py"
_spec = importlib.util.spec_from_file_location("jev_qualify", _PATH)
assert _spec and _spec.loader
jev = importlib.util.module_from_spec(_spec)
sys.modules["jev_qualify"] = jev
_spec.loader.exec_module(jev)


def test_qualifies_at_the_coin_flip() -> None:
    assert jev.qualifies(0.5) is True
    assert jev.qualifies(0.49) is False
    assert jev.qualifies(1.0) is True
    assert jev.qualifies(0.0) is False


def test_qualifies_honors_a_stricter_threshold() -> None:
    assert jev.qualifies(0.79, threshold=0.8) is False
    assert jev.qualifies(0.8, threshold=0.8) is True


def test_qualifies_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        jev.qualifies(1.1)
    with pytest.raises(ValueError):
        jev.qualifies(0.4, threshold=1.5)


def test_slice_name_uses_the_gold_prefix() -> None:
    assert jev.slice_name("positive-dental-general-practice") == "positive"
    assert jev.slice_name("hard-dental-supplier") == "hard"
    assert jev.slice_name("ambiguous-law-solo") == "ambiguous"
    assert jev.slice_name("unlabeled") == "other"


def test_state_holds_the_facts_and_not_the_question() -> None:
    place = PlaceDetails(
        id="place_001",
        name="Riverside Dental Care",
        address="412 Riverside Dr",
        lat=41.882,
        lng=-87.631,
        category="General Dentistry",
        rating=4.7,
        review_count=124,
    )
    state = jev.qualification_state(
        "Appointment scheduling software for independent dental practices",
        place,
    )
    question = jev.qualification_question()

    assert (
        state["outreach_goal"] == "Appointment scheduling software for independent dental practices"
    )
    business = state["business"]
    assert isinstance(business, dict)
    assert business["name"] == "Riverside Dental Care"
    assert question.instructions not in str(state)
    assert question.criteria is not None
    assert "role" in str(question.criteria["true"])
    assert "supplier" in str(question.criteria["false"])


def test_api_failure_on_a_positive_is_a_false_negative() -> None:
    scored = jev.score_rows([(True, None), (False, None), (True, True), (False, True)])
    assert scored.tp == 1
    assert scored.fp == 1
    assert scored.tn == 1
    assert scored.fn == 1
    assert scored.f1 == pytest.approx(0.5)


def test_sweep_does_not_change_the_stored_probability() -> None:
    labeled = [(True, 0.62), (False, 0.62)]
    by_threshold = dict(jev.threshold_sweep(labeled, thresholds=(0.5, 0.9)))
    assert by_threshold[0.5].tp == 1
    assert by_threshold[0.5].fp == 1
    assert by_threshold[0.9].tp == 0
    assert by_threshold[0.9].tn == 1


def test_format_rate_is_blank_when_there_is_nothing_to_score() -> None:
    assert jev.format_rate(0.0, defined=False) == "n/a"
    assert jev.format_rate(1.0, defined=True) == "100.0%"


def test_apply_env_file_does_not_override_existing_keys(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "TYPESAFE_API_KEY='from-file'",
                "ALREADY=from-file",
                "export EMPTY_SKIP=",
            ]
        )
    )
    environ = {"ALREADY": "from-env"}
    jev.apply_env_file(env_file, environ)
    assert environ["TYPESAFE_API_KEY"] == "from-file"
    assert environ["ALREADY"] == "from-env"
    assert environ["EMPTY_SKIP"] == ""
    assert jev.api_key_from({"TYPESAFE_API_KEY": "  "}) is None
    assert jev.api_key_from(environ) == "from-file"
