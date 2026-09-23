from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ApplicationError
from app.curriculum.models import ProblemTypeConcept
from app.exams.analytics_service import ExamAnalyticsService
from app.exams.models import (
    Exam,
    ExamAttempt,
    ExamAttemptStatus,
    ExamQuestion,
    ExamResponse,
    ExamSection,
    ExamStatus,
    ExamType,
)
from app.exams.schemas import (
    ExamAttemptResultRead,
    ExamAttemptStartRead,
    ExamAttemptStatusRead,
    ExamOptionSanitizedRead,
    ExamQuestionSanitizedRead,
    ExamResponseRead,
    ExamResponseSubmitRequest,
    ExamSectionRead,
)
from app.exams.scoring_service import ExamScoringService
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.mastery.strategy import (
    AttemptEvidence,
    DeterministicMasteryCalculationStrategy,
    MappingEvidence,
    MasteryState,
    QuestionEvidence,
)
from app.questions.models import Question
from app.students.models import StudentProfile

logger = logging.getLogger(__name__)


def _as_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ExamSimulationService:
    """Orchestrates the end-to-end Student Exam Simulator workflow.

    Workflow Stages:
    start -> answer -> timer -> submit -> backend score -> analytics

    Strict Architectural Guarantees:
    - REAL_SIMULATION Mode: Zero Hints, Zero AI Tutor.
    - Deterministic Scoring: Handled by ExamScoringService without LLMs.
    - Multi-dimensional Analytics: Handled by ExamAnalyticsService.
    - Mastery Engine Isolation: Exam attempts DO NOT mutate official student mastery
      unless an explicit policy is requested (update_mastery=True), and when enabled,
      updates are routed through the official Mastery Engine strategy.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.scoring_service = ExamScoringService(session)
        self.analytics_service = ExamAnalyticsService(session)
        self.mastery_strategy = DeterministicMasteryCalculationStrategy()

    # --------------------------------------------------------------------------
    # 1. Start Exam Simulation
    # --------------------------------------------------------------------------

    def start_exam(
        self,
        student_user_id: UUID,
        exam_id: UUID,
    ) -> ExamAttemptStartRead:
        student = self._require_student(student_user_id)
        exam = self.session.scalar(
            select(Exam)
            .options(
                selectinload(Exam.sections),
                selectinload(Exam.questions).selectinload(ExamQuestion.question).selectinload(Question.options),
            )
            .where(Exam.id == exam_id)
        )
        if exam is None:
            raise ApplicationError(404, "EXAM_NOT_FOUND", "Exam was not found.")

        if exam.status != ExamStatus.PUBLISHED:
            raise ApplicationError(
                400,
                "EXAM_NOT_PUBLISHED",
                "Cannot start an exam that has not been published.",
            )

        if not exam.questions:
            raise ApplicationError(
                400,
                "EXAM_EMPTY",
                "Exam has no questions assembled.",
            )

        # Check for existing IN_PROGRESS attempt
        existing_attempt = self.session.scalar(
            select(ExamAttempt)
            .where(
                ExamAttempt.exam_id == exam.id,
                ExamAttempt.student_id == student.id,
                ExamAttempt.status == ExamAttemptStatus.IN_PROGRESS,
            )
            .order_by(ExamAttempt.started_at.desc())
        )

        now = datetime.now(timezone.utc)

        if existing_attempt:
            # Check if expired
            expires_at = _as_utc(existing_attempt.started_at) + timedelta(minutes=exam.duration_minutes)
            if now > expires_at:
                # Auto-submit expired attempt
                self.submit_exam(student_user_id, existing_attempt.id)
            else:
                return self._build_start_read(existing_attempt, exam, now)

        # Create new attempt
        attempt = ExamAttempt(
            exam_id=exam.id,
            student_id=student.id,
            status=ExamAttemptStatus.IN_PROGRESS,
            started_at=now,
            total_points=exam.total_points,
        )
        self.session.add(attempt)
        self.session.flush()

        return self._build_start_read(attempt, exam, now)

    # --------------------------------------------------------------------------
    # 2. Record Response (with Timer & Sequence Tracking)
    # --------------------------------------------------------------------------

    def record_response(
        self,
        student_user_id: UUID,
        attempt_id: UUID,
        req: ExamResponseSubmitRequest,
    ) -> ExamResponseRead:
        student = self._require_student(student_user_id)
        attempt = self.session.scalar(
            select(ExamAttempt)
            .options(selectinload(ExamAttempt.exam))
            .where(ExamAttempt.id == attempt_id, ExamAttempt.student_id == student.id)
        )
        if attempt is None:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Exam attempt not found.")

        if attempt.status != ExamAttemptStatus.IN_PROGRESS:
            raise ApplicationError(
                400,
                "ATTEMPT_NOT_ACTIVE",
                f"Cannot submit response to an attempt with status {attempt.status}.",
            )

        # Check timer with 60s grace period
        now = datetime.now(timezone.utc)
        expires_at = _as_utc(attempt.started_at) + timedelta(minutes=attempt.exam.duration_minutes)
        if now > expires_at + timedelta(seconds=60):
            attempt.status = ExamAttemptStatus.TIMED_OUT
            self.session.flush()
            self.scoring_service.score_attempt(attempt.id)
            raise ApplicationError(
                400,
                "EXAM_TIMED_OUT",
                "Exam duration has expired. Attempt has been automatically submitted.",
            )

        # Verify question belongs to this exam
        eq = self.session.scalar(
            select(ExamQuestion).where(
                ExamQuestion.exam_id == attempt.exam_id,
                ExamQuestion.question_id == req.question_id,
            )
        )
        if eq is None:
            raise ApplicationError(
                400,
                "QUESTION_NOT_IN_EXAM",
                "Question is not part of this exam.",
            )

        # Find or create response
        response = self.session.scalar(
            select(ExamResponse).where(
                ExamResponse.attempt_id == attempt.id,
                ExamResponse.question_id == req.question_id,
            )
        )

        # Calculate chronological order_answered
        current_max_order = self.session.scalar(
            select(ExamResponse.order_answered)
            .where(ExamResponse.attempt_id == attempt.id)
            .order_by(ExamResponse.order_answered.desc())
            .limit(1)
        ) or 0

        next_order = current_max_order + 1

        if response is None:
            response = ExamResponse(
                attempt_id=attempt.id,
                question_id=req.question_id,
                student_answer=req.student_answer,
                selected_option_id=req.selected_option_id,
                response_time_seconds=req.response_time_seconds,
                answered_at=now,
                order_answered=next_order,
            )
            self.session.add(response)
        else:
            response.student_answer = req.student_answer
            response.selected_option_id = req.selected_option_id
            response.response_time_seconds = req.response_time_seconds
            response.answered_at = now
            if response.order_answered == 0:
                response.order_answered = next_order

        self.session.flush()

        return ExamResponseRead.model_validate(response)

    # --------------------------------------------------------------------------
    # 3. Check Attempt Status & Timer
    # --------------------------------------------------------------------------

    def get_attempt_status(
        self,
        student_user_id: UUID,
        attempt_id: UUID,
    ) -> ExamAttemptStatusRead:
        student = self._require_student(student_user_id)
        attempt = self.session.scalar(
            select(ExamAttempt)
            .options(
                selectinload(ExamAttempt.responses),
                selectinload(ExamAttempt.exam).selectinload(Exam.questions),
            )
            .where(ExamAttempt.id == attempt_id, ExamAttempt.student_id == student.id)
        )
        if attempt is None:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Exam attempt not found.")

        now = datetime.now(timezone.utc)
        expires_at = _as_utc(attempt.started_at) + timedelta(minutes=attempt.exam.duration_minutes)
        time_rem = max(0, int((expires_at - now).total_seconds()))

        # If expired and still IN_PROGRESS, auto-submit
        if time_rem == 0 and attempt.status == ExamAttemptStatus.IN_PROGRESS:
            attempt.status = ExamAttemptStatus.TIMED_OUT
            self.session.flush()
            self.scoring_service.score_attempt(attempt.id)

        answered_count = sum(
            1 for r in attempt.responses if r.student_answer and r.student_answer.strip()
        )

        return ExamAttemptStatusRead(
            attempt_id=attempt.id,
            exam_id=attempt.exam_id,
            status=attempt.status,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
            duration_seconds=attempt.duration_seconds,
            time_remaining_seconds=time_rem,
            answered_count=answered_count,
            total_questions=len(attempt.exam.questions),
            responses=[ExamResponseRead.model_validate(r) for r in attempt.responses],
        )

    # --------------------------------------------------------------------------
    # 4. Submit Exam (Scoring, Analytics & Optional Mastery Policy)
    # --------------------------------------------------------------------------

    def submit_exam(
        self,
        student_user_id: UUID,
        attempt_id: UUID,
        update_mastery: bool = False,
    ) -> ExamAttemptResultRead:
        student = self._require_student(student_user_id)
        attempt = self.session.scalar(
            select(ExamAttempt)
            .options(
                selectinload(ExamAttempt.responses),
                selectinload(ExamAttempt.exam).selectinload(Exam.questions),
            )
            .where(ExamAttempt.id == attempt_id, ExamAttempt.student_id == student.id)
        )
        if attempt is None:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Exam attempt not found.")

        now = datetime.now(timezone.utc)

        # Calculate duration
        if not attempt.submitted_at:
            attempt.submitted_at = now
            elapsed = int((now - _as_utc(attempt.started_at)).total_seconds())
            max_allowed = attempt.exam.duration_minutes * 60
            attempt.duration_seconds = min(elapsed, max_allowed)

        # 1. Deterministic scoring (No LLM)
        self.scoring_service.score_attempt(attempt.id)
        self.session.refresh(attempt)

        # 2. Comprehensive analytics
        analytics = self.analytics_service.generate_analytics(attempt.id)

        # 3. Explicit Mastery Engine Policy
        # Rule: Exam performance KHÔNG trực tiếp thay đổi official mastery trừ khi policy explicit.
        official_mastery_updated = False
        if update_mastery:
            self._update_mastery_via_engine(attempt)
            official_mastery_updated = True

        self.session.flush()

        return ExamAttemptResultRead(
            attempt_id=attempt.id,
            exam_id=attempt.exam_id,
            student_id=attempt.student_id,
            status=attempt.status,
            score=attempt.score or 0.0,
            score_10=analytics.score_10,
            total_points=attempt.total_points,
            accuracy=attempt.accuracy or 0.0,
            duration_seconds=attempt.duration_seconds,
            analytics=analytics,
            official_mastery_updated=official_mastery_updated,
        )

    # --------------------------------------------------------------------------
    # 5. REAL_SIMULATION Guardrails (No Hints, No Tutor)
    # --------------------------------------------------------------------------

    def assert_hints_allowed(self, attempt_id: UUID) -> None:
        """Enforce REAL_SIMULATION guardrail: Hints strictly forbidden."""
        attempt = self.session.scalar(
            select(ExamAttempt).options(selectinload(ExamAttempt.exam)).where(ExamAttempt.id == attempt_id)
        )
        if attempt and attempt.exam.exam_type == ExamType.REAL_SIMULATION:
            raise ApplicationError(
                403,
                "HINTS_NOT_ALLOWED_IN_REAL_SIMULATION",
                "Hints are strictly prohibited during a real exam simulation.",
            )

    def assert_tutor_allowed(self, attempt_id: UUID) -> None:
        """Enforce REAL_SIMULATION guardrail: AI Tutor strictly forbidden."""
        attempt = self.session.scalar(
            select(ExamAttempt).options(selectinload(ExamAttempt.exam)).where(ExamAttempt.id == attempt_id)
        )
        if attempt and attempt.exam.exam_type == ExamType.REAL_SIMULATION:
            raise ApplicationError(
                403,
                "TUTOR_NOT_ALLOWED_IN_REAL_SIMULATION",
                "AI Tutor assistance is strictly prohibited during a real exam simulation.",
            )

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------

    def _require_student(self, user_id: UUID) -> StudentProfile:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if student is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile not found.")
        return student

    def _build_start_read(
        self,
        attempt: ExamAttempt,
        exam: Exam,
        now: datetime,
    ) -> ExamAttemptStartRead:
        expires_at = _as_utc(attempt.started_at) + timedelta(minutes=exam.duration_minutes)
        time_rem = max(0, int((expires_at - now).total_seconds()))

        # Sanitize questions (no correct answers / explanations)
        sanitized_questions: list[ExamQuestionSanitizedRead] = []
        for eq in exam.questions:
            q = eq.question
            options = [
                ExamOptionSanitizedRead(
                    id=opt.id,
                    label=opt.label,
                    content=opt.content,
                    order_index=opt.order_index,
                )
                for opt in q.options
            ]
            sanitized_questions.append(
                ExamQuestionSanitizedRead(
                    id=eq.id,
                    question_id=eq.question_id,
                    section_id=eq.section_id,
                    order_index=eq.order_index,
                    points=eq.points,
                    content=q.content,
                    question_type=q.question_type,
                    difficulty=q.difficulty,
                    cognitive_level=q.cognitive_level,
                    options=options,
                )
            )

        sections_read = [
            ExamSectionRead.model_validate(s) for s in exam.sections
        ]

        return ExamAttemptStartRead(
            attempt_id=attempt.id,
            exam_id=exam.id,
            exam_title=exam.title,
            exam_type=exam.exam_type,
            duration_minutes=exam.duration_minutes,
            started_at=attempt.started_at,
            expires_at=expires_at,
            time_remaining_seconds=time_rem,
            total_questions=len(exam.questions),
            total_points=exam.total_points,
            sections=sections_read,
            questions=sanitized_questions,
        )

    def _update_mastery_via_engine(self, attempt: ExamAttempt) -> None:
        """Route exam attempt results through official Mastery Engine calculation strategy."""
        now = datetime.now(timezone.utc)
        for resp in attempt.responses:
            if not resp.student_answer:
                continue

            q = self.session.scalar(
                select(Question)
                .options(
                    selectinload(Question.concept_links),
                    selectinload(Question.problem_type_links),
                )
                .where(Question.id == resp.question_id)
            )
            if not q:
                continue

            q_evidence = QuestionEvidence(difficulty=q.difficulty)
            att_evidence = AttemptEvidence(
                is_correct=bool(resp.is_correct),
                score=resp.score_awarded or 0.0,
                hint_count=0,
                response_time_seconds=resp.response_time_seconds,
            )

            # 1. Update Concept Mastery
            for c_link in q.concept_links:
                c_row = self.session.scalar(
                    select(StudentConceptMastery).where(
                        StudentConceptMastery.student_id == attempt.student_id,
                        StudentConceptMastery.concept_id == c_link.concept_id,
                    )
                )
                prev_state = (
                    MasteryState(
                        mastery_score=c_row.mastery_score,
                        confidence=c_row.confidence,
                        attempt_count=c_row.attempt_count,
                        correct_count=c_row.correct_count,
                    )
                    if c_row
                    else MasteryState()
                )
                next_state = self.mastery_strategy.calculate_from_attempt(
                    prev_state,
                    q_evidence,
                    MappingEvidence(weight=c_link.weight),
                    att_evidence,
                )
                if c_row is None:
                    c_row = StudentConceptMastery(
                        student_id=attempt.student_id,
                        concept_id=c_link.concept_id,
                        mastery_score=next_state.mastery_score,
                        confidence=next_state.confidence,
                        attempt_count=next_state.attempt_count,
                        correct_count=next_state.correct_count,
                        last_practiced_at=now,
                        last_updated_at=now,
                    )
                    self.session.add(c_row)
                else:
                    c_row.mastery_score = next_state.mastery_score
                    c_row.confidence = next_state.confidence
                    c_row.attempt_count = next_state.attempt_count
                    c_row.correct_count = next_state.correct_count
                    c_row.last_practiced_at = now
                    c_row.last_updated_at = now

            # 2. Update ProblemType Mastery
            for pt_link in q.problem_type_links:
                pt_row = self.session.scalar(
                    select(StudentProblemTypeMastery).where(
                        StudentProblemTypeMastery.student_id == attempt.student_id,
                        StudentProblemTypeMastery.problem_type_id == pt_link.problem_type_id,
                    )
                )
                prev_state = (
                    MasteryState(
                        mastery_score=pt_row.mastery_score,
                        confidence=pt_row.confidence,
                        attempt_count=pt_row.attempt_count,
                        correct_count=pt_row.correct_count,
                    )
                    if pt_row
                    else MasteryState()
                )
                next_state = self.mastery_strategy.calculate_from_attempt(
                    prev_state,
                    q_evidence,
                    MappingEvidence(weight=pt_link.weight or 1.0),
                    att_evidence,
                )
                if pt_row is None:
                    pt_row = StudentProblemTypeMastery(
                        student_id=attempt.student_id,
                        problem_type_id=pt_link.problem_type_id,
                        mastery_score=next_state.mastery_score,
                        confidence=next_state.confidence,
                        attempt_count=next_state.attempt_count,
                        correct_count=next_state.correct_count,
                        last_practiced_at=now,
                        last_updated_at=now,
                    )
                    self.session.add(pt_row)
                else:
                    pt_row.mastery_score = next_state.mastery_score
                    pt_row.confidence = next_state.confidence
                    pt_row.attempt_count = next_state.attempt_count
                    pt_row.correct_count = next_state.correct_count
                    pt_row.last_practiced_at = now
                    pt_row.last_updated_at = now

        self.session.flush()
