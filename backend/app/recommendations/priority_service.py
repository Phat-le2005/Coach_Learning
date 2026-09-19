from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.mastery.aggregation import MasteryAggregationService
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.mastery.state import DerivedMasteryState
from app.practice.models import PracticeSession, PracticeSessionType, QuestionAttempt
from app.questions.models import Question, QuestionConcept, QuestionProblemType, QuestionStatus
from app.recommendations.schemas import (
    AcademicGoalContext,
    ActiveTeachingPlanContext,
    LearningPriorityRead,
    PriorityReasonCode,
    PriorityTargetType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject


@dataclass(frozen=True, slots=True)
class _PriorityCandidate:
    target_type: PriorityTargetType
    target_id: UUID
    reason_code: PriorityReasonCode
    score: float
    mastery_score: float
    confidence: float
    desired_difficulty: float


class LearningPriorityService:
    """Rank deterministic leaf learning targets from current relational evidence."""

    _REASON_BASE = {
        PriorityReasonCode.PREREQUISITE_REPAIR: 100.0,
        PriorityReasonCode.CURRENT_LESSON: 95.0,
        PriorityReasonCode.REVIEW_DUE: 90.0,
        PriorityReasonCode.DIAGNOSTIC_FOLLOWUP: 85.0,
        PriorityReasonCode.WEAK_PROBLEM_TYPE: 80.0,
        PriorityReasonCode.WEAK_CONCEPT: 75.0,
        PriorityReasonCode.DIFFICULTY_PROGRESSION: 50.0,
    }

    def __init__(self, session: Session) -> None:
        self.session = session
        self.aggregation = MasteryAggregationService(session)

    def get_priorities(
        self,
        student_id: UUID,
        subject_id: UUID,
        active_teaching_plan: ActiveTeachingPlanContext | None = None,
        academic_goal: AcademicGoalContext | None = None,
        *,
        limit: int = 20,
    ) -> list[LearningPriorityRead]:
        if limit < 1:
            raise ApplicationError(422, "INVALID_PRIORITY_LIMIT", "Priority limit must be positive.")
        if self.session.get(StudentProfile, student_id) is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile was not found.")
        if self.session.get(Subject, subject_id) is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")

        problem_types = list(
            self.session.scalars(
                select(ProblemType)
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .where(Chapter.subject_id == subject_id, ProblemType.is_active.is_(True))
                .order_by(ProblemType.order_index, ProblemType.code, ProblemType.id)
            )
        )
        problem_type_ids = {item.id for item in problem_types}
        concepts = list(
            self.session.scalars(
                select(Concept)
                .where(Concept.subject_id == subject_id)
                .order_by(Concept.order_index, Concept.code, Concept.id)
            )
        )
        concept_ids = {item.id for item in concepts}
        self._validate_context_ids(
            problem_type_ids,
            active_teaching_plan,
            academic_goal,
        )

        problem_mastery = {
            item.problem_type_id: item
            for item in self.session.scalars(
                select(StudentProblemTypeMastery).where(
                    StudentProblemTypeMastery.student_id == student_id,
                    StudentProblemTypeMastery.problem_type_id.in_(problem_type_ids),
                )
            )
        }
        concept_mastery = {
            item.concept_id: item
            for item in self.session.scalars(
                select(StudentConceptMastery).where(
                    StudentConceptMastery.student_id == student_id,
                    StudentConceptMastery.concept_id.in_(concept_ids),
                )
            )
        }
        mappings = list(
            self.session.execute(
                select(ProblemTypeConcept.problem_type_id, ProblemTypeConcept.concept_id)
                .where(ProblemTypeConcept.problem_type_id.in_(problem_type_ids))
            )
        )
        mapped_concept_ids = {concept_id for _, concept_id in mappings}
        prerequisite_edges = list(
            self.session.execute(
                select(
                    ConceptRelation.source_concept_id,
                    ConceptRelation.target_concept_id,
                ).where(
                    ConceptRelation.relation_type == RelationType.PREREQUISITE,
                    ConceptRelation.target_concept_id.in_(mapped_concept_ids),
                )
            )
        )
        exam_relevance_pt, exam_relevance_concept = self._exam_relevance(
            subject_id, problem_type_ids, concept_ids
        )
        diagnostic_problem_types, diagnostic_concepts = self._diagnostic_followup(
            student_id, subject_id
        )
        active_ids = set(active_teaching_plan.problem_type_ids) if active_teaching_plan else set()
        goal_ids = set(academic_goal.target_problem_type_ids) if academic_goal else set()
        exam_multiplier = academic_goal.exam_relevance_multiplier if academic_goal else 1.0
        if not 0.0 <= exam_multiplier <= 3.0:
            raise ApplicationError(
                422,
                "INVALID_EXAM_RELEVANCE_MULTIPLIER",
                "Exam relevance multiplier must be between 0 and 3.",
            )

        candidates: dict[tuple[PriorityTargetType, UUID], _PriorityCandidate] = {}
        for problem_type in problem_types:
            snapshot = self.aggregation.snapshot(problem_mastery.get(problem_type.id))
            reason = self._problem_type_reason(
                problem_type.id,
                snapshot.state,
                active_ids,
                diagnostic_problem_types,
            )
            goal_boost = 15.0 if problem_type.id in goal_ids else 0.0
            relevance = exam_relevance_pt.get(problem_type.id, 0.0) * 10.0 * exam_multiplier
            severity = (1.0 - snapshot.mastery_score) * snapshot.confidence * 20.0
            self._consider(
                candidates,
                _PriorityCandidate(
                    target_type=PriorityTargetType.PROBLEM_TYPE,
                    target_id=problem_type.id,
                    reason_code=reason,
                    score=self._REASON_BASE[reason] + severity + relevance + goal_boost,
                    mastery_score=snapshot.mastery_score,
                    confidence=snapshot.confidence,
                    desired_difficulty=self.difficulty_for_mastery(snapshot.mastery_score),
                ),
            )

        prerequisite_ids = {source_id for source_id, _ in prerequisite_edges}
        for concept in concepts:
            snapshot = self.aggregation.snapshot(concept_mastery.get(concept.id))
            reason: PriorityReasonCode | None = None
            if concept.id in prerequisite_ids and snapshot.state in {
                DerivedMasteryState.WEAK,
                DerivedMasteryState.LEARNING,
                DerivedMasteryState.NOT_STARTED,
            }:
                reason = PriorityReasonCode.PREREQUISITE_REPAIR
            elif snapshot.state == DerivedMasteryState.REVIEW_DUE:
                reason = PriorityReasonCode.REVIEW_DUE
            elif concept.id in diagnostic_concepts:
                reason = PriorityReasonCode.DIAGNOSTIC_FOLLOWUP
            elif snapshot.state == DerivedMasteryState.WEAK:
                reason = PriorityReasonCode.WEAK_CONCEPT
            if reason is None:
                continue
            relevance = exam_relevance_concept.get(concept.id, 0.0) * 10.0 * exam_multiplier
            severity = (1.0 - snapshot.mastery_score) * max(snapshot.confidence, 0.25) * 20.0
            self._consider(
                candidates,
                _PriorityCandidate(
                    target_type=PriorityTargetType.CONCEPT,
                    target_id=concept.id,
                    reason_code=reason,
                    score=self._REASON_BASE[reason] + severity + relevance,
                    mastery_score=snapshot.mastery_score,
                    confidence=snapshot.confidence,
                    desired_difficulty=self.difficulty_for_mastery(snapshot.mastery_score),
                ),
            )

        ranked = sorted(
            candidates.values(),
            key=lambda item: (-item.score, item.target_type.value, str(item.target_id)),
        )[:limit]
        return [self._to_read(item) for item in ranked]

    @staticmethod
    def difficulty_for_mastery(mastery_score: float) -> float:
        if mastery_score < 0.4:
            return 0.3
        if mastery_score < 0.75:
            return 0.55
        return 0.8

    def _exam_relevance(
        self,
        subject_id: UUID,
        problem_type_ids: set[UUID],
        concept_ids: set[UUID],
    ) -> tuple[dict[UUID, float], dict[UUID, float]]:
        problem_rows = self.session.execute(
            select(QuestionProblemType.problem_type_id, func.max(Question.exam_weight))
            .join(Question, Question.id == QuestionProblemType.question_id)
            .where(
                Question.subject_id == subject_id,
                Question.status == QuestionStatus.APPROVED,
                QuestionProblemType.problem_type_id.in_(problem_type_ids),
            )
            .group_by(QuestionProblemType.problem_type_id)
        )
        concept_rows = self.session.execute(
            select(QuestionConcept.concept_id, func.max(Question.exam_weight))
            .join(Question, Question.id == QuestionConcept.question_id)
            .where(
                Question.subject_id == subject_id,
                Question.status == QuestionStatus.APPROVED,
                QuestionConcept.concept_id.in_(concept_ids),
            )
            .group_by(QuestionConcept.concept_id)
        )
        return (
            {item_id: float(weight) for item_id, weight in problem_rows},
            {item_id: float(weight) for item_id, weight in concept_rows},
        )

    def _diagnostic_followup(
        self, student_id: UUID, subject_id: UUID
    ) -> tuple[set[UUID], set[UUID]]:
        question_ids = set(
            self.session.scalars(
                select(QuestionAttempt.question_id)
                .join(
                    PracticeSession,
                    PracticeSession.id == QuestionAttempt.practice_session_id,
                )
                .join(Question, Question.id == QuestionAttempt.question_id)
                .where(
                    QuestionAttempt.student_id == student_id,
                    QuestionAttempt.is_correct.is_(False),
                    PracticeSession.session_type == PracticeSessionType.DIAGNOSTIC,
                    Question.subject_id == subject_id,
                )
                .order_by(QuestionAttempt.created_at.desc())
                .limit(20)
            )
        )
        if not question_ids:
            return set(), set()
        return (
            set(
                self.session.scalars(
                    select(QuestionProblemType.problem_type_id).where(
                        QuestionProblemType.question_id.in_(question_ids)
                    )
                )
            ),
            set(
                self.session.scalars(
                    select(QuestionConcept.concept_id).where(
                        QuestionConcept.question_id.in_(question_ids)
                    )
                )
            ),
        )

    @staticmethod
    def _problem_type_reason(
        problem_type_id: UUID,
        state: DerivedMasteryState,
        active_ids: set[UUID],
        diagnostic_ids: set[UUID],
    ) -> PriorityReasonCode:
        if problem_type_id in active_ids:
            return PriorityReasonCode.CURRENT_LESSON
        if state == DerivedMasteryState.REVIEW_DUE:
            return PriorityReasonCode.REVIEW_DUE
        if problem_type_id in diagnostic_ids:
            return PriorityReasonCode.DIAGNOSTIC_FOLLOWUP
        if state == DerivedMasteryState.WEAK:
            return PriorityReasonCode.WEAK_PROBLEM_TYPE
        return PriorityReasonCode.DIFFICULTY_PROGRESSION

    @staticmethod
    def _validate_context_ids(
        valid_problem_type_ids: set[UUID],
        active_plan: ActiveTeachingPlanContext | None,
        academic_goal: AcademicGoalContext | None,
    ) -> None:
        supplied = set(active_plan.problem_type_ids) if active_plan else set()
        supplied.update(academic_goal.target_problem_type_ids if academic_goal else ())
        if not supplied.issubset(valid_problem_type_ids):
            raise ApplicationError(
                422,
                "PRIORITY_CONTEXT_SUBJECT_MISMATCH",
                "Priority context contains a ProblemType outside the requested subject.",
            )

    @staticmethod
    def _consider(
        candidates: dict[tuple[PriorityTargetType, UUID], _PriorityCandidate],
        candidate: _PriorityCandidate,
    ) -> None:
        key = (candidate.target_type, candidate.target_id)
        existing = candidates.get(key)
        if existing is None or candidate.score > existing.score:
            candidates[key] = candidate

    @staticmethod
    def _to_read(item: _PriorityCandidate) -> LearningPriorityRead:
        return LearningPriorityRead(
            target_type=item.target_type,
            problem_type_id=(
                item.target_id if item.target_type == PriorityTargetType.PROBLEM_TYPE else None
            ),
            concept_id=(
                item.target_id if item.target_type == PriorityTargetType.CONCEPT else None
            ),
            reason_code=item.reason_code,
            priority_score=round(item.score, 6),
            mastery_score=item.mastery_score,
            confidence=item.confidence,
            desired_difficulty=item.desired_difficulty,
        )

