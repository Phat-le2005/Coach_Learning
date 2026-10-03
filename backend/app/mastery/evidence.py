from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import ConceptRelation, RelationType
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.mastery.strategy import AttemptEvidence, DeterministicMasteryCalculationStrategy, MappingEvidence, MasteryCalculationStrategy, MasteryState, QuestionEvidence
from app.practice.evidence import AttemptEvaluatedEvidence
from app.practice.models import QuestionAttempt
from app.questions.models import Question
from app.review.models import ReviewSchedule
from app.review.service import ReviewScheduleService
from app.students.models import StudentProfile


@dataclass(frozen=True, slots=True)
class WeightedConceptEvidence:
    concept_id: UUID
    weight: float


@dataclass(frozen=True, slots=True)
class WeightedProblemTypeEvidence:
    problem_type_id: UUID
    weight: float
    is_primary: bool = False


@dataclass(frozen=True, slots=True)
class GenericMasteryEvidence:
    student_id: UUID
    is_correct: bool
    score: float
    difficulty: float
    response_time_seconds: float | None
    hint_count: int
    occurred_at: datetime
    concepts: tuple[WeightedConceptEvidence, ...]
    problem_types: tuple[WeightedProblemTypeEvidence, ...]


class DeterministicMasteryEvidencePublisher:
    """Apply evaluated evidence using the existing replaceable mastery strategy."""
    def __init__(self, strategy: MasteryCalculationStrategy | None = None) -> None:
        self.strategy = strategy or DeterministicMasteryCalculationStrategy()

    def publish(self, evidence: GenericMasteryEvidence, session: Session) -> None:
        if session.scalar(select(StudentProfile.id).where(StudentProfile.id == evidence.student_id).with_for_update()) is None:
            raise RuntimeError("Mastery evidence references a missing student")
        attempt = AttemptEvidence(is_correct=evidence.is_correct, score=evidence.score, hint_count=evidence.hint_count, response_time_seconds=evidence.response_time_seconds)
        question = QuestionEvidence(difficulty=evidence.difficulty)
        reviews = ReviewScheduleService(session)
        for mapping in evidence.concepts:
            row = session.scalar(select(StudentConceptMastery).where(StudentConceptMastery.student_id == evidence.student_id, StudentConceptMastery.concept_id == mapping.concept_id).with_for_update())
            state = self.strategy.calculate_from_attempt(self._state(row), question, MappingEvidence(weight=mapping.weight), attempt)
            if row is None:
                row = StudentConceptMastery(student_id=evidence.student_id, concept_id=mapping.concept_id, mastery_score=state.mastery_score, confidence=state.confidence, attempt_count=state.attempt_count, correct_count=state.correct_count, last_practiced_at=evidence.occurred_at, last_updated_at=datetime.now(timezone.utc)); session.add(row)
            else:
                self._apply(row, state, evidence.occurred_at)
            if state.mastery_score >= .8 and state.confidence >= .65 and session.scalar(select(ConceptRelation.id).where(ConceptRelation.source_concept_id == mapping.concept_id, ConceptRelation.relation_type == RelationType.PREREQUISITE).limit(1)) is not None:
                reviews.ensure_concept_schedule(evidence.student_id, mapping.concept_id, as_of=evidence.occurred_at)
            schedule = session.scalar(select(ReviewSchedule).where(ReviewSchedule.student_id == evidence.student_id, ReviewSchedule.concept_id == mapping.concept_id))
            if schedule is not None and _is_due(schedule.next_review_at, evidence.occurred_at):
                reviews.record_performance(evidence.student_id, target_concept_id=mapping.concept_id, score=evidence.score, is_correct=evidence.is_correct, as_of=evidence.occurred_at)
        for mapping in evidence.problem_types:
            row = session.scalar(select(StudentProblemTypeMastery).where(StudentProblemTypeMastery.student_id == evidence.student_id, StudentProblemTypeMastery.problem_type_id == mapping.problem_type_id).with_for_update())
            state = self.strategy.calculate_from_attempt(self._state(row), question, MappingEvidence(weight=mapping.weight), attempt)
            if row is None:
                row = StudentProblemTypeMastery(student_id=evidence.student_id, problem_type_id=mapping.problem_type_id, mastery_score=state.mastery_score, confidence=state.confidence, attempt_count=state.attempt_count, correct_count=state.correct_count, last_practiced_at=evidence.occurred_at, last_updated_at=datetime.now(timezone.utc)); session.add(row)
            else:
                self._apply(row, state, evidence.occurred_at)
            if state.mastery_score >= .8 and state.confidence >= .65:
                reviews.ensure_problem_type_schedule(evidence.student_id, mapping.problem_type_id, as_of=evidence.occurred_at)
            schedule = session.scalar(select(ReviewSchedule).where(ReviewSchedule.student_id == evidence.student_id, ReviewSchedule.problem_type_id == mapping.problem_type_id))
            if schedule is not None and _is_due(schedule.next_review_at, evidence.occurred_at):
                reviews.record_performance(evidence.student_id, target_problem_type_id=mapping.problem_type_id, score=evidence.score, is_correct=evidence.is_correct, as_of=evidence.occurred_at)
        session.flush()

    @staticmethod
    def _state(row: StudentConceptMastery | StudentProblemTypeMastery | None) -> MasteryState:
        return MasteryState() if row is None else MasteryState(mastery_score=row.mastery_score, confidence=row.confidence, attempt_count=row.attempt_count, correct_count=row.correct_count)

    @staticmethod
    def _apply(row: StudentConceptMastery | StudentProblemTypeMastery, state: MasteryState, practiced_at: datetime) -> None:
        row.mastery_score, row.confidence, row.attempt_count, row.correct_count = state.mastery_score, state.confidence, state.attempt_count, state.correct_count
        row.last_practiced_at = _latest(row.last_practiced_at, practiced_at)
        row.last_updated_at = datetime.now(timezone.utc)


