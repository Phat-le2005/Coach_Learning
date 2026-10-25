from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import Select, exists, false, func, or_, select
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
from app.learning.models import QuickCheckQuestion
from app.hints.models import PracticeQuestionHint
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionConcept,
    PracticeSessionProblemType,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
    QuestionGroupAttempt,
    QuestionGroupAttemptItem,
)
from app.practice.schemas import (
    PracticeAnswerCreate,
    PracticeGroupAnswerCreate,
    PracticeItemRead,
    PracticeQuestionGroupItemRead,
    PracticeQuestionGroupRead,
    PracticeQuestionRead,
    PracticeSessionCreate,
    PracticeSessionRead,
)
from app.questions.eligibility import standalone_question_only
from app.questions.group_scoring import score_question_group
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionGroup,
    QuestionGroupItem,
    QuestionGroupScoringPolicy,
    QuestionGroupType,
    QuestionLearningOutcome,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
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

    def get_next_item(
        self, current_user: User, practice_session_id: UUID
    ) -> PracticeItemRead:
        student = self._student_for_user(current_user.id)
        practice_session = self._session_or_404(practice_session_id)
        self._authorize_owner(practice_session, student)
        self._require_active(practice_session)
        group = self.session.scalar(
            self._eligible_groups(practice_session, exclude_attempted=True).limit(1)
        )
        if group is not None:
            return PracticeItemRead(
                item_type="QUESTION_GROUP",
                question_group=self.to_group_read(group),
            )
        question = self.session.scalar(
            self._eligible_questions(practice_session, exclude_attempted=True).limit(1)
        )
        if question is not None:
            return PracticeItemRead(
                item_type="QUESTION",
                question=PracticeQuestionRead.model_validate(question),
            )
        raise ApplicationError(
            404,
            "NO_AVAILABLE_PRACTICE_ITEM",
            "No approved eligible practice item remains for this session.",
        )

    def answer(
        self,
        current_user: User,
        practice_session_id: UUID,
        data: PracticeAnswerCreate,
        *,
        commit: bool = True,
        complete_if_exhausted: bool = True,
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
        persisted_hint_count = int(
            self.session.scalar(
                select(func.count())
                .select_from(PracticeQuestionHint)
                .where(
                    PracticeQuestionHint.practice_session_id == practice_session.id,
                    PracticeQuestionHint.question_id == question.id,
                )
            )
            or 0
        )
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
            # Persisted hint history is authoritative once the Hint System has
            # served a hint. The request value remains as a compatibility path
            # for attempts created before hint history existed.
            hint_count=(persisted_hint_count or data.hint_count),
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

            if complete_if_exhausted:
                self._complete_if_exhausted(practice_session)
            if commit:
                self.session.commit()
            else:
                self.session.flush()
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

    def answer_group(
        self,
        current_user: User,
        practice_session_id: UUID,
        data: PracticeGroupAnswerCreate,
        *,
        commit: bool = True,
    ) -> QuestionGroupAttempt:
        student = self._student_for_user(current_user.id)
        practice_session = self.session.scalar(
            self._session_statement()
            .where(PracticeSession.id == practice_session_id)
            .with_for_update()
        )
        if practice_session is None:
            raise ApplicationError(
                404, "PRACTICE_SESSION_NOT_FOUND", "Practice session was not found."
            )
        self._authorize_owner(practice_session, student)
        duplicate = self.session.scalar(
            select(QuestionGroupAttempt.id).where(
                QuestionGroupAttempt.practice_session_id == practice_session.id,
                QuestionGroupAttempt.question_group_id == data.question_group_id,
            )
        )
        if duplicate is not None:
            raise self._duplicate_group_answer_error()
        self._require_active(practice_session)

        group = self.session.scalar(
            self._eligible_groups(practice_session, exclude_attempted=False).where(
                QuestionGroup.id == data.question_group_id
            )
        )
        if group is None:
            raise ApplicationError(
                422,
                "QUESTION_GROUP_NOT_ELIGIBLE",
                "Question group is not approved and fully classified in this session scope.",
            )

        answers = {item.label: item.student_answer for item in data.answers}
        ordered_items = sorted(group.items, key=lambda item: item.order_index)
        evaluations = []
        for item in ordered_items:
            evaluation = self.evaluator.evaluate(item.question, answers[item.label])
            if (
                evaluation.status != EvaluationStatus.AUTO_EVALUATED
                or evaluation.is_correct is None
                or evaluation.score is None
            ):
                raise ApplicationError(
                    422,
                    "QUESTION_GROUP_AUTO_EVALUATION_REQUIRED",
                    "Every group child must support deterministic automatic evaluation.",
                )
            evaluations.append(evaluation)

        previous_attempt_number = self.session.scalar(
            select(func.max(QuestionAttempt.attempt_number)).where(
                QuestionAttempt.practice_session_id == practice_session.id
            )
        )
        first_attempt_number = (previous_attempt_number or 0) + 1
        child_attempts = [
            QuestionAttempt(
                practice_session_id=practice_session.id,
                student_id=student.id,
                question_id=item.question_id,
                student_answer=answers[item.label],
                is_correct=evaluation.is_correct,
                score=evaluation.score,
                response_time_seconds=None,
                hint_count=0,
                attempt_number=first_attempt_number + index,
                evaluation_status=EvaluationStatus.AUTO_EVALUATED,
            )
            for index, (item, evaluation) in enumerate(
                zip(ordered_items, evaluations, strict=True)
            )
        ]
        correctness = [bool(evaluation.is_correct) for evaluation in evaluations]
        group_attempt = QuestionGroupAttempt(
            practice_session_id=practice_session.id,
            student_id=student.id,
            question_group_id=group.id,
            correct_count=sum(correctness),
            score=score_question_group(
                group.scoring_policy, correctness, max_points=1.0
            ),
            response_time_seconds=data.response_time_seconds,
            scoring_policy=group.scoring_policy,
        )

        try:
            self.session.add_all(child_attempts)
            self.session.flush()
            for attempt in child_attempts:
                self.session.refresh(attempt)
            self.session.add(group_attempt)
            self.session.flush()
            group_attempt.attempt_items = [
                QuestionGroupAttemptItem(
                    question_group_item_id=item.id,
                    question_attempt_id=attempt.id,
                    label=item.label,
                    order_index=item.order_index,
                )
                for item, attempt in zip(
                    ordered_items, child_attempts, strict=True
                )
            ]
            self.session.flush()
            for item, attempt in zip(ordered_items, child_attempts, strict=True):
                self.evidence_publisher.publish(
                    self._make_evidence(attempt, practice_session, item.question),
                    self.session,
                )
            self._complete_if_exhausted(practice_session)
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            logger.info(
                "Duplicate/concurrent group answer rejected (session_id=%s, group_id=%s)",
                practice_session_id,
                data.question_group_id,
            )
            raise self._duplicate_group_answer_error() from exc
        except Exception:
            self.session.rollback()
            raise

        logger.info(
            "Question group answer recorded (group_attempt_id=%s, correct_count=%s)",
            group_attempt.id,
            group_attempt.correct_count,
        )
        return group_attempt

    @staticmethod
    def to_group_read(group: QuestionGroup) -> PracticeQuestionGroupRead:
        return PracticeQuestionGroupRead(
            id=group.id,
            subject_id=group.subject_id,
            content=group.content,
            group_type=group.group_type,
            scoring_policy=group.scoring_policy,
            difficulty=group.difficulty,
            exam_weight=group.exam_weight,
            cognitive_level=group.cognitive_level,
            items=[
                PracticeQuestionGroupItemRead(
                    label=item.label,
                    order_index=item.order_index,
                    question_id=item.question_id,
                    content=item.question.content,
                )
                for item in sorted(group.items, key=lambda row: row.order_index)
            ],
        )

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
        if practice_session.session_type == PracticeSessionType.QUICK_CHECK:
            statement = (
                self._question_statement()
                .join(QuickCheckQuestion, QuickCheckQuestion.question_id == Question.id)
                .where(
                    QuickCheckQuestion.quick_check_id == practice_session.id,
                    Question.status == QuestionStatus.APPROVED,
                    standalone_question_only(),
                    or_(Question.question_type == QuestionType.OPEN_RESPONSE,
                        Question.correct_answer.is_not(None)),
                )
                .order_by(QuickCheckQuestion.order_index)
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

        statement = (
            self._question_statement()
            .where(
                Question.subject_id == practice_session.subject_id,
                Question.status == QuestionStatus.APPROVED,
                standalone_question_only(),
                or_(Question.question_type == QuestionType.OPEN_RESPONSE,
                    Question.correct_answer.is_not(None)),
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

    def _eligible_groups(
        self, practice_session: PracticeSession, *, exclude_attempted: bool
    ) -> Select[tuple[QuestionGroup]]:
        if practice_session.session_type == PracticeSessionType.QUICK_CHECK:
            return select(QuestionGroup).where(false())

        item_count = (
            select(func.count(QuestionGroupItem.id))
            .where(QuestionGroupItem.group_id == QuestionGroup.id)
            .correlate(QuestionGroup)
            .scalar_subquery()
        )
        invalid_child = exists(
            select(QuestionGroupItem.id)
            .join(Question, Question.id == QuestionGroupItem.question_id)
            .where(
                QuestionGroupItem.group_id == QuestionGroup.id,
                or_(
                    Question.subject_id != QuestionGroup.subject_id,
                    Question.status != QuestionStatus.APPROVED,
                    Question.question_type != QuestionType.TRUE_FALSE,
                    Question.correct_answer.is_(None),
                    func.upper(func.trim(Question.correct_answer)).not_in(("TRUE", "FALSE")),
                    ~Question.problem_type_links.any(),
                    ~Question.concept_links.any(),
                    ~Question.learning_outcome_links.any(),
                ),
            )
        )
        statement = (
            select(QuestionGroup)
            .options(
                selectinload(QuestionGroup.items)
                .selectinload(QuestionGroupItem.question)
                .selectinload(Question.problem_type_links),
                selectinload(QuestionGroup.items)
                .selectinload(QuestionGroupItem.question)
                .selectinload(Question.concept_links),
                selectinload(QuestionGroup.items)
                .selectinload(QuestionGroupItem.question)
                .selectinload(Question.learning_outcome_links),
                selectinload(QuestionGroup.items)
                .selectinload(QuestionGroupItem.question)
                .selectinload(Question.options),
            )
            .where(
                QuestionGroup.subject_id == practice_session.subject_id,
                QuestionGroup.status == QuestionStatus.APPROVED,
                QuestionGroup.group_type == QuestionGroupType.TRUE_FALSE_FOUR,
                QuestionGroup.scoring_policy
                == QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
                item_count == 4,
                ~invalid_child,
            )
            .order_by(QuestionGroup.created_at, QuestionGroup.id)
        )
        for label, order_index in zip("abcd", range(4), strict=True):
            statement = statement.where(
                exists(
                    select(QuestionGroupItem.id).where(
                        QuestionGroupItem.group_id == QuestionGroup.id,
                        QuestionGroupItem.label == label,
                        QuestionGroupItem.order_index == order_index,
                    )
                )
            )
        problem_type_ids = [
            link.problem_type_id for link in practice_session.problem_type_links
        ]
        if problem_type_ids:
            statement = statement.where(
                exists(
                    select(QuestionGroupItem.id)
                    .join(
                        QuestionProblemType,
                        QuestionProblemType.question_id
                        == QuestionGroupItem.question_id,
                    )
                    .where(
                        QuestionGroupItem.group_id == QuestionGroup.id,
                        QuestionProblemType.problem_type_id.in_(problem_type_ids),
                    )
                )
            )
        concept_ids = [link.concept_id for link in practice_session.concept_links]
        if concept_ids:
            statement = statement.where(
                exists(
                    select(QuestionGroupItem.id)
                    .join(
                        QuestionConcept,
                        QuestionConcept.question_id == QuestionGroupItem.question_id,
                    )
                    .where(
                        QuestionGroupItem.group_id == QuestionGroup.id,
                        QuestionConcept.concept_id.in_(concept_ids),
                    )
                )
            )
        if exclude_attempted:
            statement = statement.where(
                ~exists(
                    select(QuestionGroupAttempt.id).where(
                        QuestionGroupAttempt.practice_session_id
                        == practice_session.id,
                        QuestionGroupAttempt.question_group_id == QuestionGroup.id,
                    )
                )
            )
        return statement

    def _complete_if_exhausted(self, practice_session: PracticeSession) -> None:
        standalone_remaining = self.session.scalar(
            self._eligible_questions(practice_session, exclude_attempted=True).limit(1)
        )
        group_remaining = self.session.scalar(
            self._eligible_groups(practice_session, exclude_attempted=True).limit(1)
        )
        if standalone_remaining is None and group_remaining is None:
            practice_session.status = PracticeSessionStatus.COMPLETED
            practice_session.completed_at = datetime.now(timezone.utc)

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

    @staticmethod
    def _duplicate_group_answer_error() -> ApplicationError:
        return ApplicationError(
            409,
            "QUESTION_GROUP_ALREADY_ANSWERED",
            "This question group has already been answered in the practice session.",
        )
