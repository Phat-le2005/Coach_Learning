from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class AttemptEvaluatedEvidence:
    attempt_id: UUID
    practice_session_id: UUID
    student_id: UUID
    question_id: UUID
    subject_id: UUID
    is_correct: bool
    score: float
    problem_type_ids: tuple[UUID, ...]
    concept_ids: tuple[UUID, ...]
    learning_outcome_ids: tuple[UUID, ...]
    occurred_at: datetime


class AttemptEvidencePublisher(Protocol):
    def publish(self, evidence: AttemptEvaluatedEvidence, session: Session) -> None:
        """Handle evidence inside the attempt transaction or raise to roll it back."""


class NoOpAttemptEvidencePublisher:
    """Explicit opt-out publisher for isolated callers that should store no projections."""

    def publish(self, evidence: AttemptEvaluatedEvidence, session: Session) -> None:
        return None
