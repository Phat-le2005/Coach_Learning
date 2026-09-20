import re
import unicodedata
from collections.abc import Sequence
from typing import Protocol

from app.hints.models import HintLevel
from app.questions.models import QuestionType


class HintOptionView(Protocol):
    label: str
    content: str


class HintQuestionView(Protocol):
    correct_answer: str | None
    question_type: QuestionType
    options: Sequence[HintOptionView]


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(without_marks.casefold().split())


def reveals_final_answer(
    question: HintQuestionView, level: HintLevel, content: str
) -> bool:
    """Conservative deterministic guardrail for levels that must stay scaffolded."""

    if level == HintLevel.LEVEL_4 or not question.correct_answer:
        return False

    hint = _normalize(content)
    answer = _normalize(question.correct_answer)
    if not hint or not answer:
        return False

    if question.question_type == QuestionType.MULTIPLE_CHOICE:
        if hint == answer:
            return True
        answer_pattern = re.escape(answer)
        reveal_pattern = (
            rf"\b(answer|option|choice|dap an|lua chon|chon)\s*"
            rf"(?:la|is|:|-)?\s*{answer_pattern}\b"
        )
        if re.search(reveal_pattern, hint):
            return True
        correct_option = next(
            (
                option
                for option in question.options
                if _normalize(option.label) == answer
            ),
            None,
        )
        if correct_option is not None:
            option_content = _normalize(correct_option.content)
            if len(option_content) >= 4 and option_content in hint:
                return True
        return False

    if question.question_type == QuestionType.TRUE_FALSE:
        if hint == answer:
            return True
        pattern = (
            rf"\b(answer|dap an|statement|menh de|is|la)\s*"
            rf"(?:la|is|:|-)?\s*{re.escape(answer)}\b"
        )
        return re.search(pattern, hint) is not None

    if question.question_type == QuestionType.SHORT_ANSWER:
        return len(answer) >= 3 and answer in hint

    return False
