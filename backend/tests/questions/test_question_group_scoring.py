from __future__ import annotations

from typing import cast

import pytest

from app.questions.group_scoring import (
    score_question_group,
    true_false_four_score_fraction,
)
from app.questions.models import QuestionGroupScoringPolicy


@pytest.mark.parametrize(
    ("correct_count", "expected"),
    [(0, 0.0), (1, 0.1), (2, 0.25), (3, 0.5), (4, 1.0)],
)
def test_moet_2025_true_false_score_table(
    correct_count: int,
    expected: float,
) -> None:
    correctness = [True] * correct_count + [False] * (4 - correct_count)

    assert true_false_four_score_fraction(correct_count) == expected
    assert score_question_group(
        QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
        correctness,
    ) == expected


def test_question_group_score_scales_by_max_points() -> None:
    assert score_question_group(
        QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
        [True, True, True, False],
        max_points=2.0,
    ) == 1.0


@pytest.mark.parametrize("correctness", [[True] * 3, [True] * 5])
def test_question_group_score_requires_exactly_four_answers(
    correctness: list[bool],
) -> None:
    with pytest.raises(ValueError, match="exactly four booleans"):
        score_question_group(
            QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
            correctness,
        )


def test_question_group_score_rejects_non_boolean_answers() -> None:
    with pytest.raises(ValueError, match="exactly four booleans"):
        score_question_group(
            QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
            cast(list[bool], [True, False, 1, False]),
        )


@pytest.mark.parametrize("max_points", [0.0, -1.0, float("inf"), float("nan")])
def test_question_group_score_requires_positive_finite_max_points(
    max_points: float,
) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        score_question_group(
            QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
            [True, True, True, True],
            max_points=max_points,
        )


def test_question_group_score_rejects_unsupported_policy() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        score_question_group(
            cast(QuestionGroupScoringPolicy, "UNSUPPORTED"),
            [True, True, True, True],
        )


def test_question_group_score_is_deterministic() -> None:
    results = {
        score_question_group(
            QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
            [True, False, True, True],
            max_points=3.5,
        )
        for _ in range(20)
    }

    assert results == {1.75}
