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
    """Return whether the effective reviewed candidate needs a group model.

    A confirmed reviewed type supersedes the raw group marker because that marker was
    derived from the same initial type detection. Explicit review-record requirements
    remain authoritative.
    """
    review_record = candidate.get("review_record")
    resolved_type = effective_question_type(candidate)
    if resolved_type == "TRUE_FALSE_GROUP":
        return True
    if (
        isinstance(review_record, dict)
        and review_record.get("requires_question_group_model") is True
    ):
        return True
    has_confirmed_reviewed_type = resolved_type is not None and (
        "reviewed_question_type" in candidate
        or (
            isinstance(review_record, dict)
            and "reviewed_question_type" in review_record
        )
    )
    if has_confirmed_reviewed_type:
        return False
    return (
        candidate.get("question_type_detected") == "TRUE_FALSE_GROUP"
        or candidate.get("requires_question_group_model") is True
    )
