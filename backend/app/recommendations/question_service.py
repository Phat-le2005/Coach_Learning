from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.questions.eligibility import standalone_question_only
from app.questions.models import CognitiveLevel, Question, QuestionStatus
from app.recommendations.mix import LearningMixConfig
from app.recommendations.priority_service import LearningPriorityService
from app.recommendations.schemas import (
    ActiveTeachingPlanContext,
    LearningPriorityRead,
    PriorityReasonCode,
    PriorityTargetType,
    QuestionRecommendationRead,
)
from app.practice.models import QuestionAttempt
from app.students.models import StudentProfile
from app.subjects.models import Subject


@dataclass(frozen=True, slots=True)
class _CandidateScore:
    question: Question
    total: float
    problem_type_match: float
    concept_match: float
    difficulty_fit: float
    cognitive_fit: float
    exam_relevance: float


class QuestionRecommendationService:
    RECENT_QUESTION_LIMIT = 20

    def __init__(self, session: Session) -> None:
        self.session = session

    def recommend(
        self,
        student_id: UUID,
        subject_id: UUID,
        *,
        target_problem_type_id: UUID | None = None,
        target_concept_id: UUID | None = None,
        desired_difficulty: float | None = None,
        active_teaching_plan: ActiveTeachingPlanContext | None = None,
    ) -> QuestionRecommendationRead | None:
        if self.session.get(StudentProfile, student_id) is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile was not found.")
        if self.session.get(Subject, subject_id) is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        self._validate_targets(subject_id, target_problem_type_id, target_concept_id)
        if desired_difficulty is not None and not 0.0 <= desired_difficulty <= 1.0:
            raise ApplicationError(
                422,
                "INVALID_DESIRED_DIFFICULTY",
                "Desired difficulty must be between 0 and 1.",
            )

        priorities = LearningPriorityService(self.session).get_priorities(
            student_id,
            subject_id,
            active_teaching_plan=active_teaching_plan,
        )
        selected_priority = self._select_priority(
            priorities, target_problem_type_id, target_concept_id
        )
        if target_problem_type_id is None and target_concept_id is None and selected_priority:
            target_problem_type_id = selected_priority.problem_type_id
            target_concept_id = selected_priority.concept_id
        reason = (
            selected_priority.reason_code
            if selected_priority is not None
            else PriorityReasonCode.DIFFICULTY_PROGRESSION
        )
        target_difficulty = (
            desired_difficulty
            if desired_difficulty is not None
            else self._target_difficulty(
                student_id,
                target_problem_type_id,
                target_concept_id,
                selected_priority,
            )
        )

        recent_question_ids = set(
            self.session.scalars(
                select(QuestionAttempt.question_id)
                .where(QuestionAttempt.student_id == student_id)
                .order_by(QuestionAttempt.created_at.desc(), QuestionAttempt.id.desc())
                .limit(self.RECENT_QUESTION_LIMIT)
            )
        )
        statement = (
            select(Question)
            .options(
                selectinload(Question.problem_type_links),
                selectinload(Question.concept_links),
                selectinload(Question.learning_outcome_links),
            )
            .where(
                Question.subject_id == subject_id,
                Question.status == QuestionStatus.APPROVED,
                standalone_question_only(),
                Question.problem_type_links.any(),
                Question.concept_links.any(),
                Question.learning_outcome_links.any(),
            )
        )
        if target_problem_type_id is not None:
            statement = statement.where(
                Question.problem_type_links.any(problem_type_id=target_problem_type_id)
            )
        if target_concept_id is not None:
            statement = statement.where(
                Question.concept_links.any(concept_id=target_concept_id)
            )
        if recent_question_ids:
            statement = statement.where(~Question.id.in_(recent_question_ids))
        questions = list(self.session.scalars(statement))
        if not questions:
            return None

        scored = [
            self._score(
                question,
                target_problem_type_id,
                target_concept_id,
                target_difficulty,
            )
            for question in questions
        ]
        winner = sorted(
            scored,
            key=lambda item: (
                -item.total,
                abs(item.question.difficulty - target_difficulty),
                str(item.question.id),
            ),
        )[0]
        return QuestionRecommendationRead(
            question_id=winner.question.id,
            target_problem_types=sorted(
                (link.problem_type_id for link in winner.question.problem_type_links),
                key=str,
            ),
            target_concepts=sorted(
                (link.concept_id for link in winner.question.concept_links), key=str
            ),
            difficulty=winner.question.difficulty,
            reason_code=reason,
        )

    def recommend_mixed_batch(
        self,
        student_id: UUID,
        subject_id: UUID,
        *,
        count: int = 5,
        mix_config: LearningMixConfig | None = None,
        active_teaching_plan: ActiveTeachingPlanContext | None = None,
    ) -> list[QuestionRecommendationRead]:
        if count < 1:
            raise ApplicationError(422, "INVALID_BATCH_COUNT", "Batch count must be positive.")

        priority_service = LearningPriorityService(self.session)
        mixed_priorities = priority_service.get_mixed_priorities(
            student_id,
            subject_id,
            total_count=count,
            mix_config=mix_config,
            active_teaching_plan=active_teaching_plan,
        )

        results: list[QuestionRecommendationRead] = []
        used_question_ids: set[UUID] = set()

        for priority in mixed_priorities:
            rec = self.recommend(
                student_id,
                subject_id,
                target_problem_type_id=priority.problem_type_id,
                target_concept_id=priority.concept_id,
                active_teaching_plan=active_teaching_plan,
            )
            if rec and rec.question_id not in used_question_ids:
                used_question_ids.add(rec.question_id)
                results.append(rec)

        return results

    def _validate_targets(
        self,
        subject_id: UUID,
        problem_type_id: UUID | None,
        concept_id: UUID | None,
    ) -> None:
        if problem_type_id is not None:
            owner_subject_id = self.session.scalar(
                select(Chapter.subject_id)
                .join(Topic, Topic.chapter_id == Chapter.id)
                .join(ProblemType, ProblemType.topic_id == Topic.id)
                .where(ProblemType.id == problem_type_id, ProblemType.is_active.is_(True))
            )
            if owner_subject_id is None:
                raise ApplicationError(
                    404, "PROBLEM_TYPE_NOT_FOUND", "Active ProblemType was not found."
                )
            if owner_subject_id != subject_id:
                raise ApplicationError(
                    422,
                    "PROBLEM_TYPE_SUBJECT_MISMATCH",
                    "ProblemType does not belong to the requested subject.",
                )
        if concept_id is not None:
            concept = self.session.get(Concept, concept_id)
            if concept is None:
                raise ApplicationError(404, "CONCEPT_NOT_FOUND", "Concept was not found.")
            if concept.subject_id != subject_id:
                raise ApplicationError(
                    422,
                    "CONCEPT_SUBJECT_MISMATCH",
                    "Concept does not belong to the requested subject.",
                )

    def _target_difficulty(
        self,
        student_id: UUID,
        problem_type_id: UUID | None,
        concept_id: UUID | None,
        selected_priority: LearningPriorityRead | None,
    ) -> float:
        if selected_priority is not None:
            return selected_priority.desired_difficulty
        mastery_values: list[float] = []
        if problem_type_id is not None:
            row = self.session.get(
                StudentProblemTypeMastery, (student_id, problem_type_id)
            )
            mastery_values.append(row.mastery_score if row else 0.0)
        if concept_id is not None:
            row = self.session.get(StudentConceptMastery, (student_id, concept_id))
            mastery_values.append(row.mastery_score if row else 0.0)
        mastery = min(mastery_values) if mastery_values else 0.0
        return LearningPriorityService.difficulty_for_mastery(mastery)

    @staticmethod
    def _select_priority(
        priorities: list[LearningPriorityRead],
        problem_type_id: UUID | None,
        concept_id: UUID | None,
    ) -> LearningPriorityRead | None:
        if problem_type_id is None and concept_id is None:
            return priorities[0] if priorities else None
        matches = [
            item
            for item in priorities
            if (problem_type_id is not None and item.problem_type_id == problem_type_id)
            or (concept_id is not None and item.concept_id == concept_id)
        ]
        return matches[0] if matches else None

    @staticmethod
    def _score(
        question: Question,
        problem_type_id: UUID | None,
        concept_id: UUID | None,
        desired_difficulty: float,
    ) -> _CandidateScore:
        problem_type_match = 0.0
        if problem_type_id is not None:
            for link in question.problem_type_links:
                if link.problem_type_id == problem_type_id:
                    problem_type_match = 0.35 * (
                        link.weight if link.weight is not None else 1.0
                    )
                    break
        concept_match = 0.0
        if concept_id is not None:
            for link in question.concept_links:
                if link.concept_id == concept_id:
                    concept_match = 0.25 * link.weight
                    break
        difficulty_fit = 0.3 * (1.0 - abs(question.difficulty - desired_difficulty))
        cognitive_fit = 0.1 if question.cognitive_level in _preferred_cognitive_levels(
            desired_difficulty
        ) else 0.0
        exam_relevance = 0.1 * question.exam_weight
        return _CandidateScore(
            question=question,
            total=round(
                problem_type_match
                + concept_match
                + difficulty_fit
                + cognitive_fit
                + exam_relevance,
                8,
            ),
            problem_type_match=problem_type_match,
            concept_match=concept_match,
            difficulty_fit=difficulty_fit,
            cognitive_fit=cognitive_fit,
            exam_relevance=exam_relevance,
        )


def _preferred_cognitive_levels(difficulty: float) -> set[CognitiveLevel]:
    if difficulty < 0.4:
        return {CognitiveLevel.REMEMBER, CognitiveLevel.UNDERSTAND}
    if difficulty < 0.7:
        return {CognitiveLevel.UNDERSTAND, CognitiveLevel.APPLY}
    return {CognitiveLevel.APPLY, CognitiveLevel.ANALYZE}
