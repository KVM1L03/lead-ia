"""Gold-set scoring logic for the Jev qualifier eval (issue #103 / #105).

The question, state shape, and cutoff are the production ones — imported from
``ai_worker.jev_qualifier`` — so this eval can never silently drift from what
``qualify_lead()`` actually asks Jev. This module adds only what the eval
needs on top: gold-set slicing and confusion-matrix scoring.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ai_worker.jev_qualifier import (
    DEFAULT_THRESHOLD,
    QUESTION_NAME,
    qualification_question,
    qualification_state,
    qualifies,
)

__all__ = [
    "DEFAULT_THRESHOLD",
    "QUESTION_NAME",
    "SWEEP_THRESHOLDS",
    "Confusion",
    "api_key_from",
    "apply_env_file",
    "format_rate",
    "outcome",
    "percentile_95",
    "qualification_question",
    "qualification_state",
    "qualifies",
    "score_rows",
    "slice_name",
    "threshold_sweep",
]

SWEEP_THRESHOLDS: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9)
_SLICES = frozenset({"positive", "hard", "ambiguous"})


def slice_name(description: str) -> str:
    """Gold-set bucket from the description prefix: positive, hard, or ambiguous."""
    head, _, _ = description.partition("-")
    if head in _SLICES:
        return head
    return "other"


@dataclass(frozen=True)
class Confusion:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def __add__(self, other: Confusion) -> Confusion:
        return Confusion(
            tp=self.tp + other.tp,
            fp=self.fp + other.fp,
            tn=self.tn + other.tn,
            fn=self.fn + other.fn,
        )

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.n if self.n else 0.0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        precision, recall = self.precision, self.recall
        return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def outcome(expected: bool, predicted: bool | None) -> Confusion:
    """Score one example. A missing prediction counts as not qualified.

    That matches ``evals/dspy_eval.py``: an API failure on a positive is a
    false negative, and an API failure on a negative is a true negative.
    """
    if predicted is None:
        return Confusion(fn=1) if expected else Confusion(tn=1)
    if expected and predicted:
        return Confusion(tp=1)
    if expected and not predicted:
        return Confusion(fn=1)
    if not expected and predicted:
        return Confusion(fp=1)
    return Confusion(tn=1)


def score_rows(rows: Sequence[tuple[bool, bool | None]]) -> Confusion:
    total = Confusion()
    for expected, predicted in rows:
        total += outcome(expected, predicted)
    return total


def threshold_sweep(
    labeled: Sequence[tuple[bool, float]],
    thresholds: Sequence[float] = SWEEP_THRESHOLDS,
) -> list[tuple[float, Confusion]]:
    """Re-score stored probabilities. Does not call the API again."""
    return [
        (
            threshold,
            score_rows(
                [(expected, qualifies(noul, threshold=threshold)) for expected, noul in labeled]
            ),
        )
        for threshold in thresholds
    ]


def format_rate(value: float, *, defined: bool) -> str:
    """Percent, or ``n/a`` when the rate has no denominator (no positives to score)."""
    if not defined:
        return "n/a"
    return f"{value:.1%}"


def percentile_95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil(0.95 * len(ordered)) - 1
    return ordered[max(0, index)]


def apply_env_file(path: Path, environ: MutableMapping[str, str]) -> None:
    """Fill keys that are absent. An already-set variable is left alone."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if not key or key in environ:
            continue
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
            cleaned = cleaned[1:-1]
        environ[key] = cleaned


def api_key_from(environ: Mapping[str, str]) -> str | None:
    key = environ.get("TYPESAFE_API_KEY", "").strip()
    return key or None
