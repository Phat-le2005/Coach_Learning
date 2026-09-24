from __future__ import annotations

from typing import Any


SUPPORTED_STAGING_QUESTION_TYPES = {
    "MULTIPLE_CHOICE",
    "TRUE_FALSE_GROUP",
    "SHORT_ANSWER",
}


def _supported_type(value: object) -> str | None:
    return (
        value
        if isinstance(value, str) and value in SUPPORTED_STAGING_QUESTION_TYPES
        else None
    )


def effective_question_type(candidate: dict[str, Any]) -> str | None:
    """Resolve a staging type without changing its immutable raw detection."""
    if "reviewed_question_type" in candidate:
        return _supported_type(candidate.get("reviewed_question_type"))

    review_record = candidate.get("review_record")
    if isinstance(review_record, dict) and "reviewed_question_type" in review_record:
        return _supported_type(review_record.get("reviewed_question_type"))

    return _supported_type(candidate.get("question_type_detected"))


def requires_question_group(candidate: dict[str, Any]) -> bool:
    """Return whether an effective candidate explicitly needs a group model."""
    review_record = candidate.get("review_record")
    return (
        effective_question_type(candidate) == "TRUE_FALSE_GROUP"
        or candidate.get("requires_question_group_model") is True
        or (
            isinstance(review_record, dict)
            and review_record.get("requires_question_group_model") is True
        )
    )
