from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.mastery.evidence import MasteryAttemptEvidencePublisher
from app.practice.evaluation import AnswerEvaluationService
from app.practice.evidence import (
    AttemptEvaluatedEvidence,
    AttemptEvidencePublisher,
)
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionConcept,
    PracticeSessionProblemType,
    PracticeSessionStatus,
    QuestionAttempt,
)
from app.practice.schemas import PracticeAnswerCreate, PracticeSessionCreate, PracticeSessionRead
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionProblemType,
    QuestionStatus,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import User

logger = logging.getLogger(__name__)


class PracticeService:
    def __init__(
        self,
        session: Session,
        evaluator: AnswerEvaluationService | None = None,
        evidence_publisher: AttemptEvidencePublisher | None = None,
    ) -> None:
        self.session = session
        self.evaluator = evaluator or AnswerEvaluationService()
        self.evidence_publisher = (
            evidence_publisher
            if evidence_publisher is not None
            else MasteryAttemptEvidencePublisher()
        )

    def create_session(self, current_user: User, data: PracticeSessionCreate) -> PracticeSession:
        student = self._student_for_user(current_user.id)
        if self.session.get(Subject, data.subject_id) is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        self._validate_problem_types(data.subject_id, set(data.problem_type_ids))
        self._validate_concepts(data.subject_id, set(data.concept_ids))

        practice_session = PracticeSession(
            student_id=student.id,
            subject_id=data.subject_id,
            session_type=data.session_type,
            problem_type_links=[
                PracticeSessionProblemType(problem_type_id=item_id)
                for item_id in data.problem_type_ids
            ],
            concept_links=[
                PracticeSessionConcept(concept_id=item_id) for item_id in data.concept_ids
            ],
        )
        self.session.add(practice_session)
        self.session.commit()
        logger.info(
            "Practice session created (session_id=%s, student_id=%s)",
            practice_session.id,
            student.id,
        )
        return self._session_or_404(practice_session.id)

    def get_session(self, current_user: User, practice_session_id: UUID) -> PracticeSession:
        student = self._student_for_user(current_user.id)
        practice_session = self._session_or_404(practice_session_id)
        self._authorize_owner(practice_session, student)
        return practice_session

    def get_next_question(self, current_user: User, practice_session_id: UUID) -> Question:
        student = self._student_for_user(current_user.id)
        practice_session = self._session_or_404(practice_session_id)
        self._authorize_owner(practice_session, student)
        self._require_active(practice_session)
        question = self.session.scalar(
            self._eligible_questions(practice_session, exclude_attempted=True).limit(1)
        )
        if question is None:
            raise ApplicationError(
                404,
                "NO_AVAILABLE_QUESTION",
                "No approved classified question remains for this practice session.",
            )
        return question

    def answer(
        self,
        current_user: User,
        practice_session_id: UUID,
        data: PracticeAnswerCreate,
    ) -> QuestionAttempt:
        student = self._student_for_user(current_user.id)
        practice_session = self.session.scalar(
            self._session_statement()
            .where(PracticeSession.id == practice_session_id)
            .with_for_update()
        )
        if practice_session is None:
            raise ApplicationError(404, "PRACTICE_SESSION_NOT_FOUND", "Practice session was not found.")
        self._authorize_owner(practice_session, student)

        duplicate = self.session.scalar(
            select(QuestionAttempt.id).where(
                QuestionAttempt.practice_session_id == practice_session.id,
                QuestionAttempt.question_id == data.question_id,
            )
        )
        if duplicate is not None:
            raise self._duplicate_answer_error()
        self._require_active(practice_session)

        question = self.session.scalar(
            self._eligible_questions(practice_session, exclude_attempted=False).where(
                Question.id == data.question_id
            )
        )
        if question is None:
            raise ApplicationError(
                422,
                "QUESTION_NOT_ELIGIBLE",
                "Question is not an approved classified question in this session scope.",
            )

        evaluation = self.evaluator.evaluate(question, data.student_answer)
        previous_attempt_number = self.session.scalar(
            select(func.max(QuestionAttempt.attempt_number)).where(
                QuestionAttempt.practice_session_id == practice_session.id
            )
        )
        attempt = QuestionAttempt(
            practice_session_id=practice_session.id,
            student_id=student.id,
            question_id=question.id,
            student_answer=data.student_answer,
            is_correct=evaluation.is_correct,
            score=evaluation.score,
            response_time_seconds=data.response_time_seconds,
            hint_count=data.hint_count,
            attempt_number=(previous_attempt_number or 0) + 1,
            evaluation_status=evaluation.status,
        )

        try:
            self.session.add(attempt)
            self.session.flush()
            self.session.refresh(attempt)
            if (
                attempt.evaluation_status
                in {EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED}
                and attempt.is_correct is not None
                and attempt.score is not None
            ):
                self.evidence_publisher.publish(
                    self._make_evidence(attempt, practice_session, question), self.session
                )

            remaining = self.session.scalar(
                self._eligible_questions(practice_session, exclude_attempted=True).limit(1)
            )
            if remaining is None:
                practice_session.status = PracticeSessionStatus.COMPLETED
                practice_session.completed_at = datetime.now(timezone.utc)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            logger.info(
                "Duplicate/concurrent practice answer rejected (session_id=%s, question_id=%s)",
                practice_session_id,
                data.question_id,
            )
            raise self._duplicate_answer_error() from exc
        except Exception:
            self.session.rollback()
            raise

        logger.info(
            "Practice answer recorded (attempt_id=%s, status=%s)",
            attempt.id,
            attempt.evaluation_status.value,
        )
        return attempt

    @staticmethod
    def to_read(practice_session: PracticeSession) -> PracticeSessionRead:
        return PracticeSessionRead(
            id=practice_session.id,
            student_id=practice_session.student_id,
            subject_id=practice_session.subject_id,
            session_type=practice_session.session_type,
            started_at=practice_session.started_at,
            completed_at=practice_session.completed_at,
            status=practice_session.status,
            created_at=practice_session.created_at,
            problem_type_ids=[link.problem_type_id for link in practice_session.problem_type_links],
            concept_ids=[link.concept_id for link in practice_session.concept_links],
            attempts=practice_session.attempts,
        )

    def _eligible_questions(
        self, practice_session: PracticeSession, *, exclude_attempted: bool
    ) -> Select[tuple[Question]]:
        statement = (
            self._question_statement()
            .where(
                Question.subject_id == practice_session.subject_id,
                Question.status == QuestionStatus.APPROVED,
                Question.problem_type_links.any(),
                Question.concept_links.any(),
                Question.learning_outcome_links.any(),
            )
            .order_by(Question.created_at, Question.id)
        )
        problem_type_ids = [link.problem_type_id for link in practice_session.problem_type_links]
        if problem_type_ids:
            statement = statement.where(
                Question.problem_type_links.any(
                    QuestionProblemType.problem_type_id.in_(problem_type_ids)
                )
            )
        concept_ids = [link.concept_id for link in practice_session.concept_links]
        if concept_ids:
            statement = statement.where(
                Question.concept_links.any(QuestionConcept.concept_id.in_(concept_ids))
            )
        if exclude_attempted:
            statement = statement.where(
                ~Question.id.in_(
                    select(QuestionAttempt.question_id).where(
                        QuestionAttempt.practice_session_id == practice_session.id
                    )
                )
            )
        return statement

    @staticmethod
    def _question_statement() -> Select[tuple[Question]]:
        return select(Question).options(
            selectinload(Question.options),
            selectinload(Question.problem_type_links),
            selectinload(Question.concept_links),
            selectinload(Question.learning_outcome_links),
        )

    @staticmethod
    def _session_statement() -> Select[tuple[PracticeSession]]:
        return select(PracticeSession).options(
            selectinload(PracticeSession.problem_type_links),
            selectinload(PracticeSession.concept_links),
            selectinload(PracticeSession.attempts),
        )

    def _session_or_404(self, practice_session_id: UUID) -> PracticeSession:
        practice_session = self.session.scalar(
            self._session_statement().where(PracticeSession.id == practice_session_id)
        )
        if practice_session is None:
            raise ApplicationError(404, "PRACTICE_SESSION_NOT_FOUND", "Practice session was not found.")
        return practice_session

    def _student_for_user(self, user_id: UUID) -> StudentProfile:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if student is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
        return student

    def _validate_problem_types(self, subject_id: UUID, item_ids: set[UUID]) -> None:
        if not item_ids:
            return
        rows = list(
            self.session.execute(
                select(ProblemType.id, Chapter.subject_id)
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .where(ProblemType.id.in_(item_ids))
            )
        )
        if {row[0] for row in rows} != item_ids:
            raise ApplicationError(
                404, "PROBLEM_TYPE_NOT_FOUND", "One or more problem types were not found."
            )
        if any(row[1] != subject_id for row in rows):
            raise ApplicationError(
                422,
                "PROBLEM_TYPE_SUBJECT_MISMATCH",
                "All problem types must belong to the practice subject.",
            )

    def _validate_concepts(self, subject_id: UUID, item_ids: set[UUID]) -> None:
        if not item_ids:
            return
        concepts = list(self.session.scalars(select(Concept).where(Concept.id.in_(item_ids))))
        if {item.id for item in concepts} != item_ids:
            raise ApplicationError(404, "CONCEPT_NOT_FOUND", "One or more concepts were not found.")
        if any(item.subject_id != subject_id for item in concepts):
            raise ApplicationError(
                422,
                "CONCEPT_SUBJECT_MISMATCH",
                "All concepts must belong to the practice subject.",
            )

    @staticmethod
    def _authorize_owner(
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
                "Only an active practice session can accept or provide questions.",
            )

    @staticmethod
    def _make_evidence(
        attempt: QuestionAttempt,
        practice_session: PracticeSession,
        question: Question,
    ) -> AttemptEvaluatedEvidence:
        return AttemptEvaluatedEvidence(
            attempt_id=attempt.id,
            practice_session_id=practice_session.id,
            student_id=attempt.student_id,
            question_id=question.id,
            subject_id=practice_session.subject_id,
            is_correct=bool(attempt.is_correct),
            score=float(attempt.score),
            problem_type_ids=tuple(sorted(link.problem_type_id for link in question.problem_type_links)),
            concept_ids=tuple(sorted(link.concept_id for link in question.concept_links)),
            learning_outcome_ids=tuple(
                sorted(link.learning_outcome_id for link in question.learning_outcome_links)
            ),
            occurred_at=attempt.created_at,
        )

    @staticmethod
    def _duplicate_answer_error() -> ApplicationError:
        return ApplicationError(
            409,
            "QUESTION_ALREADY_ANSWERED",
            "This question has already been answered in the practice session.",
        )
