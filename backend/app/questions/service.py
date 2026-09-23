from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.hints.models import QuestionHint
from app.hints.policy import reveals_final_answer
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.questions.schemas import (
    QuestionConceptInput,
    QuestionCreate,
    QuestionHintInput,
    QuestionLearningOutcomeInput,
    QuestionOptionInput,
    QuestionPatch,
    QuestionProblemTypeInput,
    QuestionWriteBase,
)
from app.subjects.models import Subject
from app.users.models import Role, User

logger = logging.getLogger(__name__)


class QuestionService:
    """Owns Question Bank validation, visibility, and review state transitions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, actor: User, data: QuestionCreate) -> Question:
        self._subject_or_404(data.subject_id)
        self._validate_concepts(data.subject_id, data.concepts)
        self._validate_classifications(
            data.subject_id, data.problem_types, data.learning_outcomes
        )
        self._validate_hints(
            data.correct_answer, data.question_type, data.options, data.hints
        )
        question = Question(
            **data.model_dump(
                exclude={
                    "options",
                    "concepts",
                    "problem_types",
                    "learning_outcomes",
                    "hints",
                }
            ),
            status=QuestionStatus.DRAFT,
            created_by=actor.id,
        )
        question.options = self._make_options(data.options)
        question.concept_links = self._make_concepts(data.concepts)
        question.problem_type_links = self._make_problem_types(data.problem_types)
        question.learning_outcome_links = self._make_learning_outcomes(
            data.learning_outcomes
        )
        question.hints = self._make_hints(data.hints)
        # HIGH FIX: Check for duplicate content hash before saving.
        # QuestionImportService runs this check during batch imports, but
        # the single-question creation path was missing it.
        existing_id = self.session.scalar(
            select(Question.id).where(
                Question.content_hash == question.content_hash,
                Question.subject_id == question.subject_id,
            )
        )
        if existing_id is not None:
            raise ApplicationError(
                409,
                "DUPLICATE_QUESTION",
                f"A question with identical content already exists (id={existing_id}). "
                "Duplicates are not allowed in the Question Bank.",
            )
        self.session.add(question)
        self.session.commit()
        logger.info("Question created (question_id=%s, created_by=%s)", question.id, actor.id)
        return self._question_or_404(question.id)

    def list(
        self,
        actor: User,
        *,
        subject_id: UUID | None = None,
        concept_id: UUID | None = None,
        problem_type_id: UUID | None = None,
        learning_outcome_id: UUID | None = None,
        difficulty_min: float | None = None,
        difficulty_max: float | None = None,
        question_type: QuestionType | None = None,
        status: QuestionStatus | None = None,
        cognitive_level: CognitiveLevel | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Question]:
        if difficulty_min is not None and difficulty_max is not None and difficulty_min > difficulty_max:
            raise ApplicationError(422, "INVALID_DIFFICULTY_RANGE", "difficulty_min cannot exceed difficulty_max.")
        statement: Select[tuple[Question]] = select(Question).options(
            selectinload(Question.options),
            selectinload(Question.concept_links),
            selectinload(Question.problem_type_links),
            selectinload(Question.learning_outcome_links),
            selectinload(Question.hints),
        )
        if actor.role != Role.ADMIN:
            statement = statement.where(
                or_(Question.created_by == actor.id, Question.status == QuestionStatus.APPROVED)
            )
        if subject_id is not None:
            statement = statement.where(Question.subject_id == subject_id)
        if concept_id is not None:
            statement = statement.join(QuestionConcept).where(QuestionConcept.concept_id == concept_id)
        if problem_type_id is not None:
            statement = statement.join(QuestionProblemType).where(
                QuestionProblemType.problem_type_id == problem_type_id
            )
        if learning_outcome_id is not None:
            statement = statement.join(QuestionLearningOutcome).where(
                QuestionLearningOutcome.learning_outcome_id == learning_outcome_id
            )
        if difficulty_min is not None:
            statement = statement.where(Question.difficulty >= difficulty_min)
        if difficulty_max is not None:
            statement = statement.where(Question.difficulty <= difficulty_max)
        if question_type is not None:
            statement = statement.where(Question.question_type == question_type)
        if status is not None:
            statement = statement.where(Question.status == status)
        if cognitive_level is not None:
            statement = statement.where(Question.cognitive_level == cognitive_level)
        statement = statement.order_by(Question.created_at.desc(), Question.id).offset(offset).limit(limit)
        return list(self.session.scalars(statement).unique())

    def get(self, actor: User, question_id: UUID) -> Question:
        question = self._question_or_404(question_id)
        if actor.role != Role.ADMIN and question.created_by != actor.id and question.status != QuestionStatus.APPROVED:
            raise self._access_denied()
        return question

    def patch(self, actor: User, question_id: UUID, data: QuestionPatch) -> Question:
        question = self._question_for_update(question_id)
        supplied = data.model_fields_set
        if not supplied:
            return self.get(actor, question_id)
        if "status" in supplied:
            if supplied != {"status"} or data.status != QuestionStatus.ARCHIVED or actor.role != Role.ADMIN:
                raise ApplicationError(
                    409,
                    "INVALID_QUESTION_TRANSITION",
                    "Use the review endpoints for workflow transitions; only an admin can archive a question.",
                )
            if question.status == QuestionStatus.ARCHIVED:
                raise self._not_editable()
            question.status = QuestionStatus.ARCHIVED
            self.session.commit()
            logger.info("Question archived (question_id=%s, actor_id=%s)", question.id, actor.id)
            return self._question_or_404(question.id)

        self._authorize_edit(actor, question)
        resulting_type = data.question_type if "question_type" in supplied else question.question_type
        resulting_options = data.options if "options" in supplied else [
            QuestionOptionInput(label=option.label, content=option.content, order_index=option.order_index)
            for option in question.options
        ]
        resulting_concepts = data.concepts if "concepts" in supplied else [
            QuestionConceptInput(concept_id=link.concept_id, weight=link.weight)
            for link in question.concept_links
        ]
        resulting_problem_types = data.problem_types if "problem_types" in supplied else [
            QuestionProblemTypeInput(
                problem_type_id=link.problem_type_id,
                weight=link.weight,
                is_primary=link.is_primary,
            )
            for link in question.problem_type_links
        ]
        resulting_outcomes = data.learning_outcomes if "learning_outcomes" in supplied else [
            QuestionLearningOutcomeInput(
                learning_outcome_id=link.learning_outcome_id, weight=link.weight
            )
            for link in question.learning_outcome_links
        ]
        resulting_hints = data.hints if "hints" in supplied else [
            QuestionHintInput(hint_level=hint.hint_level, content=hint.content)
            for hint in question.hints
        ]
        assert (
            resulting_type is not None
            and resulting_options is not None
            and resulting_concepts is not None
            and resulting_problem_types is not None
            and resulting_outcomes is not None
            and resulting_hints is not None
        )
        try:
            QuestionWriteBase.validate_collections(
                resulting_type,
                resulting_options,
                resulting_concepts,
                resulting_problem_types,
                resulting_outcomes,
                resulting_hints,
            )
        except ValueError as error:
            raise ApplicationError(422, "INVALID_QUESTION", str(error)) from error

        resulting_subject = data.subject_id if "subject_id" in supplied else question.subject_id
        assert resulting_subject is not None
        self._subject_or_404(resulting_subject)
        self._validate_concepts(resulting_subject, resulting_concepts)
        self._validate_classifications(
            resulting_subject, resulting_problem_types, resulting_outcomes
        )
        resulting_answer = (
            data.correct_answer if "correct_answer" in supplied else question.correct_answer
        )
        self._validate_hints(
            resulting_answer, resulting_type, resulting_options, resulting_hints
        )
        for field in {
            "subject_id", "content", "question_type", "difficulty", "correct_answer",
            "explanation", "source_type", "source_reference", "source_year",
            "cognitive_level", "exam_weight",
        } & supplied:
            setattr(question, field, getattr(data, field))
        if "options" in supplied:
            question.options.clear()
            self.session.flush()
            question.options = self._make_options(resulting_options)
        if "concepts" in supplied:
            question.concept_links.clear()
            self.session.flush()
            question.concept_links = self._make_concepts(resulting_concepts)
        if "problem_types" in supplied:
            question.problem_type_links.clear()
            self.session.flush()
            question.problem_type_links = self._make_problem_types(resulting_problem_types)
        if "learning_outcomes" in supplied:
            question.learning_outcome_links.clear()
            self.session.flush()
            question.learning_outcome_links = self._make_learning_outcomes(resulting_outcomes)
        if "hints" in supplied:
            question.hints.clear()
            self.session.flush()
            question.hints = self._make_hints(resulting_hints)
        self.session.commit()
        logger.info("Question updated (question_id=%s, actor_id=%s)", question.id, actor.id)
        return self._question_or_404(question.id)

    def submit_review(self, actor: User, question_id: UUID) -> Question:
        question = self._question_for_update(question_id)
        if actor.role != Role.ADMIN and question.created_by != actor.id:
            raise self._access_denied()
        if question.status != QuestionStatus.DRAFT:
            raise self._invalid_transition("Only a DRAFT question can be submitted for review.")
        self._validate_ready(question)
        question.status = QuestionStatus.REVIEW
        self.session.commit()
        logger.info("Question submitted for review (question_id=%s, actor_id=%s)", question.id, actor.id)
        return self._question_or_404(question.id)

    def approve(self, actor: User, question_id: UUID) -> Question:
        if actor.role != Role.ADMIN:
            raise self._access_denied()
        question = self._question_for_update(question_id)
        if question.status != QuestionStatus.REVIEW:
            raise self._invalid_transition("Only a REVIEW question can be approved.")
        self._validate_ready(question)
        question.status = QuestionStatus.APPROVED
        self.session.commit()
        logger.info("Question approved (question_id=%s, actor_id=%s)", question.id, actor.id)
        return self._question_or_404(question.id)

    def get_approved_for_learning(self, question_id: UUID) -> Question:
        question = self.session.scalar(
            self._question_statement().where(
                Question.id == question_id, Question.status == QuestionStatus.APPROVED
            )
        )
        if question is None:
            raise ApplicationError(404, "APPROVED_QUESTION_NOT_FOUND", "Approved question was not found.")
        return question

    def _authorize_edit(self, actor: User, question: Question) -> None:
        if actor.role == Role.ADMIN:
            if question.status not in {QuestionStatus.DRAFT, QuestionStatus.REVIEW}:
                raise self._not_editable()
            return
        if question.created_by != actor.id:
            raise self._access_denied()
        if question.status != QuestionStatus.DRAFT:
            raise self._not_editable()

    def _validate_ready(self, question: Question) -> None:
        if not question.concept_links:
            raise self._not_ready("A question must be linked to at least one concept.")
        answer = question.correct_answer.strip().upper() if question.correct_answer else None
        if question.question_type == QuestionType.MULTIPLE_CHOICE:
            labels = {option.label.upper() for option in question.options}
            if answer is None or answer not in labels:
                raise self._not_ready("MULTIPLE_CHOICE correct_answer must match an option label.")
        elif question.question_type == QuestionType.TRUE_FALSE:
            if answer not in {"TRUE", "FALSE"}:
                raise self._not_ready("TRUE_FALSE correct_answer must be TRUE or FALSE.")
        elif question.question_type == QuestionType.SHORT_ANSWER and answer is None:
            raise self._not_ready("SHORT_ANSWER requires correct_answer.")

    def _validate_concepts(self, subject_id: UUID, links: list[QuestionConceptInput]) -> None:
        if not links:
            return
        concept_ids = {link.concept_id for link in links}
        concepts = list(self.session.scalars(select(Concept).where(Concept.id.in_(concept_ids))))
        found_ids = {concept.id for concept in concepts}
        if found_ids != concept_ids:
            raise ApplicationError(404, "CONCEPT_NOT_FOUND", "One or more concepts were not found.")
        if any(concept.subject_id != subject_id for concept in concepts):
            raise ApplicationError(422, "CONCEPT_SUBJECT_MISMATCH", "All concepts must belong to the question subject.")

    def _validate_classifications(
        self,
        subject_id: UUID,
        problem_types: list[QuestionProblemTypeInput],
        outcomes: list[QuestionLearningOutcomeInput],
    ) -> None:
        problem_ids = {link.problem_type_id for link in problem_types}
        if problem_ids:
            rows = list(self.session.execute(
                select(ProblemType.id, Chapter.subject_id)
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .where(ProblemType.id.in_(problem_ids))
            ))
            if {row[0] for row in rows} != problem_ids:
                raise ApplicationError(
                    404, "PROBLEM_TYPE_NOT_FOUND", "One or more problem types were not found."
                )
            if any(row[1] != subject_id for row in rows):
                raise ApplicationError(
                    422,
                    "PROBLEM_TYPE_SUBJECT_MISMATCH",
                    "All problem types must belong to the question subject.",
                )
        outcome_ids = {link.learning_outcome_id for link in outcomes}
        if outcome_ids:
            found = list(
                self.session.scalars(
                    select(LearningOutcome).where(LearningOutcome.id.in_(outcome_ids))
                )
            )
            if {item.id for item in found} != outcome_ids:
                raise ApplicationError(
                    404,
                    "LEARNING_OUTCOME_NOT_FOUND",
                    "One or more learning outcomes were not found.",
                )
            if any(item.subject_id != subject_id for item in found):
                raise ApplicationError(
                    422,
                    "LEARNING_OUTCOME_SUBJECT_MISMATCH",
                    "All learning outcomes must belong to the question subject.",
                )

    def _subject_or_404(self, subject_id: UUID) -> Subject:
        subject = self.session.get(Subject, subject_id)
        if subject is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        return subject

    def _question_or_404(self, question_id: UUID) -> Question:
        question = self.session.scalar(self._question_statement().where(Question.id == question_id))
        if question is None:
            raise ApplicationError(404, "QUESTION_NOT_FOUND", "Question was not found.")
        return question

    def _question_for_update(self, question_id: UUID) -> Question:
        question = self.session.scalar(
            self._question_statement().where(Question.id == question_id).with_for_update()
        )
        if question is None:
            raise ApplicationError(404, "QUESTION_NOT_FOUND", "Question was not found.")
        return question

    @staticmethod
    def _question_statement() -> Select[tuple[Question]]:
        return select(Question).options(
            selectinload(Question.options),
            selectinload(Question.concept_links),
            selectinload(Question.problem_type_links),
            selectinload(Question.learning_outcome_links),
            selectinload(Question.hints),
        )

    @staticmethod
    def _make_options(options: list[QuestionOptionInput]) -> list[QuestionOption]:
        return [QuestionOption(**option.model_dump()) for option in options]

    @staticmethod
    def _make_concepts(concepts: list[QuestionConceptInput]) -> list[QuestionConcept]:
        return [QuestionConcept(**link.model_dump()) for link in concepts]

    @staticmethod
    def _make_problem_types(
        problem_types: list[QuestionProblemTypeInput],
    ) -> list[QuestionProblemType]:
        return [QuestionProblemType(**link.model_dump()) for link in problem_types]

    @staticmethod
    def _make_learning_outcomes(
        outcomes: list[QuestionLearningOutcomeInput],
    ) -> list[QuestionLearningOutcome]:
        return [QuestionLearningOutcome(**link.model_dump()) for link in outcomes]

    @staticmethod
    def _make_hints(hints: list[QuestionHintInput]) -> list[QuestionHint]:
        return [QuestionHint(**hint.model_dump()) for hint in hints]

    @staticmethod
    def _validate_hints(
        correct_answer: str | None,
        question_type: QuestionType,
        options: list[QuestionOptionInput],
        hints: list[QuestionHintInput],
    ) -> None:
        if not hints or not correct_answer:
            return

        class _PolicyQuestion:
            correct_answer: str | None
            question_type: QuestionType
            options: list[QuestionOptionInput]

        candidate = _PolicyQuestion()
        candidate.correct_answer = correct_answer
        candidate.question_type = question_type
        candidate.options = options
        for hint in hints:
            if reveals_final_answer(candidate, hint.hint_level, hint.content):
                raise ApplicationError(
                    422,
                    "HINT_REVEALS_FINAL_ANSWER",
                    "Predefined hints before LEVEL_4 cannot reveal the final answer.",
                )

    @staticmethod
    def _access_denied() -> ApplicationError:
        return ApplicationError(403, "QUESTION_ACCESS_DENIED", "You do not have access to this question.")

    @staticmethod
    def _not_editable() -> ApplicationError:
        return ApplicationError(409, "QUESTION_NOT_EDITABLE", "Question cannot be edited in its current status.")

    @staticmethod
    def _not_ready(message: str) -> ApplicationError:
        return ApplicationError(409, "QUESTION_NOT_READY", message)

    @staticmethod
    def _invalid_transition(message: str) -> ApplicationError:
        return ApplicationError(409, "INVALID_QUESTION_TRANSITION", message)
