"""Stable policy constants shared by validation and promotion."""

from app.question_validation.models import (
    MANUAL_CHECK_TYPES,
    REQUIRED_CHECK_TYPES,
    SYSTEM_CHECK_TYPES,
    QuestionValidationBatchStatus,
)

ACTIVE_BATCH_STATUSES = frozenset(
    {
        QuestionValidationBatchStatus.OPEN,
        QuestionValidationBatchStatus.IN_REVIEW,
        QuestionValidationBatchStatus.READY_FOR_PROMOTION,
    }
)

QUESTION_CREATION_ADVISORY_LOCK_KEY = "edums:question-import"
CANONICAL_TRUE_FALSE_ANSWERS = frozenset({"TRUE", "FALSE"})

__all__ = [
    "ACTIVE_BATCH_STATUSES",
    "CANONICAL_TRUE_FALSE_ANSWERS",
    "MANUAL_CHECK_TYPES",
    "QUESTION_CREATION_ADVISORY_LOCK_KEY",
    "REQUIRED_CHECK_TYPES",
    "SYSTEM_CHECK_TYPES",
]
