"""Deterministic evaluation eligibility for questions across repair, verification, and supply domains."""

from __future__ import annotations

import re
import unicodedata

from app.questions.models import Question, QuestionType

_WHITESPACE = re.compile(r"\s+")


def normalize_answer_string(value: str) -> str:
    """Normalize answer string using NFKC, whitespace collapsing, and casefolding."""
    normalized = unicodedata.normalize("NFKC", value)
    return _WHITESPACE.sub(" ", normalized.strip()).casefold()


def is_deterministically_auto_evaluable(question: Question) -> bool:
    """Return True if question can be evaluated automatically and deterministically.

    Rules:
    - MULTIPLE_CHOICE:
        - correct_answer is non-empty
        - normalized correct_answer matches a normalized label among question options
    - TRUE_FALSE:
        - correct_answer is non-empty
        - normalized correct_answer is in {"true", "false"}
    - SHORT_ANSWER:
        - correct_answer is non-empty
    - OPEN_RESPONSE (or any other type):
        - False
    """
    if not question.correct_answer:
        return False

    expected = normalize_answer_string(question.correct_answer)
    if not expected:
        return False

    if question.question_type == QuestionType.MULTIPLE_CHOICE:
        if not question.options:
            return False
        labels = {
            normalize_answer_string(opt.label)
            for opt in question.options
            if opt.label
        }
        return expected in labels
    elif question.question_type == QuestionType.TRUE_FALSE:
        return expected in {"true", "false"}
    elif question.question_type == QuestionType.SHORT_ANSWER:
        return True

    return False
