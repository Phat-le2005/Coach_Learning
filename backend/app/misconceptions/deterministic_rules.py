from __future__ import annotations

import re
from typing import Callable
from uuid import UUID

from app.misconceptions.models import MisconceptionCategory
from app.misconceptions.schemas import MisconceptionAnalysisOutput
from app.misconceptions.taxonomy import ScopedTaxonomy
from app.questions.models import Question, QuestionType

# Regular expression to test whether a response has reasoning steps or explanation
_REASONING_INDICATORS = re.compile(
    r"(\b(vì|do|nên|bởi vì|suy ra|tại|khi|ta có|bước|đạo hàm|tích phân|nghiệm|dấu)\b|=>|->|=|<=|>=|\+|\-|\*|\/|\^)",
    re.IGNORECASE,
)


def has_reasoning(student_answer: str | None) -> bool:
    """Determine if a student response contains explicit reasoning/scratchwork.

    Returns False for bare option letters ('A', 'B'), boolean flags ('TRUE', 'FALSE'),
    or short single-token guesses.
    """
    if not student_answer:
        return False

    cleaned = student_answer.strip()
    if len(cleaned) < 5:
        # Single choice label e.g. "A", "b", "1"
        return False

    # Check bare tokens like "TRUE", "FALSE", "A", "B", "C", "D"
    if cleaned.upper() in {"TRUE", "FALSE", "ĐÚNG", "SAI", "YES", "NO", "A", "B", "C", "D"}:
        return False

    # Check words count
    words = cleaned.split()
    if len(words) < 3 and not any(op in cleaned for op in ["=", "+", "-", "*", "/", "=>", "^"]):
        return False

    # If it has length >= 12 and contains reasoning indicators or mathematical steps
    if len(cleaned) >= 12 or _REASONING_INDICATORS.search(cleaned):
        return True

    return len(words) >= 4


# Type for custom deterministic rule functions
DeterministicRuleFunc = Callable[
    [Question, str, ScopedTaxonomy], MisconceptionAnalysisOutput | None
]


class DeterministicRuleMatcher:
    """Evaluates explicit, deterministic rules for misconceptions before calling AI."""

    def __init__(
        self,
        custom_rules: list[DeterministicRuleFunc] | None = None,
    ) -> None:
        self.custom_rules = custom_rules or []

    def evaluate(
        self,
        question: Question,
        student_answer: str,
        taxonomy: ScopedTaxonomy,
    ) -> MisconceptionAnalysisOutput | None:
        """Evaluate deterministic rules against the question and student answer.

        Returns MisconceptionAnalysisOutput if a deterministic pattern matches with high confidence,
        or None if insufficient.
        """
        if not student_answer or not taxonomy.definitions:
            return None

        # 1. Check custom registered rules first
        for rule in self.custom_rules:
            result = rule(question, student_answer, taxonomy)
            if result is not None:
                return result

        # 2. Check built-in deterministic patterns matching scoped taxonomy
        defs_by_code = {d.code: d for d in taxonomy.definitions}

        # Pattern: Indefinite integral missing constant '+ C'
        if "INDEFINITE_INTEGRAL_MISSING_CONSTANT" in defs_by_code:
            d = defs_by_code["INDEFINITE_INTEGRAL_MISSING_CONSTANT"]
            ans_lower = student_answer.lower()
            if (
                any(kw in question.content.lower() for kw in ["nguyên hàm", "tích phân bất định", "indefinite integral", "∫"])
                and ("+" not in ans_lower or "c" not in ans_lower)
                and len(student_answer.strip()) > 3
            ):
                return MisconceptionAnalysisOutput(
                    concept_id=d.concept_id,
                    problem_type_id=d.problem_type_id,
                    misconception_code=d.code,
                    error_category=d.category,
                    first_wrong_step="Omitted arbitrary constant '+ C' in indefinite integral result.",
                    confidence=0.95,
                    possible_prerequisite_concept_id=None,
                    requires_prerequisite_check=False,
                )

        # Pattern: Logarithm sum distribution log(a+b) = log(a) + log(b)
        if "LOG_SUM_DISTRIBUTION" in defs_by_code:
            d = defs_by_code["LOG_SUM_DISTRIBUTION"]
            if re.search(r"log\s*\([^)]+\+[^)]+\)\s*=\s*log", student_answer, re.IGNORECASE) or re.search(
                r"ln\s*\([^)]+\+[^)]+\)\s*=\s*ln", student_answer, re.IGNORECASE
            ):
                return MisconceptionAnalysisOutput(
                    concept_id=d.concept_id,
                    problem_type_id=d.problem_type_id,
                    misconception_code=d.code,
                    error_category=d.category,
                    first_wrong_step="Distributed logarithm over addition: log(a+b) = log(a)+log(b).",
                    confidence=0.98,
                    possible_prerequisite_concept_id=None,
                    requires_prerequisite_check=False,
                )

        # Pattern: Derivative sign direction reversed
        if "DERIVATIVE_SIGN_DIRECTION" in defs_by_code:
            d = defs_by_code["DERIVATIVE_SIGN_DIRECTION"]
            ans_clean = student_answer.lower()
            if (
                ("y' > 0" in ans_clean and "nghịch biến" in ans_clean)
                or ("y' < 0" in ans_clean and "đồng biến" in ans_clean)
                or ("f'(x) > 0" in ans_clean and "nghịch biến" in ans_clean)
                or ("f'(x) < 0" in ans_clean and "đồng biến" in ans_clean)
            ):
                return MisconceptionAnalysisOutput(
                    concept_id=d.concept_id,
                    problem_type_id=d.problem_type_id,
                    misconception_code=d.code,
                    error_category=d.category,
                    first_wrong_step="Reversed the relationship between derivative sign and monotonicity.",
                    confidence=0.95,
                    possible_prerequisite_concept_id=None,
                    requires_prerequisite_check=False,
                )

        # Pattern: Stationary point assumed always extremum without sign check
        if "DERIVATIVE_ZERO_ALWAYS_EXTREMUM" in defs_by_code:
            d = defs_by_code["DERIVATIVE_ZERO_ALWAYS_EXTREMUM"]
            ans_clean = student_answer.lower()
            if (
                ("y' = 0" in ans_clean or "f'(x) = 0" in ans_clean)
                and ("luôn là cực trị" in ans_clean or "nên là cực trị" in ans_clean or "chắc chắn là điểm cực" in ans_clean)
            ):
                return MisconceptionAnalysisOutput(
                    concept_id=d.concept_id,
                    problem_type_id=d.problem_type_id,
                    misconception_code=d.code,
                    error_category=d.category,
                    first_wrong_step="Assumed f'(x)=0 is sufficient for extremum without verifying sign change.",
                    confidence=0.95,
                    possible_prerequisite_concept_id=None,
                    requires_prerequisite_check=False,
                )

        return None
