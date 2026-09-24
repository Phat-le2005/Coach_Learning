from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

from app.questions.models import QuestionGroupScoringPolicy


_MOET_2025_TRUE_FALSE_FRACTIONS = {
    0: 0.0,
    1: 0.1,
    2: 0.25,
    3: 0.5,
    4: 1.0,
}


def true_false_four_score_fraction(correct_count: int) -> float:
    if isinstance(correct_count, bool) or not isinstance(correct_count, int):
        raise ValueError("correct_count must be an integer from 0 to 4")
    try:
        return _MOET_2025_TRUE_FALSE_FRACTIONS[correct_count]
    except KeyError as error:
        raise ValueError("correct_count must be from 0 to 4") from error


def score_question_group(
    policy: QuestionGroupScoringPolicy,
    correctness: Sequence[bool],
    max_points: float = 1.0,
) -> float:
    answers = tuple(correctness)
    if len(answers) != 4 or any(type(value) is not bool for value in answers):
        raise ValueError("correctness must contain exactly four booleans")
    if (
        isinstance(max_points, bool)
        or not isinstance(max_points, (int, float))
        or not isfinite(float(max_points))
        or max_points <= 0
    ):
        raise ValueError("max_points must be a finite number greater than zero")
    if policy != QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE:
        raise ValueError(f"Unsupported question group scoring policy: {policy!r}")
    return true_false_four_score_fraction(sum(answers)) * float(max_points)
