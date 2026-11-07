"""Reference availability only; callers still enforce source approval and review."""
from __future__ import annotations

import re

SOLUTION_PRIMARY_SOURCE_TYPE = "PDF_HANDOFF_200"


def reference_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    # An image reference alone is not readable by a text-only grader.
    without_images = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    without_tags = re.sub(r"<[^>]*>", "", without_images)
    if not without_tags.strip():
        return None
    return value.strip()


def has_grading_reference(correct_answer: object, explanation: object) -> bool:
    return bool(reference_text(explanation) or reference_text(correct_answer))


def preferred_solution(explanation: object, correct_answer: object = None) -> str | None:
    return reference_text(explanation) or reference_text(correct_answer)
