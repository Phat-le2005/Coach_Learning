"""Content-bound grading capability for curated OCR questions (no schema change)."""
from hashlib import sha256
import json

from app.core.exceptions import ApplicationError
from app.math_solutions.numeric_reference import NUMERIC_PROFILE


OCR_SOURCE = "OCR_CURATED_PA2"
PROFILE = "cubic-monotonicity-v1"
TASKS = {"all_intervals", "inner_sum", "inner_width"}
CRITERION_CONCEPTS = {
    "ASSUMPTION": ["FUNCTION_DOMAIN"],
    "DERIVATIVE_CALCULATION": ["DERIVATIVE_RULES"],
    "ROOT_FINDING": ["SIGN_ANALYSIS"],
    "VARIATION_TABLE": ["SIGN_ANALYSIS"],
    "CONCLUSION": ["MONOTONICITY_CRITERION"],
}


def reference_digest(content: str, answer: str | None, explanation: str | None) -> str:
    return sha256(json.dumps([content, answer, explanation], ensure_ascii=False,
                            separators=(",", ":")).encode("utf-8")).hexdigest()


def profile_data(rubric) -> dict | None:
    criteria = rubric.criteria
    if not isinstance(criteria, dict) or "grading_profile" not in criteria:
        return None
    if not ((criteria.get("grading_profile") == PROFILE and criteria.get("task") in TASKS)
            or (criteria.get("grading_profile") == NUMERIC_PROFILE and criteria.get("task") in {"probability", "grouped_statistics", "definite_integral", "polynomial_extrema"})):
        raise ApplicationError(409, "GRADING_PROFILE_UNSUPPORTED", "Unsupported reviewed grading profile.")
    return criteria


def verify_reference(rubric, question) -> dict | None:
    profile = profile_data(rubric)
    if question.source_type == OCR_SOURCE and profile is None:
        raise ApplicationError(409, "GRADING_PROFILE_REQUIRED", "Curated OCR requires its reviewed rubric.")
    if profile and profile.get("reference_sha256") != reference_digest(question.content, question.correct_answer, question.explanation):
        raise ApplicationError(409, "GRADING_REFERENCE_CHANGED", "Review a new rubric after changing the problem or reference.")
    return profile
