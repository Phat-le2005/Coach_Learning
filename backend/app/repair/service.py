from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.mastery.evidence import MasteryAttemptEvidencePublisher
from app.misconceptions.service import MisconceptionService
from app.practice.evaluation import AnswerEvaluationService
from app.practice.evidence import AttemptEvaluatedEvidence, AttemptEvidencePublisher
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionConcept,
    PracticeSessionProblemType,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionStatus,
)
from app.repair.policy import RepairPolicy
from app.repair.schemas import (
    RepairAnswerResult,
    RepairAnswerSubmit,
    RepairEvaluationResult,
    RepairSessionCreate,
    RepairSessionRead,
    RepairStepQuestionOptionRead,
    RepairStepRead,
    RepairStepRole,
    RepairTargetType,
    RepairTriggerType,
)
from app.students.models import StudentProfile
from app.users.models import User

logger = logging.getLogger(__name__)


class RepairSessionService:
    """Orchestrates structured Repair Sessions for struggling ProblemTypes or prerequisite Concepts.

    Pedagogical sequence:
        Step 1: Brief Review (Foundational recap & pitfall awareness)
        Step 2: Easy Verification (Recall / elementary check)
        Step 3: Guided Practice (Scaffolding & hints enabled)
        Step 4: Medium Practice (Standard target difficulty)
        Step 5: Final Recheck (Exit verification of gap resolution)
    """

    def __init__(
        self,
        session: Session,
        policy: RepairPolicy | None = None,
        evidence_publisher: AttemptEvidencePublisher | None = None,
        evaluator: AnswerEvaluationService | None = None,
        misconception_service: MisconceptionService | None = None,
    ) -> None:
        self.session = session
        self.policy = policy or RepairPolicy()
        self.evidence_publisher = evidence_publisher or MasteryAttemptEvidencePublisher()
        self.evaluator = evaluator or AnswerEvaluationService()
        self.misconception_service = misconception_service or MisconceptionService(session)

    # --------------------------------------------------------------------------
    # Start Repair Session
    # --------------------------------------------------------------------------

    def start_repair_session(
        self,
        current_user: User,
        data: RepairSessionCreate,
    ) -> RepairSessionRead:
        """Create and initialize a new 5-step Repair Session from APPROVED Question Bank."""
        student = self._student_for_user(current_user.id)

        # 1. Resolve target and subject
        target_name = ""
        target_code = ""
        subject_id: UUID

        if data.target_type == RepairTargetType.PROBLEM_TYPE:
            pt = self.session.get(ProblemType, data.target_id)
            if pt is None:
                raise ApplicationError(404, "PROBLEM_TYPE_NOT_FOUND", "Target problem type not found.")
            target_name = pt.name
            target_code = pt.code
            subject_id = self.session.scalar(
                select(Chapter.subject_id)
                .join(Topic, Topic.chapter_id == Chapter.id)
                .join(ProblemType, ProblemType.topic_id == Topic.id)
                .where(ProblemType.id == pt.id)
            )
            if subject_id is None:
                raise ApplicationError(422, "SUBJECT_RESOLUTION_FAILED", "Could not resolve subject for problem type.")
        else:
            concept = self.session.get(Concept, data.target_id)
            if concept is None:
                raise ApplicationError(404, "CONCEPT_NOT_FOUND", "Target prerequisite concept not found.")
            target_name = concept.name
            target_code = concept.code
            subject_id = concept.subject_id

        # 2. Create PracticeSession with session_type = REPAIR
        practice_session = PracticeSession(
            student_id=student.id,
            subject_id=subject_id,
            session_type=PracticeSessionType.REPAIR,
            status=PracticeSessionStatus.ACTIVE,
        )
        self.session.add(practice_session)
        self.session.flush()

        # 3. Associate target links
        if data.target_type == RepairTargetType.PROBLEM_TYPE:
            pt_link = PracticeSessionProblemType(
                practice_session_id=practice_session.id,
                problem_type_id=data.target_id,
            )
            self.session.add(pt_link)
        else:
            c_link = PracticeSessionConcept(
                practice_session_id=practice_session.id,
                concept_id=data.target_id,
            )
            self.session.add(c_link)

        # 4. Select questions from APPROVED Question Bank
        selected_questions = self._select_questions(
            target_type=data.target_type,
            target_id=data.target_id,
            subject_id=subject_id,
        )

        self.session.commit()

        # 5. Build and return the 5-step sequence
        return self._build_session_read(
            practice_session=practice_session,
            target_type=data.target_type,
            target_id=data.target_id,
            target_name=target_name,
            target_code=target_code,
            trigger=data.trigger,
            questions=selected_questions,
            attempts=[],
        )

    # --------------------------------------------------------------------------
    # View Session
    # --------------------------------------------------------------------------

    def get_repair_session(
        self,
        current_user: User,
        session_id: UUID,
    ) -> RepairSessionRead:
        """Retrieve details and progress of an existing repair session."""
        student = self._student_for_user(current_user.id)
        practice_session = self.session.get(PracticeSession, session_id)
        if practice_session is None:
            raise ApplicationError(404, "SESSION_NOT_FOUND", "Repair session not found.")
        if practice_session.student_id != student.id:
            raise ApplicationError(403, "SESSION_ACCESS_DENIED", "Access denied to this repair session.")
        if practice_session.session_type != PracticeSessionType.REPAIR:
            raise ApplicationError(400, "INVALID_SESSION_TYPE", "Session is not a repair session.")

        target_type, target_id, target_name, target_code = self._resolve_session_target(practice_session)
        questions = self._get_session_questions(practice_session, target_type, target_id)
        attempts = list(
            self.session.scalars(
                select(QuestionAttempt)
                .where(QuestionAttempt.practice_session_id == practice_session.id)
                .order_by(QuestionAttempt.attempt_number)
            ).all()
        )

        return self._build_session_read(
            practice_session=practice_session,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            target_code=target_code,
            trigger=None,
            questions=questions,
            attempts=attempts,
        )

    # --------------------------------------------------------------------------
    # Submit Step Answer
    # --------------------------------------------------------------------------

    def submit_step_answer(
        self,
        current_user: User,
        session_id: UUID,
        step_number: int,
        data: RepairAnswerSubmit,
    ) -> RepairAnswerResult:
        """Submit an answer for an active question step (steps 2 to 5)."""
        if step_number < 2 or step_number > 5:
            raise ApplicationError(
                400,
                "INVALID_QUESTION_STEP",
                f"Step {step_number} is not an answerable question step. Questions are at steps 2 to 5.",
            )

        student = self._student_for_user(current_user.id)
        practice_session = self.session.get(PracticeSession, session_id)
        if practice_session is None:
            raise ApplicationError(404, "SESSION_NOT_FOUND", "Repair session not found.")
        if practice_session.student_id != student.id:
            raise ApplicationError(403, "SESSION_ACCESS_DENIED", "Access denied to this repair session.")
        if practice_session.status != PracticeSessionStatus.ACTIVE:
            raise ApplicationError(400, "SESSION_NOT_ACTIVE", "Repair session is no longer active.")

        target_type, target_id, _, _ = self._resolve_session_target(practice_session)
        questions = self._get_session_questions(practice_session, target_type, target_id)
        q_idx = step_number - 2
        if q_idx >= len(questions):
            raise ApplicationError(404, "STEP_QUESTION_NOT_FOUND", "No question assigned for this step.")

        question = questions[q_idx]

        # Prevent duplicate submissions for the same question in this session
        existing = self.session.scalar(
            select(QuestionAttempt).where(
                QuestionAttempt.practice_session_id == practice_session.id,
                QuestionAttempt.question_id == question.id,
            )
        )
        if existing is not None:
            raise ApplicationError(409, "STEP_ALREADY_ATTEMPTED", "This step has already been completed.")

        # Evaluate the answer deterministically
        evaluation = self.evaluator.evaluate(question, data.student_answer)

        # Create standard QuestionAttempt
        attempt = QuestionAttempt(
            practice_session_id=practice_session.id,
            student_id=student.id,
            question_id=question.id,
            student_answer=data.student_answer,
            is_correct=evaluation.is_correct,
            score=evaluation.score,
            response_time_seconds=data.response_time_seconds,
            hint_count=data.hint_count,
            attempt_number=step_number - 1,
            evaluation_status=evaluation.status,
        )
        self.session.add(attempt)
        self.session.flush()

        # Normal evidence flow to Mastery Engine (AI NEVER sets mastery directly!)
        if (
            attempt.evaluation_status in {EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED}
            and attempt.is_correct is not None
            and attempt.score is not None
        ):
            evidence = self._make_evidence(attempt, practice_session, question)
            self.evidence_publisher.publish(evidence, self.session)

        self.session.commit()

        return RepairAnswerResult(
            step_number=step_number,
            question_id=question.id,
            is_correct=attempt.is_correct,
            score=attempt.score,
            evaluation_status=attempt.evaluation_status,
            explanation=question.explanation,
        )

    # --------------------------------------------------------------------------
    # Complete & Evaluate Session (Deterministic Success Criteria)
    # --------------------------------------------------------------------------

    def evaluate_session_completion(
        self,
        current_user: User,
        session_id: UUID,
        *,
        misconception_definition_id: UUID | None = None,
    ) -> RepairEvaluationResult:
        """Deterministically evaluate session completion against policy requirements."""
        student = self._student_for_user(current_user.id)
        practice_session = self.session.get(PracticeSession, session_id)
        if practice_session is None:
            raise ApplicationError(404, "SESSION_NOT_FOUND", "Repair session not found.")
        if practice_session.student_id != student.id:
            raise ApplicationError(403, "SESSION_ACCESS_DENIED", "Access denied to this repair session.")

        attempts = list(
            self.session.scalars(
                select(QuestionAttempt)
                .where(QuestionAttempt.practice_session_id == practice_session.id)
                .order_by(QuestionAttempt.attempt_number)
            ).all()
        )

        if len(attempts) < self.policy.min_questions_attempted:
            raise ApplicationError(
                400,
                "INCOMPLETE_REPAIR_SESSION",
                f"Cannot evaluate: only {len(attempts)} of {self.policy.min_questions_attempted} questions completed.",
            )

        # 1. Check minimum performance threshold
        scores = [a.score for a in attempts if a.score is not None]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        # 2. Check final recheck correct
        final_attempt = attempts[-1]
        final_recheck_correct = final_attempt.is_correct is True

        # 3. Deterministic success criteria
        is_successful = (
            avg_score >= self.policy.min_performance_threshold
            and final_recheck_correct
            and len(attempts) >= self.policy.min_questions_attempted
        )

        misconception_resolved = False
        if is_successful:
            practice_session.status = PracticeSessionStatus.COMPLETED
            practice_session.completed_at = datetime.now(timezone.utc)

            # If targeting a persistent misconception, mark it as RESOLVED
            if misconception_definition_id is not None:
                try:
                    self.misconception_service.resolve(
                        student_id=student.id,
                        misconception_definition_id=misconception_definition_id,
                        commit=False,
                    )
                    misconception_resolved = True
                except Exception as exc:
                    logger.warning("Could not auto-resolve misconception on repair success: %s", exc)

            self.session.commit()
            resolution_status = "RESOLVED"
            summary_message = (
                f"Repair Session hoàn thành xuất sắc! Điểm trung bình {avg_score:.2f} "
                f"(>= {self.policy.min_performance_threshold:.2f}) và câu Final Recheck chính xác."
            )
        else:
            resolution_status = "NEEDS_FURTHER_PRACTICE"
            reasons = []
            if avg_score < self.policy.min_performance_threshold:
                reasons.append(f"điểm trung bình {avg_score:.2f} chưa đạt ngưỡng {self.policy.min_performance_threshold:.2f}")
            if not final_recheck_correct:
                reasons.append("câu Final Recheck chưa chính xác")
            summary_message = f"Repair Session chưa đạt tiêu chuẩn: {', '.join(reasons)}."

        return RepairEvaluationResult(
            session_id=practice_session.id,
            is_successful=is_successful,
            status=practice_session.status,
            average_score=avg_score,
            final_recheck_correct=final_recheck_correct,
            evidence_count=len(attempts),
            resolution_status=resolution_status,
            misconception_resolved=misconception_resolved,
            summary_message=summary_message,
        )

    # --------------------------------------------------------------------------
    # Private Helpers: Question Selection & Assembly
    # --------------------------------------------------------------------------

    def _select_questions(
        self,
        target_type: RepairTargetType,
        target_id: UUID,
        subject_id: UUID,
    ) -> list[Question]:
        """Select questions strictly from APPROVED Question Bank with difficulty progression."""
        if target_type == RepairTargetType.PREREQUISITE_CONCEPT:
            # Query questions mapped to this Concept, ordered by difficulty ascending (foundation first)
            query = (
                select(Question)
                .join(QuestionConcept, QuestionConcept.question_id == Question.id)
                .where(
                    QuestionConcept.concept_id == target_id,
                    Question.status == QuestionStatus.APPROVED,
                )
                .order_by(Question.difficulty.asc())
                .limit(4)
            )
        else:
            # Target is ProblemType: query questions mapped to this ProblemType
            query = (
                select(Question)
                .join(QuestionProblemType, QuestionProblemType.question_id == Question.id)
                .where(
                    QuestionProblemType.problem_type_id == target_id,
                    Question.status == QuestionStatus.APPROVED,
                )
                .order_by(Question.difficulty.asc())
                .limit(4)
            )

        questions = list(self.session.scalars(query).all())

        if not questions:
            # Fallback for subjects with questions mapped to subject
            fallback_query = (
                select(Question)
                .where(
                    Question.subject_id == subject_id,
                    Question.status == QuestionStatus.APPROVED,
                )
                .order_by(Question.difficulty.asc())
                .limit(4)
            )
            questions = list(self.session.scalars(fallback_query).all())

        # Guarantee at least up to 4 items by repeating if pool is small
        if questions and len(questions) < 4:
            while len(questions) < 4:
                questions.append(questions[-1])

        return questions

    def _build_session_read(
        self,
        practice_session: PracticeSession,
        target_type: RepairTargetType,
        target_id: UUID,
        target_name: str,
        target_code: str,
        trigger: RepairTriggerType | None,
        questions: list[Question],
        attempts: list[QuestionAttempt],
    ) -> RepairSessionRead:
        """Assemble the complete 5-step RepairSessionRead model."""
        attempts_by_qid = {a.question_id: a for a in attempts}

        # Step 1: Brief Review
        review_text = (
            f"Tóm tắt kiến thức trọng tâm cho [{target_name} ({target_code})]:\n"
            f"- Đọc kỹ yêu cầu đề bài và xác định đúng các giả thiết nền tảng.\n"
            f"- Tránh các sai lầm phổ biến: không nhầm lẫn điều kiện biên hoặc dấu đạo hàm.\n"
            f"- Quy tắc cốt lõi: thực hiện kiểm tra từng bước theo đúng định lý và công thức."
        )

        steps: list[RepairStepRead] = [
            RepairStepRead(
                step_number=1,
                role=RepairStepRole.BRIEF_REVIEW,
                instruction="Đọc kỹ tóm tắt phương pháp và các lưu ý tránh sai lầm trước khi làm bài.",
                review_content=review_text,
            )
        ]

        roles = [
            (2, RepairStepRole.EASY_VERIFICATION, "Kiểm tra nhanh nhận biết kiến thức cơ bản.", False),
            (3, RepairStepRole.GUIDED_PRACTICE, "Luyện tập có hướng dẫn (hỗ trợ xem gợi ý).", True),
            (4, RepairStepRole.MEDIUM_PRACTICE, "Luyện tập chuẩn mức độ vận dụng.", False),
            (5, RepairStepRole.FINAL_RECHECK, "Kiểm tra chốt phiên để xác nhận khắc phục lỗ hổng.", False),
        ]

        for step_no, role, instruction, hints_avail in roles:
            q_idx = step_no - 2
            q = questions[q_idx] if q_idx < len(questions) else None
            if q is not None:
                attempt = attempts_by_qid.get(q.id)
                opts = [
                    RepairStepQuestionOptionRead(
                        id=opt.id,
                        label=opt.label,
                        content=opt.content,
                        order_index=opt.order_index,
                    )
                    for opt in q.options
                ]
                steps.append(
                    RepairStepRead(
                        step_number=step_no,
                        role=role,
                        instruction=instruction,
                        question_id=q.id,
                        question_content=q.content,
                        question_type=q.question_type,
                        difficulty=q.difficulty,
                        options=opts,
                        hints_available=hints_avail,
                        is_attempted=attempt is not None,
                        is_correct=attempt.is_correct if attempt else None,
                        score=attempt.score if attempt else None,
                    )
                )

        return RepairSessionRead(
            id=practice_session.id,
            student_id=practice_session.student_id,
            subject_id=practice_session.subject_id,
            trigger=trigger or RepairTriggerType.LOW_PROBLEM_TYPE_MASTERY,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            target_code=target_code,
            status=practice_session.status,
            started_at=practice_session.started_at,
            completed_at=practice_session.completed_at,
            steps=steps,
            is_completed=practice_session.status == PracticeSessionStatus.COMPLETED,
        )

    def _resolve_session_target(
        self, practice_session: PracticeSession
    ) -> tuple[RepairTargetType, UUID, str, str]:
        """Determine target type, id, name, and code from session links."""
        pt_link = self.session.scalar(
            select(PracticeSessionProblemType).where(
                PracticeSessionProblemType.practice_session_id == practice_session.id
            )
        )
        if pt_link is not None:
            pt = self.session.get(ProblemType, pt_link.problem_type_id)
            return (
                RepairTargetType.PROBLEM_TYPE,
                pt_link.problem_type_id,
                pt.name if pt else "Problem Type",
                pt.code if pt else "",
            )

        c_link = self.session.scalar(
            select(PracticeSessionConcept).where(
                PracticeSessionConcept.practice_session_id == practice_session.id
            )
        )
        if c_link is not None:
            c = self.session.get(Concept, c_link.concept_id)
            return (
                RepairTargetType.PREREQUISITE_CONCEPT,
                c_link.concept_id,
                c.name if c else "Concept",
                c.code if c else "",
            )

        raise ApplicationError(422, "ORPHAN_REPAIR_SESSION", "No target associated with this repair session.")

    def _get_session_questions(
        self,
        practice_session: PracticeSession,
        target_type: RepairTargetType,
        target_id: UUID,
    ) -> list[Question]:
        """Fetch assigned questions for this session."""
        return self._select_questions(
            target_type=target_type,
            target_id=target_id,
            subject_id=practice_session.subject_id,
        )

    def _student_for_user(self, user_id: UUID) -> StudentProfile:
        student = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if student is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile not found.")
        return student

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
            occurred_at=attempt.created_at or datetime.now(timezone.utc),
        )

