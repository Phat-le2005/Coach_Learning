from datetime import datetime, timezone
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.mastery.strategy import (
    AttemptEvidence,
    DeterministicMasteryCalculationStrategy,
    MappingEvidence,
    MasteryCalculationStrategy,
    MasteryState,
    QuestionEvidence,
)
from app.practice.evidence import AttemptEvaluatedEvidence
from app.practice.models import QuestionAttempt
from app.questions.models import Question
from app.students.models import StudentProfile

logger = logging.getLogger(__name__)


class MasteryAttemptEvidencePublisher:
    """Project one evaluated attempt into concept and problem-type mastery rows."""

    def __init__(self, strategy: MasteryCalculationStrategy | None = None) -> None:
        self.strategy = strategy or DeterministicMasteryCalculationStrategy()

    def publish(self, evidence: AttemptEvaluatedEvidence, session: Session) -> None:
        # A per-student lock serializes updates even when two sessions finish concurrently.
        student_id = session.scalar(
            select(StudentProfile.id)
            .where(StudentProfile.id == evidence.student_id)
            .with_for_update()
        )
        if student_id is None:
            raise RuntimeError("Mastery evidence references a missing student")

        attempt = session.get(QuestionAttempt, evidence.attempt_id)
        question = session.scalar(
            select(Question)
            .options(
                selectinload(Question.concept_links),
                selectinload(Question.problem_type_links),
            )
            .where(Question.id == evidence.question_id)
        )
        if attempt is None or question is None:
            raise RuntimeError("Mastery evidence references missing attempt data")
        if attempt.student_id != evidence.student_id or attempt.question_id != question.id:
            raise RuntimeError("Mastery evidence does not match the stored attempt")

        attempt_evidence = AttemptEvidence(
            is_correct=evidence.is_correct,
            score=evidence.score,
            hint_count=attempt.hint_count,
            response_time_seconds=attempt.response_time_seconds,
        )
        question_evidence = QuestionEvidence(difficulty=question.difficulty)

        for link in question.concept_links:
            row = session.scalar(
                select(StudentConceptMastery)
                .where(
                    StudentConceptMastery.student_id == evidence.student_id,
                    StudentConceptMastery.concept_id == link.concept_id,
                )
                .with_for_update()
            )
            next_state = self.strategy.calculate_from_attempt(
                self._state(row),
                question_evidence,
                MappingEvidence(weight=link.weight),
                attempt_evidence,
            )
            if row is None:
                row = StudentConceptMastery(
                    student_id=evidence.student_id,
                    concept_id=link.concept_id,
                    mastery_score=next_state.mastery_score,
                    confidence=next_state.confidence,
                    attempt_count=next_state.attempt_count,
                    correct_count=next_state.correct_count,
                    last_practiced_at=evidence.occurred_at,
                    last_updated_at=datetime.now(timezone.utc),
                )
                session.add(row)
            else:
                self._apply(row, next_state, evidence.occurred_at)

        for link in question.problem_type_links:
            row = session.scalar(
                select(StudentProblemTypeMastery)
                .where(
                    StudentProblemTypeMastery.student_id == evidence.student_id,
                    StudentProblemTypeMastery.problem_type_id == link.problem_type_id,
                )
                .with_for_update()
            )
            next_state = self.strategy.calculate_from_attempt(
                self._state(row),
                question_evidence,
                MappingEvidence(weight=link.weight if link.weight is not None else 1.0),
                attempt_evidence,
            )
            if row is None:
                row = StudentProblemTypeMastery(
                    student_id=evidence.student_id,
                    problem_type_id=link.problem_type_id,
                    mastery_score=next_state.mastery_score,
                    confidence=next_state.confidence,
                    attempt_count=next_state.attempt_count,
                    correct_count=next_state.correct_count,
                    last_practiced_at=evidence.occurred_at,
                    last_updated_at=datetime.now(timezone.utc),
                )
                session.add(row)
            else:
                self._apply(row, next_state, evidence.occurred_at)

        session.flush()
        logger.info(
            "Mastery evidence applied (attempt_id=%s, concepts=%d, problem_types=%d)",
            evidence.attempt_id,
            len(question.concept_links),
            len(question.problem_type_links),
        )

    @staticmethod
    def _state(
        row: StudentConceptMastery | StudentProblemTypeMastery | None,
    ) -> MasteryState:
        if row is None:
            return MasteryState()
        return MasteryState(
            mastery_score=row.mastery_score,
            confidence=row.confidence,
            attempt_count=row.attempt_count,
            correct_count=row.correct_count,
        )

    @staticmethod
    def _apply(
        row: StudentConceptMastery | StudentProblemTypeMastery,
        state: MasteryState,
        practiced_at: datetime,
    ) -> None:
        row.mastery_score = state.mastery_score
        row.confidence = state.confidence
        row.attempt_count = state.attempt_count
        row.correct_count = state.correct_count
        row.last_practiced_at = _latest(row.last_practiced_at, practiced_at)
        row.last_updated_at = datetime.now(timezone.utc)


def _latest(current: datetime, candidate: datetime) -> datetime:
    current_aware = current if current.tzinfo is not None else current.replace(tzinfo=timezone.utc)
    candidate_aware = (
        candidate if candidate.tzinfo is not None else candidate.replace(tzinfo=timezone.utc)
    )
    return candidate if candidate_aware >= current_aware else current