class MasteryAttemptEvidencePublisher:
    """Compatibility adapter for the public practice publisher API."""
    def __init__(self, strategy: MasteryCalculationStrategy | None = None) -> None:
        self.strategy = strategy or DeterministicMasteryCalculationStrategy()

    def publish(self, evidence: AttemptEvaluatedEvidence, session: Session) -> None:
        attempt = session.get(QuestionAttempt, evidence.attempt_id)
        question = session.scalar(select(Question).options(selectinload(Question.concept_links), selectinload(Question.problem_type_links)).where(Question.id == evidence.question_id))
        if attempt is None or question is None or attempt.student_id != evidence.student_id:
            raise RuntimeError("Mastery evidence references missing or inconsistent attempt data")
        from app.learning_evidence.models import LearningEvidenceSourceKind
        from app.learning_evidence.publisher import LearningEvidencePayload, LearningEvidencePublisher
        LearningEvidencePublisher(self.strategy).publish(LearningEvidencePayload(student_id=evidence.student_id, subject_id=evidence.subject_id, source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION, source_entity_id=attempt.id, is_correct=evidence.is_correct, score=evidence.score, difficulty=question.difficulty, response_time_seconds=attempt.response_time_seconds, hint_count=attempt.hint_count, evaluation_status=attempt.evaluation_status, occurred_at=evidence.occurred_at, concepts=tuple(WeightedConceptEvidence(x.concept_id, x.weight) for x in question.concept_links), problem_types=tuple(WeightedProblemTypeEvidence(x.problem_type_id, x.weight or 1.0) for x in question.problem_type_links), metadata={"practice_session_id": str(evidence.practice_session_id), "question_id": str(question.id), **evidence.metadata}), session)


def _latest(current: datetime, candidate: datetime) -> datetime:
    a = current if current.tzinfo else current.replace(tzinfo=timezone.utc); b = candidate if candidate.tzinfo else candidate.replace(tzinfo=timezone.utc)
    return candidate if b >= a else current


def _is_due(next_review_at: datetime, occurred_at: datetime) -> bool:
    a = next_review_at if next_review_at.tzinfo else next_review_at.replace(tzinfo=timezone.utc); b = occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=timezone.utc)
    return a <= b
