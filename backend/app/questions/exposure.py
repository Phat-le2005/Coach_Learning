"""Tracking canonical question exposure and root-cause source question resolution."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import AssignmentStudentQuestion
from app.knowledge_gap.models import RootCauseDiagnosis
from app.learning_evidence.models import (
    LearningEvidenceEvent,
    LearningEvidenceSourceKind,
)
from app.practice.models import QuestionAttempt


class QuestionExposureService:
    """Track canonical question repetition and resolve diagnosis source questions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_recent_exposed_question_ids(
        self,
        student_id: UUID,
        limit: int = 20,
    ) -> set[UUID]:
        """Collect recent canonical question IDs attempted by or assigned to the student.

        Pulls from:
        - QuestionAttempt (direct practice attempts)
        - LearningEvidenceEvent where source_kind is PRACTICE_QUESTION or
          ASSIGNMENT_CANONICAL_QUESTION.
        Teacher material items do not link to canonical questions and are excluded.
        """
        exposed: set[UUID] = set()

        # 1. Direct QuestionAttempt records
        attempt_qids = self.session.scalars(
            select(QuestionAttempt.question_id)
            .where(QuestionAttempt.student_id == student_id)
            .order_by(QuestionAttempt.created_at.desc(), QuestionAttempt.id.desc())
            .limit(limit)
        ).all()
        exposed.update(attempt_qids)

        # 2. Canonical questions recorded via LearningEvidenceEvent
        evidence_events = self.session.scalars(
            select(LearningEvidenceEvent)
            .where(
                LearningEvidenceEvent.student_id == student_id,
                LearningEvidenceEvent.source_kind.in_(
                    [
                        LearningEvidenceSourceKind.PRACTICE_QUESTION,
                        LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION,
                    ]
                ),
            )
            .order_by(
                LearningEvidenceEvent.occurred_at.desc(),
                LearningEvidenceEvent.id.desc(),
            )
            .limit(limit)
        ).all()

        for ev in evidence_events:
            if ev.source_kind == LearningEvidenceSourceKind.PRACTICE_QUESTION:
                attempt = self.session.get(QuestionAttempt, ev.source_entity_id)
                if attempt is not None:
                    exposed.add(attempt.question_id)
            elif ev.source_kind == LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION:
                asq = self.session.get(AssignmentStudentQuestion, ev.source_entity_id)
                if asq is not None:
                    exposed.add(asq.question_id)

        return exposed

    def get_diagnosis_source_question_id(
        self,
        diagnosis: RootCauseDiagnosis,
    ) -> UUID | None:
        """Resolve the source canonical question ID for a root cause diagnosis.

        If the evidence event originated from a canonical QuestionAttempt or
        AssignmentStudentQuestion, returns the Question.id. If from teacher material
        item or unknown, returns None.
        """
        if not diagnosis.learning_evidence_event_id:
            return None

        event = self.session.get(LearningEvidenceEvent, diagnosis.learning_evidence_event_id)
        if event is None:
            return None

        if event.source_kind == LearningEvidenceSourceKind.PRACTICE_QUESTION:
            attempt = self.session.get(QuestionAttempt, event.source_entity_id)
            return attempt.question_id if attempt is not None else None

        if event.source_kind == LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION:
            asq = self.session.get(AssignmentStudentQuestion, event.source_entity_id)
            return asq.question_id if asq is not None else None

        return None
