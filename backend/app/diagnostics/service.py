from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ApplicationError
from app.diagnostics.blueprint import DiagnosticBlueprintService
from app.diagnostics.models import (
    DiagnosticAssessment,
    DiagnosticBlueprintItem,
    DiagnosticCompletionReason,
)
from app.diagnostics.schemas import (
    DiagnosticAnswerCreate,
    DiagnosticAnswerRead,
    DiagnosticChapterSummary,
    DiagnosticConceptMastery,
    DiagnosticProblemTypeMastery,
    DiagnosticQuestionRead,
    DiagnosticResultRead,
    DiagnosticStartCreate,
    DiagnosticStartRead,
    DiagnosticSubjectSummary,
    DiagnosticTopicSummary,
)
from app.diagnostics.selector import DiagnosticQuestionSelector
from app.mastery.models import StudentProblemTypeMastery
from app.mastery.service import MasteryQueryService
from app.practice.models import (
    PracticeSession,
    PracticeSessionProblemType,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.practice.schemas import PracticeQuestionRead, QuestionAttemptRead
from app.practice.service import PracticeService
from app.questions.models import Question, QuestionProblemType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import User

logger = logging.getLogger(__name__)


class DiagnosticService:
    STRONG_MASTERY = 0.65
    WEAK_MASTERY = 0.4
    MIN_CLASSIFICATION_CONFIDENCE = 0.1

    def __init__(self, session: Session) -> None:
        self.session = session
        self.blueprints = DiagnosticBlueprintService(session)
        self.selector = DiagnosticQuestionSelector(session)

    def start(self, current_user: User, data: DiagnosticStartCreate) -> DiagnosticStartRead:
        student = self._student_for_user(current_user.id)
        if self.session.get(Subject, data.subject_id) is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        blueprint = self.blueprints.build(
            data.subject_id,
            max_questions=data.max_questions,
            minimum_problem_type_coverage=data.minimum_problem_type_coverage,
        )
        practice_session = PracticeSession(
            student_id=student.id,
            subject_id=data.subject_id,
            session_type=PracticeSessionType.DIAGNOSTIC,
            problem_type_links=[
                PracticeSessionProblemType(problem_type_id=item_id)
                for item_id in blueprint.problem_type_ids
            ],
        )
        self.session.add(practice_session)
        self.session.flush()
        assessment = DiagnosticAssessment(
            id=practice_session.id,
            max_questions=data.max_questions,
            minimum_problem_type_coverage=data.minimum_problem_type_coverage,
            confidence_threshold=data.confidence_threshold,
            blueprint_items=[
                DiagnosticBlueprintItem(problem_type_id=item_id, order_index=index)
                for index, item_id in enumerate(blueprint.problem_type_ids)
            ],
        )
        self.session.add(assessment)
        self.session.commit()
        logger.info(
            "Diagnostic started (diagnostic_id=%s, student_id=%s, targets=%d)",
            assessment.id,
            student.id,
            len(blueprint.problem_type_ids),
        )
        return self._start_read(assessment, practice_session)

    def next_question(
        self, current_user: User, diagnostic_id: UUID
    ) -> DiagnosticQuestionRead:
        assessment = self._assessment(diagnostic_id, for_update=True)
        practice_session = self._practice_session(diagnostic_id)
        student = self._student_for_user(current_user.id)
        self._authorize_owner(practice_session, student)
        if practice_session.status != PracticeSessionStatus.ACTIVE:
            return self._empty_next(practice_session.status)
        if assessment.current_question_id is not None:
            return self._question_read(
                assessment,
                practice_session.status,
                self._question(assessment.current_question_id),
            )

        question_count, coverage, confidence = self._progress(assessment, student.id)
        reason = self._completion_reason(assessment, question_count, coverage, confidence)
        if reason is not None:
            self._complete(assessment, practice_session, reason)
            self.session.commit()
            return self._empty_next(practice_session.status)

        selection = self.selector.select_next(
            practice_session_id=practice_session.id,
            student_id=student.id,
            subject_id=practice_session.subject_id,
            blueprint_problem_type_ids=[
                item.problem_type_id for item in assessment.blueprint_items
            ],
        )
        if selection is None:
            self._complete(
                assessment,
                practice_session,
                DiagnosticCompletionReason.NO_AVAILABLE_QUESTION,
            )
            self.session.commit()
            return self._empty_next(practice_session.status)

        assessment.current_question_id = selection.question.id
        assessment.current_target_problem_type_id = selection.target_problem_type_id
        assessment.current_target_concept_id = selection.target_concept_id
        assessment.current_difficulty = selection.desired_difficulty
        assessment.current_selection_reason = selection.reason
        self._ensure_question_scope(practice_session, selection.question)
        self.session.commit()
        return self._question_read(assessment, practice_session.status, selection.question)

    def answer(
        self,
        current_user: User,
        diagnostic_id: UUID,
        data: DiagnosticAnswerCreate,
    ) -> DiagnosticAnswerRead:
        assessment = self._assessment(diagnostic_id, for_update=True)
        practice_session = self._practice_session(diagnostic_id)
        student = self._student_for_user(current_user.id)
        self._authorize_owner(practice_session, student)
        if practice_session.status != PracticeSessionStatus.ACTIVE:
            raise ApplicationError(
                409,
                "DIAGNOSTIC_NOT_ACTIVE",
                "Only an active diagnostic can accept answers.",
            )
        if assessment.current_question_id is None:
            raise ApplicationError(
                409,
                "DIAGNOSTIC_QUESTION_NOT_SELECTED",
                "Request the next diagnostic question before answering.",
            )
        if data.question_id != assessment.current_question_id:
            raise ApplicationError(
                422,
                "DIAGNOSTIC_QUESTION_MISMATCH",
                "The answer does not match the current diagnostic question.",
            )

        attempt = PracticeService(self.session).answer(
            current_user,
            diagnostic_id,
            data,
            commit=False,
            complete_if_exhausted=False,
        )
        self._clear_pending(assessment)
        question_count, coverage, confidence = self._progress(assessment, student.id)
        reason = self._completion_reason(assessment, question_count, coverage, confidence)
        if reason is not None:
            self._complete(assessment, practice_session, reason)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        logger.info(
            "Diagnostic answer recorded (diagnostic_id=%s, attempt_id=%s, status=%s)",
            diagnostic_id,
            attempt.id,
            practice_session.status.value,
        )
        return DiagnosticAnswerRead(
            attempt=QuestionAttemptRead.model_validate(attempt),
            status=practice_session.status,
            coverage=coverage,
            confidence=confidence,
            completion_reason=assessment.completion_reason,
        )

    def result(self, current_user: User, diagnostic_id: UUID) -> DiagnosticResultRead:
        assessment = self._assessment(diagnostic_id)
        practice_session = self._practice_session(diagnostic_id)
        student = self._student_for_user(current_user.id)
        self._authorize_owner(practice_session, student)
        if (
            practice_session.status != PracticeSessionStatus.COMPLETED
            or assessment.completion_reason is None
        ):
            raise ApplicationError(
                409,
                "DIAGNOSTIC_NOT_COMPLETED",
                "Diagnostic result is available after the assessment completes.",
            )

        overview = MasteryQueryService(self.session).overview_for_student_id(student.id)
        subject = next(
            (item for item in overview.subjects if item.subject_id == practice_session.subject_id),
            None,
        )
        if subject is None:
            raise RuntimeError("Diagnostic subject is missing from mastery overview")
        problem_types = [
            problem_type
            for chapter in subject.chapters
            for topic in chapter.topics
            for problem_type in topic.problem_types
        ]
        concepts = subject.concepts
        strong_problem_types = [
            item.problem_type_id
            for item in problem_types
            if item.attempt_count > 0
            and item.mastery_score >= self.STRONG_MASTERY
            and item.confidence >= self.MIN_CLASSIFICATION_CONFIDENCE
        ]
        weak_problem_types = [
            item.problem_type_id
            for item in problem_types
            if item.attempt_count > 0
            and item.mastery_score < self.WEAK_MASTERY
            and item.confidence >= self.MIN_CLASSIFICATION_CONFIDENCE
        ]
        strong_concepts = [
            item.concept_id
            for item in concepts
            if item.attempt_count > 0
            and item.mastery_score >= self.STRONG_MASTERY
            and item.confidence >= self.MIN_CLASSIFICATION_CONFIDENCE
        ]
        weak_concepts = [
            item.concept_id
            for item in concepts
            if item.attempt_count > 0
            and item.mastery_score < self.WEAK_MASTERY
            and item.confidence >= self.MIN_CLASSIFICATION_CONFIDENCE
        ]
        blueprint_ids = [item.problem_type_id for item in assessment.blueprint_items]
        by_problem_type = {item.problem_type_id: item for item in problem_types}
        recommended = sorted(
            blueprint_ids,
            key=lambda item_id: self._starting_priority(by_problem_type[item_id]),
        )[:5]
        question_count, coverage, confidence = self._progress(assessment, student.id)

        return DiagnosticResultRead(
            diagnostic_id=assessment.id,
            student_id=student.id,
            completion_reason=assessment.completion_reason,
            question_count=question_count,
            coverage=coverage,
            confidence=confidence,
            subject_summary=DiagnosticSubjectSummary(
                subject_id=subject.subject_id,
                code=subject.code,
                name=subject.name,
                **self._metric(subject),
            ),
            chapter_summary=[
                DiagnosticChapterSummary(
                    chapter_id=chapter.chapter_id,
                    code=chapter.code,
                    name=chapter.name,
                    **self._metric(chapter),
                )
                for chapter in subject.chapters
            ],
            topic_summary=[
                DiagnosticTopicSummary(
                    topic_id=topic.topic_id,
                    chapter_id=topic.chapter_id,
                    code=topic.code,
                    name=topic.name,
                    **self._metric(topic),
                )
                for chapter in subject.chapters
                for topic in chapter.topics
            ],
            problem_type_mastery=[
                DiagnosticProblemTypeMastery(
                    problem_type_id=item.problem_type_id,
                    topic_id=item.topic_id,
                    code=item.code,
                    name=item.name,
                    **self._metric(item),
                )
                for item in problem_types
            ],
            concept_mastery=[
                DiagnosticConceptMastery(
                    concept_id=item.concept_id,
                    code=item.code,
                    name=item.name,
                    **self._metric(item),
                )
                for item in concepts
            ],
            strong_problem_types=strong_problem_types,
            weak_problem_types=weak_problem_types,
            strong_concepts=strong_concepts,
            weak_concepts=weak_concepts,
            recommended_starting_problem_types=recommended,
        )

    def _assessment(
        self, diagnostic_id: UUID, *, for_update: bool = False
    ) -> DiagnosticAssessment:
        statement = (
            select(DiagnosticAssessment)
            .options(selectinload(DiagnosticAssessment.blueprint_items))
            .where(DiagnosticAssessment.id == diagnostic_id)
        )
        if for_update:
            statement = statement.with_for_update()
        assessment = self.session.scalar(statement)
        if assessment is None:
            raise ApplicationError(
                404, "DIAGNOSTIC_NOT_FOUND", "Diagnostic assessment was not found."
            )
        return assessment

    def _practice_session(self, diagnostic_id: UUID) -> PracticeSession:
        practice_session = self.session.get(PracticeSession, diagnostic_id)
        if (
            practice_session is None
            or practice_session.session_type != PracticeSessionType.DIAGNOSTIC
        ):
            raise ApplicationError(
                404, "DIAGNOSTIC_NOT_FOUND", "Diagnostic assessment was not found."
            )
        return practice_session

    def _question(self, question_id: UUID) -> Question:
        question = self.session.scalar(
            select(Question)
            .options(
                selectinload(Question.options),
                selectinload(Question.problem_type_links),
                selectinload(Question.concept_links),
                selectinload(Question.learning_outcome_links),
            )
            .where(Question.id == question_id)
        )
        if question is None:
            raise RuntimeError("Pending diagnostic question no longer exists")
        return question

    def _progress(
        self, assessment: DiagnosticAssessment, student_id: UUID
    ) -> tuple[int, float, float]:
        blueprint_ids = [item.problem_type_id for item in assessment.blueprint_items]
        question_count = self.session.scalar(
            select(func.count())
            .select_from(QuestionAttempt)
            .where(QuestionAttempt.practice_session_id == assessment.id)
        ) or 0
        covered = set(
            self.session.scalars(
                select(QuestionProblemType.problem_type_id)
                .join(
                    QuestionAttempt,
                    QuestionAttempt.question_id == QuestionProblemType.question_id,
                )
                .where(
                    QuestionAttempt.practice_session_id == assessment.id,
                    QuestionProblemType.problem_type_id.in_(blueprint_ids),
                )
                .distinct()
            )
        )
        confidence_by_id = {
            item.problem_type_id: item.confidence
            for item in self.session.scalars(
                select(StudentProblemTypeMastery).where(
                    StudentProblemTypeMastery.student_id == student_id,
                    StudentProblemTypeMastery.problem_type_id.in_(blueprint_ids),
                )
            )
        }
        coverage = len(covered) / len(blueprint_ids)
        confidence = sum(confidence_by_id.get(item_id, 0.0) for item_id in blueprint_ids) / len(
            blueprint_ids
        )
        return int(question_count), round(coverage, 6), round(confidence, 6)

    @staticmethod
    def _completion_reason(
        assessment: DiagnosticAssessment,
        question_count: int,
        coverage: float,
        confidence: float,
    ) -> DiagnosticCompletionReason | None:
        if question_count >= assessment.max_questions:
            return DiagnosticCompletionReason.MAX_QUESTIONS
        if (
            coverage >= assessment.minimum_problem_type_coverage
            and confidence >= assessment.confidence_threshold
        ):
            return DiagnosticCompletionReason.CONFIDENCE_REACHED
        return None

    @staticmethod
    def _complete(
        assessment: DiagnosticAssessment,
        practice_session: PracticeSession,
        reason: DiagnosticCompletionReason,
    ) -> None:
        DiagnosticService._clear_pending(assessment)
        assessment.completion_reason = reason
        practice_session.status = PracticeSessionStatus.COMPLETED
        practice_session.completed_at = datetime.now(timezone.utc)

    @staticmethod
    def _clear_pending(assessment: DiagnosticAssessment) -> None:
        assessment.current_question_id = None
        assessment.current_target_problem_type_id = None
        assessment.current_target_concept_id = None
        assessment.current_difficulty = None
        assessment.current_selection_reason = None

    @staticmethod
    def _ensure_question_scope(
        practice_session: PracticeSession, question: Question
    ) -> None:
        existing = {item.problem_type_id for item in practice_session.problem_type_links}
        for link in question.problem_type_links:
            if link.problem_type_id not in existing:
                practice_session.problem_type_links.append(
                    PracticeSessionProblemType(problem_type_id=link.problem_type_id)
                )
                existing.add(link.problem_type_id)

    @staticmethod
    def _authorize_owner(
        practice_session: PracticeSession, student: StudentProfile
    ) -> None:
        if practice_session.student_id != student.id:
            raise ApplicationError(
                403,
                "DIAGNOSTIC_ACCESS_DENIED",
                "You do not have access to this diagnostic assessment.",
            )

    def _student_for_user(self, user_id: UUID) -> StudentProfile:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if student is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
        return student

    @staticmethod
    def _start_read(
        assessment: DiagnosticAssessment, practice_session: PracticeSession
    ) -> DiagnosticStartRead:
        return DiagnosticStartRead(
            id=assessment.id,
            subject_id=practice_session.subject_id,
            status=practice_session.status,
            max_questions=assessment.max_questions,
            minimum_problem_type_coverage=assessment.minimum_problem_type_coverage,
            confidence_threshold=assessment.confidence_threshold,
            blueprint_problem_type_ids=[
                item.problem_type_id for item in assessment.blueprint_items
            ],
            started_at=practice_session.started_at,
        )

    @staticmethod
    def _question_read(
        assessment: DiagnosticAssessment,
        status: PracticeSessionStatus,
        question: Question,
    ) -> DiagnosticQuestionRead:
        return DiagnosticQuestionRead(
            status=status,
            question=PracticeQuestionRead.model_validate(question),
            target_problem_type_id=assessment.current_target_problem_type_id,
            target_concept_id=assessment.current_target_concept_id,
            desired_difficulty=assessment.current_difficulty,
            selection_reason=assessment.current_selection_reason,
        )

    @staticmethod
    def _empty_next(status: PracticeSessionStatus) -> DiagnosticQuestionRead:
        return DiagnosticQuestionRead(
            status=status,
            question=None,
            target_problem_type_id=None,
            target_concept_id=None,
            desired_difficulty=None,
            selection_reason=None,
        )

    @staticmethod
    def _metric(item: object) -> dict[str, object]:
        return {
            "mastery_score": getattr(item, "mastery_score"),
            "confidence": getattr(item, "confidence"),
            "attempt_count": getattr(item, "attempt_count"),
            "correct_count": getattr(item, "correct_count"),
            "state": getattr(item, "state"),
        }

    @staticmethod
    def _starting_priority(item: object) -> tuple[int, float, float, str]:
        mastery_score = float(getattr(item, "mastery_score"))
        attempt_count = int(getattr(item, "attempt_count"))
        confidence = float(getattr(item, "confidence"))
        problem_type_id = getattr(item, "problem_type_id")
        if attempt_count > 0 and mastery_score < DiagnosticService.WEAK_MASTERY:
            group = 0
        elif attempt_count == 0:
            group = 1
        else:
            group = 2
        return group, mastery_score, confidence, str(problem_type_id)
