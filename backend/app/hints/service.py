from __future__ import annotations

import logging
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.ai.dependencies import create_ai_provider
from app.ai.gateway import AIGateway
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.types import AIMessage, AIRole, AITaskType
from app.ai.usage_service import AIUsageService
from app.concepts.models import Concept
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.curriculum.models import LearningOutcome, ProblemType
from app.diagnostics.models import DiagnosticAssessment
from app.hints.models import HintLevel, HintSource, PracticeQuestionHint, QuestionHint
from app.hints.policy import reveals_final_answer
from app.hints.schemas import AIHintOutput, HintRequest
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.models import (
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.practice.service import PracticeService
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionProblemType,
)
from app.students.models import StudentProfile
from app.users.models import User

logger = logging.getLogger(__name__)


class HintService:
    """Issues progressive hints and records exactly what a student was shown."""

    PROMPT_NAME = "hint_generator"
    PROMPT_VERSION = "v2"

    def __init__(
        self,
        session: Session,
        gateway: AIGateway | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.session = session
        self.gateway = gateway
        self.prompt_registry = prompt_registry or default_prompt_registry

    async def get_hint(
        self,
        current_user: User,
        question_id: UUID,
        data: HintRequest,
    ) -> PracticeQuestionHint:
        student = self._student_for_user(current_user.id)
        practice_session = self.session.get(PracticeSession, data.practice_session_id)
        if practice_session is None:
            raise ApplicationError(
                404, "PRACTICE_SESSION_NOT_FOUND", "Practice session was not found."
            )
        self._authorize(practice_session, student)
        self._require_active(practice_session)

        question = self._current_question(
            current_user=current_user,
            practice_session=practice_session,
            question_id=question_id,
        )
        existing = self._existing_hint(
            practice_session.id, question.id, data.current_hint_level
        )
        if existing is not None:
            return existing

        issued = self._issued_hints(practice_session.id, question.id)
        expected_level = len(issued) + 1
        if data.current_hint_level.number != expected_level:
            raise ApplicationError(
                409,
                "HINT_LEVEL_OUT_OF_SEQUENCE",
                f"The next available hint is LEVEL_{expected_level}.",
            )

        predefined = self.session.get(
            QuestionHint, (question.id, data.current_hint_level)
        )
        if predefined is not None:
            content = predefined.content
            source = HintSource.PREDEFINED
        else:
            content = await self._generate_ai_hint(
                current_user=current_user,
                student=student,
                question=question,
                level=data.current_hint_level,
                previous_hints=issued,
            )
            source = HintSource.AI

        if reveals_final_answer(question, data.current_hint_level, content):
            status_code = 422 if source == HintSource.PREDEFINED else 502
            raise ApplicationError(
                status_code,
                "HINT_REVEALS_FINAL_ANSWER",
                "Hints before LEVEL_4 cannot reveal the final answer.",
            )

        hint = PracticeQuestionHint(
            practice_session_id=practice_session.id,
            student_id=student.id,
            question_id=question.id,
            hint_level=data.current_hint_level,
            hint_count=expected_level,
            hint_source=source,
            content=content,
        )
        try:
            self.session.add(hint)
            self.session.commit()
            self.session.refresh(hint)
        except IntegrityError as exc:
            self.session.rollback()
            # Same-level retries are idempotent, including a concurrent retry.
            concurrent = self._existing_hint(
                practice_session.id, question.id, data.current_hint_level
            )
            if concurrent is not None:
                return concurrent
            raise ApplicationError(
                409,
                "HINT_REQUEST_CONFLICT",
                "The hint sequence changed while this request was processed.",
            ) from exc

        logger.info(
            "Practice hint issued (session_id=%s, question_id=%s, level=%s, source=%s)",
            practice_session.id,
            question.id,
            hint.hint_level.value,
            hint.hint_source.value,
        )
        return hint

    def _current_question(
        self,
        *,
        current_user: User,
        practice_session: PracticeSession,
        question_id: UUID,
    ) -> Question:
        duplicate = self.session.scalar(
            select(QuestionAttempt.id).where(
                QuestionAttempt.practice_session_id == practice_session.id,
                QuestionAttempt.question_id == question_id,
            )
        )
        if duplicate is not None:
            raise ApplicationError(
                409,
                "QUESTION_ALREADY_ANSWERED",
                "Hints are unavailable after the question has been answered.",
            )

        if practice_session.session_type == PracticeSessionType.DIAGNOSTIC:
            assessment = self.session.get(DiagnosticAssessment, practice_session.id)
            if assessment is None or assessment.current_question_id != question_id:
                raise ApplicationError(
                    422,
                    "QUESTION_NOT_CURRENT",
                    "The question is not the current diagnostic question.",
                )
            question = self._question(question_id)
        else:
            next_question = PracticeService(self.session).get_next_question(
                current_user, practice_session.id
            )
            if next_question.id != question_id:
                raise ApplicationError(
                    422,
                    "QUESTION_NOT_CURRENT",
                    "Hints are available only for the current practice question.",
                )
            question = next_question

        if not (
            question.problem_type_links
            and question.concept_links
            and question.learning_outcome_links
        ):
            raise ApplicationError(
                422,
                "QUESTION_NOT_CLASSIFIED",
                "Hints require ProblemType, Concept, and LearningOutcome mappings.",
            )
        return question

    async def _generate_ai_hint(
        self,
        *,
        current_user: User,
        student: StudentProfile,
        question: Question,
        level: HintLevel,
        previous_hints: list[PracticeQuestionHint],
    ) -> str:
        problem_types = list(
            self.session.scalars(
                select(ProblemType)
                .join(
                    QuestionProblemType,
                    QuestionProblemType.problem_type_id == ProblemType.id,
                )
                .where(QuestionProblemType.question_id == question.id)
                .order_by(ProblemType.code, ProblemType.id)
            )
        )
        concepts = list(
            self.session.scalars(
                select(Concept)
                .join(QuestionConcept, QuestionConcept.concept_id == Concept.id)
                .where(QuestionConcept.question_id == question.id)
                .order_by(Concept.code, Concept.id)
            )
        )
        learning_outcomes = list(
            self.session.scalars(
                select(LearningOutcome)
                .join(
                    QuestionLearningOutcome,
                    QuestionLearningOutcome.learning_outcome_id
                    == LearningOutcome.id,
                )
                .where(QuestionLearningOutcome.question_id == question.id)
                .order_by(LearningOutcome.code, LearningOutcome.id)
            )
        )
        problem_mastery = {
            item.problem_type_id: item
            for item in self.session.scalars(
                select(StudentProblemTypeMastery).where(
                    StudentProblemTypeMastery.student_id == student.id,
                    StudentProblemTypeMastery.problem_type_id.in_(
                        [item.id for item in problem_types]
                    ),
                )
            )
        }
        concept_mastery = {
            item.concept_id: item
            for item in self.session.scalars(
                select(StudentConceptMastery).where(
                    StudentConceptMastery.student_id == student.id,
                    StudentConceptMastery.concept_id.in_(
                        [item.id for item in concepts]
                    ),
                )
            )
        }
        mastery_lines = [
            *(
                f"ProblemType {item.code}: mastery="
                f"{problem_mastery[item.id].mastery_score:.3f}, confidence="
                f"{problem_mastery[item.id].confidence:.3f}"
                if item.id in problem_mastery
                else f"ProblemType {item.code}: NOT_STARTED"
                for item in problem_types
            ),
            *(
                f"Concept {item.code}: mastery="
                f"{concept_mastery[item.id].mastery_score:.3f}, confidence="
                f"{concept_mastery[item.id].confidence:.3f}"
                if item.id in concept_mastery
                else f"Concept {item.code}: NOT_STARTED"
                for item in concepts
            ),
        ]
        prompt = self.prompt_registry.get_prompt(
            self.PROMPT_NAME,
            self.PROMPT_VERSION,
            variables={
                "question_content": question.content,
                "problem_type_context": self._context_lines(
                    (
                        item.code,
                        item.name,
                        item.description,
                    )
                    for item in problem_types
                ),
                "concept_context": self._context_lines(
                    (item.code, item.name, item.description) for item in concepts
                ),
                "learning_outcome_context": self._context_lines(
                    (item.code, item.description, None) for item in learning_outcomes
                ),
                "student_mastery_compact": "\n".join(mastery_lines)
                or "No mapped mastery evidence yet.",
                "current_attempt_state": (
                    "No answer submitted; "
                    f"{len(previous_hints)} hint(s) have already been shown."
                ),
                "previous_hints": "\n".join(
                    f"- {item.hint_level.value}: {item.content}"
                    for item in previous_hints
                )
                or "None",
                "hint_level": level.value,
            },
        )
        gateway = self.gateway
        if gateway is None:
            settings = Settings()
            gateway = AIGateway(
                provider=create_ai_provider(settings), settings=settings
            )
        response = await gateway.generate_structured(
            task_type=AITaskType.HINT,
            schema=AIHintOutput,
            messages=[AIMessage(role=AIRole.USER, content=prompt)],
            temperature=0.2,
            prompt_name=self.PROMPT_NAME,
            prompt_version=self.PROMPT_VERSION,
            user_id=current_user.id,
            usage_service=AIUsageService(self.session),
        )
        output = response.data
        allowed_codes = {item.code.upper() for item in concepts}
        unknown_codes = set(output.referenced_concept_codes) - allowed_codes
        allowed_problem_codes = {item.code.upper() for item in problem_types}
        unknown_problem_codes = (
            set(output.referenced_problem_type_codes) - allowed_problem_codes
        )
        allowed_outcome_codes = {item.code.upper() for item in learning_outcomes}
        unknown_outcome_codes = (
            set(output.referenced_learning_outcome_codes) - allowed_outcome_codes
        )
        if unknown_codes or unknown_problem_codes or unknown_outcome_codes:
            raise ApplicationError(
                502,
                "AI_HINT_CURRICULUM_VIOLATION",
                "AI hint referenced concepts outside the question mappings.",
            )
        if level != HintLevel.LEVEL_4 and output.reveals_final_answer:
            raise ApplicationError(
                502,
                "AI_HINT_POLICY_VIOLATION",
                "AI hint violated the progressive disclosure policy.",
            )
        return output.content

    def _question(self, question_id: UUID) -> Question:
        question = self.session.scalar(
            select(Question)
            .options(
                selectinload(Question.options),
                selectinload(Question.problem_type_links),
                selectinload(Question.concept_links),
                selectinload(Question.learning_outcome_links),
                selectinload(Question.hints),
            )
            .where(Question.id == question_id)
        )
        if question is None:
            raise ApplicationError(404, "QUESTION_NOT_FOUND", "Question was not found.")
        return question

    def _existing_hint(
        self, session_id: UUID, question_id: UUID, level: HintLevel
    ) -> PracticeQuestionHint | None:
        return self.session.scalar(
            select(PracticeQuestionHint).where(
                PracticeQuestionHint.practice_session_id == session_id,
                PracticeQuestionHint.question_id == question_id,
                PracticeQuestionHint.hint_level == level,
            )
        )

    def _issued_hints(
        self, session_id: UUID, question_id: UUID
    ) -> list[PracticeQuestionHint]:
        return list(
            self.session.scalars(
                select(PracticeQuestionHint)
                .where(
                    PracticeQuestionHint.practice_session_id == session_id,
                    PracticeQuestionHint.question_id == question_id,
                )
                .order_by(PracticeQuestionHint.hint_count)
            )
        )

    def _student_for_user(self, user_id: UUID) -> StudentProfile:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if student is None:
            raise ApplicationError(
                404, "PROFILE_NOT_FOUND", "Student profile was not found."
            )
        return student

    @staticmethod
    def _authorize(
        practice_session: PracticeSession, student: StudentProfile
    ) -> None:
        if practice_session.student_id != student.id:
            raise ApplicationError(
                403,
                "PRACTICE_SESSION_ACCESS_DENIED",
                "You do not have access to this practice session.",
            )

    @staticmethod
    def _require_active(practice_session: PracticeSession) -> None:
        if practice_session.status != PracticeSessionStatus.ACTIVE:
            raise ApplicationError(
                409,
                "PRACTICE_SESSION_NOT_ACTIVE",
                "Hints are available only in an active practice session.",
            )

    @staticmethod
    def _context_lines(
        rows: Iterable[tuple[str, str, str | None]],
    ) -> str:
        formatted = []
        for code, name, description in rows:
            detail = f" — {description}" if description else ""
            formatted.append(f"- {code}: {name}{detail}")
        return "\n".join(formatted) or "None"
