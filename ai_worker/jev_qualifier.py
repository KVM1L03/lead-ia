"""Yes/no qualification decision via a pinned TypeSafe Jev noul.

``evals/jev_qualify.py`` imports the question, state, and cutoff from here so
production and ``make eval-jev`` always share one question and one cutoff —
they cannot silently drift apart. Haiku does not decide; it only explains
leads that pass. See docs/adr/0006-jev-for-qualification-decision.md.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from functools import lru_cache
from typing import Protocol

from typesafe_sdk import JSONContent, JSONValue, Noul, NoulCriteria, TypeSafeClient

from shared.schemas import PlaceDetails

JEV_MODEL = "jev-1.13.0"
QUESTION_NAME = "qualified"
DEFAULT_THRESHOLD = 0.5


def qualification_question() -> Noul:
    """One yes/no: does this business match the outreach goal in the state?"""
    return Noul(
        instructions="This business is a qualified lead for the outreach goal.",
        criteria=NoulCriteria(
            true="The business clearly matches the goal's role, size, and independence.",
            false=(
                "Wrong role, wrong size, a chain or franchise, or only a surface "
                "keyword match such as a supplier in the same industry."
            ),
        ),
    )


def qualification_state(outreach_goal: str, business: PlaceDetails) -> dict[str, JSONValue]:
    """Facts Jev judges. The question itself stays on the noul, not in here."""
    return {
        "outreach_goal": outreach_goal,
        "business": business.model_dump(mode="json"),
    }


def qualifies(noul: float, *, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """True when the yes-probability is at least the threshold.

    0.5 is Jev's documented coin-flip: the answer is whichever side it leans.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be between 0 and 1, got {threshold}")
    if not 0.0 <= noul <= 1.0:
        raise ValueError(f"noul must be between 0 and 1, got {noul}")
    return noul >= threshold


class _NoulAnswer(Protocol):
    @property
    def noul(self) -> float: ...


class _SystemOneResponse(Protocol):
    @property
    def nouls(self) -> Mapping[str, _NoulAnswer]: ...


class _NoulClient(Protocol):
    def system_one(
        self,
        state: JSONContent,
        questions: Mapping[str, Noul],
        *,
        model: str | None = None,
    ) -> _SystemOneResponse: ...


@lru_cache(maxsize=1)
def _default_client() -> TypeSafeClient:
    """Process-wide TypeSafeClient singleton. The model is pinned per-call in score_noul."""
    api_key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "TYPESAFE_API_KEY is empty. Jev qualification requires it — see .env.example."
        )
    return TypeSafeClient(api_key=api_key)


def score_noul(
    outreach_goal: str,
    place: PlaceDetails,
    *,
    client: _NoulClient | None = None,
) -> float:
    """Ask the pinned Jev noul whether this business qualifies.

    Calls the real TypeSafe API unless a test double is injected via ``client``.
    """
    active_client = client if client is not None else _default_client()
    response = active_client.system_one(
        qualification_state(outreach_goal, place),
        {QUESTION_NAME: qualification_question()},
        model=JEV_MODEL,
    )
    return float(response.nouls[QUESTION_NAME].noul)
