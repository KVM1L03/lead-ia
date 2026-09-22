"""Tests for the production Jev yes/no call. No network."""

from collections.abc import Mapping
from typing import ClassVar

from typesafe_sdk import JSONContent, JSONValue, Noul

from ai_worker.jev_qualifier import JEV_MODEL, QUESTION_NAME, qualification_question, score_noul
from shared.schemas import PlaceDetails

_PLACE = PlaceDetails(
    id="dental-warsaw-001",
    name="Klinika Stomatologiczna Centrum",
    address="ul. Nowy Swiat 28, Warszawa",
    lat=52.233,
    lng=21.021,
    category="dental",
    rating=4.8,
    review_count=187,
)


class _Answer:
    noul = 0.73


class _Response:
    nouls: ClassVar[dict[str, _Answer]] = {QUESTION_NAME: _Answer()}


class _Client:
    def __init__(self) -> None:
        self.model: str | None = None
        self.state: Mapping[str, JSONValue | None] | None = None
        self.question_names: list[str] = []

    def system_one(
        self,
        state: JSONContent,
        questions: Mapping[str, Noul],
        *,
        model: str | None = None,
    ) -> _Response:
        assert isinstance(state, Mapping)
        self.model = model
        self.state = dict(state)
        self.question_names = list(questions)
        return _Response()


def test_score_noul_asks_pinned_jev_with_the_shared_question() -> None:
    client = _Client()
    score = score_noul("B2B dental software", _PLACE, client=client)
    assert score == 0.73
    assert client.model == JEV_MODEL
    assert JEV_MODEL == "jev-1.13.0"
    assert client.question_names == [QUESTION_NAME]
    assert client.state is not None
    assert client.state["outreach_goal"] == "B2B dental software"
    business = client.state["business"]
    assert isinstance(business, Mapping)
    assert business["id"] == _PLACE.id
    asked = qualification_question()
    instructions = asked.instructions
    assert isinstance(instructions, str)
    assert instructions.startswith("This business is a qualified lead")
