from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.diagnostics.models import DiagnosticSelectionReason
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.models import QuestionAttempt
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)


@dataclass(frozen=True, slots=True)
class DiagnosticQuestionSelection:
    question: Question
    target_problem_type_id: UUID | None
    target_concept_id: UUID | None
    desired_difficulty: float
    reason: DiagnosticSelectionReason


class DiagnosticQuestionSelector:
    AUTO_EVALUATED_TYPES = (
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.SHORT_ANSWER,
    )

    def __init__(self, session: Session) -> None:
        self.session = session

    def select_next(
        self,
        *,
        practice_session_id: UUID,
        student_id: UUID,
        subject_id: UUID,
        blueprint_problem_type_ids: list[UUID],
    ) -> DiagnosticQuestionSelection | None:
        attempts = list(
            self.session.scalars(
                select(QuestionAttempt)
                .where(QuestionAttempt.practice_session_id == practice_session_id)
                .order_by(QuestionAttempt.attempt_number, QuestionAttempt.id)
            )
        )
        attempted_question_ids = {item.question_id for item in attempts}
        latest = attempts[-1] if attempts else None
        desired_difficulty = self._adapted_difficulty(latest)

        if latest is not None and latest.is_correct is False:
            prerequisite = self._prerequisite_selection(
                student_id=student_id,
                subject_id=subject_id,
                failed_question_id=latest.question_id,
                attempted_question_ids=attempted_question_ids,
                desired_difficulty=min(0.4, desired_difficulty),
            )
            if prerequisite is not None:
                return prerequisite

        covered = set(
            self.session.scalars(
                select(QuestionProblemType.problem_type_id)
                .join(
                    QuestionAttempt,
                    QuestionAttempt.question_id == QuestionProblemType.question_id,
                )
                .where(
                    QuestionAttempt.practice_session_id == practice_session_id,
                    QuestionProblemType.problem_type_id.in_(blueprint_problem_type_ids),
                )
                .distinct()
            )
        )
        uncovered = [item_id for item_id in blueprint_problem_type_ids if item_id not in covered]
        if uncovered:
            targets = uncovered
            reason = DiagnosticSelectionReason.BLUEPRINT_COVERAGE
        else:
            confidence = {
                item.problem_type_id: item.confidence
                for item in self.session.scalars(
                    select(StudentProblemTypeMastery).where(
                        StudentProblemTypeMastery.student_id == student_id,
                        StudentProblemTypeMastery.problem_type_id.in_(
                            blueprint_problem_type_ids
                        ),
                    )
                )
            }
            order = {item_id: index for index, item_id in enumerate(blueprint_problem_type_ids)}
            targets = sorted(
                blueprint_problem_type_ids,
                key=lambda item_id: (
                    confidence.get(item_id, 0.0),
                    order[item_id],
                    str(item_id),
                ),
            )
            reason = DiagnosticSelectionReason.CONFIDENCE_REFINEMENT

        for problem_type_id in targets:
            question = self._question(
                subject_id=subject_id,
                desired_difficulty=desired_difficulty,
                attempted_question_ids=attempted_question_ids,
                problem_type_id=problem_type_id,
            )
            if question is not None:
                return DiagnosticQuestionSelection(
                    question=question,
                    target_problem_type_id=problem_type_id,
                    target_concept_id=None,
                    desired_difficulty=desired_difficulty,
                    reason=reason,
                )
        return None

    def _prerequisite_selection(
        self,
        *,
        student_id: UUID,
        subject_id: UUID,
        failed_question_id: UUID,
        attempted_question_ids: set[UUID],
        desired_difficulty: float,
    ) -> DiagnosticQuestionSelection | None:
        failed_concept_ids = set(
            self.session.scalars(
                select(QuestionConcept.concept_id).where(
                    QuestionConcept.question_id == failed_question_id
                )
            )
        )
        if not failed_concept_ids:
            return None
        prerequisites = list(
            self.session.scalars(
                select(Concept)
                .join(
                    ConceptRelation,
                    Concept.id == ConceptRelation.source_concept_id,
                )
                .where(
                    ConceptRelation.relation_type == RelationType.PREREQUISITE,
                    ConceptRelation.target_concept_id.in_(failed_concept_ids),
                    Concept.subject_id == subject_id,
                )
                .order_by(Concept.order_index, Concept.code, Concept.id)
            )
        )
        if not prerequisites:
            return None
        mastery = {
            item.concept_id: item.mastery_score
            for item in self.session.scalars(
                select(StudentConceptMastery).where(
                    StudentConceptMastery.student_id == student_id,
                    StudentConceptMastery.concept_id.in_(
                        {item.id for item in prerequisites}
                    ),
                )
            )
        }
        prerequisites.sort(
            key=lambda item: (
                mastery.get(item.id, 0.0),
                item.order_index if item.order_index is not None else 2**31,
                item.code,
                str(item.id),
            )
        )
        for concept in prerequisites:
            question = self._question(
                subject_id=subject_id,
                desired_difficulty=desired_difficulty,
                attempted_question_ids=attempted_question_ids,
                concept_id=concept.id,
            )
            if question is not None:
                return DiagnosticQuestionSelection(
                    question=question,
                    target_problem_type_id=None,
                    target_concept_id=concept.id,
                    desired_difficulty=desired_difficulty,
                    reason=DiagnosticSelectionReason.PREREQUISITE_CHECK,
                )
        return None

    def _question(
        self,
        *,
        subject_id: UUID,
        desired_difficulty: float,
        attempted_question_ids: set[UUID],
        problem_type_id: UUID | None = None,
        concept_id: UUID | None = None,
    ) -> Question | None:
        statement = (
            select(Question)
            .options(
                selectinload(Question.options),
                selectinload(Question.problem_type_links),
                selectinload(Question.concept_links),
                selectinload(Question.learning_outcome_links),
            )
            .where(
                Question.subject_id == subject_id,
                Question.status == QuestionStatus.APPROVED,
                Question.question_type.in_(self.AUTO_EVALUATED_TYPES),
                Question.problem_type_links.any(),
                Question.concept_links.any(),
                Question.learning_outcome_links.any(),
            )
            .order_by(
                func.abs(Question.difficulty - desired_difficulty),
                Question.exam_weight.desc(),
                Question.id,
            )
        )
        if attempted_question_ids:
            statement = statement.where(~Question.id.in_(attempted_question_ids))
        if problem_type_id is not None:
            statement = statement.where(
                Question.problem_type_links.any(problem_type_id=problem_type_id)
            )
        if concept_id is not None:
            statement = statement.where(
                Question.concept_links.any(concept_id=concept_id)
            )
        return self.session.scalar(statement.limit(1))

    def _adapted_difficulty(self, latest: QuestionAttempt | None) -> float:
        if latest is None:
            return 0.55
        previous_difficulty = self.session.scalar(
            select(Question.difficulty).where(Question.id == latest.question_id)
        )
        if previous_difficulty is None or latest.is_correct is None:
            return 0.55
        adjustment = 0.2 if latest.is_correct else -0.2
        return round(min(0.85, max(0.25, previous_difficulty + adjustment)), 2)
