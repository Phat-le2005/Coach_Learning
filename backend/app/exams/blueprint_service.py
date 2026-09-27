from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.exams.models import Exam, ExamQuestion, ExamSection
from app.exams.schemas import ExamBlueprintConfig, ExamBlueprintRule
from app.questions.eligibility import standalone_question_only
from app.questions.models import Question, QuestionProblemType, QuestionStatus

logger = logging.getLogger(__name__)


class ExamBlueprintService:
    """Service to assemble standardized exam questions dynamically from blueprints.

    Architectural Guarantees:
    - 100% Data-Driven: No hardcoded examinations or static question sets in core service.
    - Prioritizes Curriculum hierarchy (Chapter, Topic) and ProblemType as primary distribution axis.
    - Concepts are leveraged for post-exam diagnosis and prerequisite analytics, not as raw distribution constraints.
    - Strictly selects APPROVED questions from the question bank.
    - Prevents question duplication across sections within the same exam.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def assemble_exam_questions(
        self,
        exam_id: UUID,
        blueprint_override: ExamBlueprintConfig | None = None,
    ) -> list[ExamQuestion]:
        exam = self.session.get(Exam, exam_id)
        if exam is None:
            raise ApplicationError(404, "EXAM_NOT_FOUND", "Exam not found.")

        # Clear existing assembled questions
        existing_questions = list(
            self.session.scalars(select(ExamQuestion).where(ExamQuestion.exam_id == exam_id)).all()
        )
        for eq in existing_questions:
            self.session.delete(eq)
        self.session.flush()

        used_question_ids: set[UUID] = set()
        created_exam_questions: list[ExamQuestion] = []
        current_order_index = 0

        # Check sections first: If exam has sections with blueprints
        sections = list(
            self.session.scalars(
                select(ExamSection)
                .where(ExamSection.exam_id == exam_id)
                .order_by(ExamSection.order_index)
            ).all()
        )

        sections_with_blueprints = [s for s in sections if s.blueprint_config]

        if sections_with_blueprints:
            for section in sections:
                if not section.blueprint_config:
                    continue
                section_bp = ExamBlueprintConfig.model_validate(section.blueprint_config)
                for rule in section_bp.rules:
                    selected = self._find_matching_questions(
                        subject_id=exam.subject_id,
                        rule=rule,
                        excluded_ids=used_question_ids,
                    )
                    for q in selected:
                        used_question_ids.add(q.id)
                        eq = ExamQuestion(
                            exam_id=exam.id,
                            section_id=section.id,
                            question_id=q.id,
                            order_index=current_order_index,
                            points=rule.points_per_question,
                        )
                        self.session.add(eq)
                        created_exam_questions.append(eq)
                        current_order_index += 1

        # Otherwise / In addition: Exam-level blueprint
        effective_blueprint = blueprint_override
        if not effective_blueprint and exam.blueprint_config:
            effective_blueprint = ExamBlueprintConfig.model_validate(exam.blueprint_config)

        if effective_blueprint and effective_blueprint.rules:
            for rule in effective_blueprint.rules:
                selected = self._find_matching_questions(
                    subject_id=exam.subject_id,
                    rule=rule,
                    excluded_ids=used_question_ids,
                )
                for q in selected:
                    used_question_ids.add(q.id)
                    eq = ExamQuestion(
                        exam_id=exam.id,
                        section_id=None,
                        question_id=q.id,
                        order_index=current_order_index,
                        points=rule.points_per_question,
                    )
                    self.session.add(eq)
                    created_exam_questions.append(eq)
                    current_order_index += 1

        if not created_exam_questions:
            raise ApplicationError(
                400,
                "NO_QUESTIONS_ASSEMBLED",
                "Blueprint did not match any approved questions in the database.",
            )

        self.session.flush()

        # Update exam summary fields
        exam.total_questions = len(created_exam_questions)
        exam.total_points = sum(eq.points for eq in created_exam_questions)
        self.session.flush()

        return created_exam_questions

    def _find_matching_questions(
        self,
        subject_id: UUID,
        rule: ExamBlueprintRule,
        excluded_ids: set[UUID],
    ) -> list[Question]:
        query = (
            select(Question)
            .where(
                Question.subject_id == subject_id,
                Question.status == QuestionStatus.APPROVED,
                standalone_question_only(),
            )
        )

        if excluded_ids:
            query = query.where(Question.id.not_in(list(excluded_ids)))

        if rule.question_type:
            query = query.where(Question.question_type == rule.question_type)

        if rule.cognitive_level:
            query = query.where(Question.cognitive_level == rule.cognitive_level)

        if rule.difficulty_min is not None:
            query = query.where(Question.difficulty >= rule.difficulty_min)

        if rule.difficulty_max is not None:
            query = query.where(Question.difficulty <= rule.difficulty_max)

        # Joins for Curriculum hierarchy
        if rule.problem_type_id:
            query = query.join(
                QuestionProblemType, QuestionProblemType.question_id == Question.id
            ).where(QuestionProblemType.problem_type_id == rule.problem_type_id)
        elif rule.topic_id:
            query = (
                query.join(QuestionProblemType, QuestionProblemType.question_id == Question.id)
                .join(ProblemType, ProblemType.id == QuestionProblemType.problem_type_id)
                .where(ProblemType.topic_id == rule.topic_id)
            )
        elif rule.chapter_id:
            query = (
                query.join(QuestionProblemType, QuestionProblemType.question_id == Question.id)
                .join(ProblemType, ProblemType.id == QuestionProblemType.problem_type_id)
                .join(Topic, Topic.id == ProblemType.topic_id)
                .where(Topic.chapter_id == rule.chapter_id)
            )

        query = query.limit(rule.count)
        results = list(self.session.scalars(query).all())

        # If strict difficulty/cognitive filtering yielded fewer questions than requested count,
        # fallback to same ProblemType/Topic/Chapter with APPROVED status.
        if len(results) < rule.count and (rule.difficulty_min is not None or rule.difficulty_max is not None or rule.cognitive_level):
            fallback_excluded = excluded_ids.union({q.id for q in results})
            needed = rule.count - len(results)

            fallback_query = (
                select(Question)
                .where(
                    Question.subject_id == subject_id,
                    Question.status == QuestionStatus.APPROVED,
                    standalone_question_only(),
                )
            )
            if fallback_excluded:
                fallback_query = fallback_query.where(Question.id.not_in(list(fallback_excluded)))
            if rule.question_type:
                fallback_query = fallback_query.where(Question.question_type == rule.question_type)

            if rule.problem_type_id:
                fallback_query = fallback_query.join(
                    QuestionProblemType, QuestionProblemType.question_id == Question.id
                ).where(QuestionProblemType.problem_type_id == rule.problem_type_id)
            elif rule.topic_id:
                fallback_query = (
                    fallback_query.join(QuestionProblemType, QuestionProblemType.question_id == Question.id)
                    .join(ProblemType, ProblemType.id == QuestionProblemType.problem_type_id)
                    .where(ProblemType.topic_id == rule.topic_id)
                )
            elif rule.chapter_id:
                fallback_query = (
                    fallback_query.join(QuestionProblemType, QuestionProblemType.question_id == Question.id)
                    .join(ProblemType, ProblemType.id == QuestionProblemType.problem_type_id)
                    .join(Topic, Topic.id == ProblemType.topic_id)
                    .where(Topic.chapter_id == rule.chapter_id)
                )

            fallback_results = list(self.session.scalars(fallback_query.limit(needed)).all())
            results.extend(fallback_results)

        return results
