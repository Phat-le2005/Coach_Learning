from datetime import datetime, timedelta, timezone
from enum import StrEnum


class DerivedMasteryState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    LEARNING = "LEARNING"
    WEAK = "WEAK"
    PRACTICING = "PRACTICING"
    MASTERED = "MASTERED"
    REVIEW_DUE = "REVIEW_DUE"


def derive_mastery_state(
    *,
    mastery_score: float,
    confidence: float,
    attempt_count: int,
    last_practiced_at: datetime | None,
    as_of: datetime | None = None,
) -> DerivedMasteryState:
    if attempt_count == 0:
        return DerivedMasteryState.NOT_STARTED

    if mastery_score >= 0.8 and confidence >= 0.65:
        if last_practiced_at is not None:
            reference = as_of or datetime.now(timezone.utc)
            practiced = last_practiced_at
            if reference.tzinfo is None and practiced.tzinfo is not None:
                reference = reference.replace(tzinfo=timezone.utc)
            if reference.tzinfo is not None and practiced.tzinfo is None:
                practiced = practiced.replace(tzinfo=timezone.utc)
            if reference - practiced >= timedelta(days=14):
                return DerivedMasteryState.REVIEW_DUE
        return DerivedMasteryState.MASTERED

    if mastery_score < 0.4 and confidence >= 0.25:
        return DerivedMasteryState.WEAK
    if attempt_count >= 3 or mastery_score >= 0.55:
        return DerivedMasteryState.PRACTICING
    return DerivedMasteryState.LEARNING
