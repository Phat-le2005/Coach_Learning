from __future__ import annotations

import asyncio
from collections import defaultdict
import concurrent.futures
from datetime import datetime, timezone
import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.ai.dependencies import get_ai_gateway_singleton
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.types import AIMessage, AIRole, AITaskType
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept
from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.exams.access_policy import assert_exam_attempt_access
from app.exams.ai_schemas import (
    ExamAIExplanationRead,
    ExamAIInputContext,
    ExamAIStructuredOutput,
)
from app.exams.analytics_service import ExamAnalyticsService
from app.exams.models import Exam, ExamAttempt, ExamAttemptStatus, ExamQuestion, ExamResponse
from app.exams.schemas import ExamAnalyticsRead
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import (
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.questions.models import Question
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import Role, User

logger = logging.getLogger(__name__)

CARELESS_PATTERN = re.compile(r"\b(bất cẩn|ẩu tả|ẩu|careless|thiếu tập trung)\b", re.IGNORECASE)


class ExamAIExplanationService:
    """Pedagogical AI Explanation and Diagnostic Engine for standardized exam results.

    Strict Architectural Guarantees:
    - 6 Deterministic Data Sources: ExamAnalytics, StudentProblemTypeMastery,
      StudentConceptMastery, Known Misconceptions, Time Behavior, Curriculum Structure.
    - Zero Score Mutation: Exam score, points and accuracy are immutable.
    - Strict Careless Guardrail: NEVER accuses student of carelessness/negligence
      unless strong empirical evidence exists (difficulty < 0.35, prior mastery >= 0.70,
      response time < 15s).
    - No Invented Curriculum Nodes: Output is constrained strictly to the provided syllabus context.
    - Role-based Authorization: Students can view their own attempts; authorized teachers
      of the student's active classroom (or Admins) can view; unauthorized access yields 403.
    - High-Reliability Fallback: Returns structured deterministic analysis if AI provider fails.
    """

    def __init__(
        self,
        session: Session,
        gateway: Any | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.session = session
        self.gateway = gateway or get_ai_gateway_singleton(get_settings())
        self.prompt_registry = prompt_registry or default_prompt_registry
        self.analytics_service = ExamAnalyticsService(session)

    # --------------------------------------------------------------------------
    # 1. Multi-Role Authorization & Security
    # --------------------------------------------------------------------------

    def require_attempt_access(self, user_id: UUID, attempt_id: UUID) -> tuple[User, ExamAttempt]:
        """Verify whether requesting user is authorized to view this exam attempt.

        Rules:
        - Admin: Always allowed.
        - Student: Allowed ONLY if student owns the attempt.
        - Teacher: Allowed ONLY if teacher is assigned to or owns a classroom
          in which the student is actively enrolled.
        - All others: 403 FORBIDDEN.
        """
        user = self.session.get(User, user_id)
        if user is None:
            raise ApplicationError(404, "USER_NOT_FOUND", "User was not found.")

        attempt = self.session.scalar(
            select(ExamAttempt)
            .options(
                selectinload(ExamAttempt.exam),
                selectinload(ExamAttempt.responses),
            )
            .where(ExamAttempt.id == attempt_id)
        )
        if attempt is None:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Exam attempt not found.")

        assert_exam_attempt_access(self.session, user, attempt)
        return user, attempt

    # --------------------------------------------------------------------------
    # 2. Context Assembly (6 Deterministic Data Sources)
    # --------------------------------------------------------------------------

    def build_explanation_context(self, attempt_id: UUID) -> ExamAIInputContext:
        """Assemble comprehensive diagnostic context for the attempt."""
        attempt = self.session.scalar(
            select(ExamAttempt)
            .options(
                selectinload(ExamAttempt.exam).selectinload(Exam.questions),
                selectinload(ExamAttempt.responses),
            )
            .where(ExamAttempt.id == attempt_id)
        )
        if attempt is None:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Exam attempt not found.")

        # 1. ExamAnalytics
        analytics: ExamAnalyticsRead = self.analytics_service.generate_analytics(attempt_id)

        # Student info
        student = self.session.get(StudentProfile, attempt.student_id)
        user = self.session.get(User, student.user_id) if student else None
        student_name = (
            user.full_name or user.username or "Học sinh"
            if user
            else "Học sinh"
        )

        # Question IDs in exam
        question_ids = [eq.question_id for eq in attempt.exam.questions]
        questions = list(
            self.session.scalars(
                select(Question)
                .options(
                    selectinload(Question.options),
                    selectinload(Question.problem_type_links),
                    selectinload(Question.concept_links),
                )
                .where(Question.id.in_(question_ids))
            ).all()
        )
        questions_by_id = {q.id: q for q in questions}

        # Curriculum IDs
        pt_ids = {
            link.problem_type_id for q in questions for link in q.problem_type_links
        }
        concept_ids = {
            link.concept_id for q in questions for link in q.concept_links
        }

        # 2. Prior ProblemType Mastery
        pt_mastery_rows = list(
            self.session.scalars(
                select(StudentProblemTypeMastery).where(
                    StudentProblemTypeMastery.student_id == attempt.student_id,
                    StudentProblemTypeMastery.problem_type_id.in_(list(pt_ids)),
                )
            ).all()
        ) if pt_ids else []
        prior_pt_map = {row.problem_type_id: row for row in pt_mastery_rows}

        # 3. Prior Concept Mastery
        concept_mastery_rows = list(
            self.session.scalars(
                select(StudentConceptMastery).where(
                    StudentConceptMastery.student_id == attempt.student_id,
                    StudentConceptMastery.concept_id.in_(list(concept_ids)),
                )
            ).all()
        ) if concept_ids else []
        prior_concept_map = {row.concept_id: row for row in concept_mastery_rows}

        # 4. Known Misconceptions
        known_misconceptions_raw = list(
            self.session.execute(
                select(StudentMisconception, MisconceptionDefinition)
                .join(
                    MisconceptionDefinition,
                    StudentMisconception.misconception_definition_id == MisconceptionDefinition.id,
                )
                .where(
                    StudentMisconception.student_id == attempt.student_id,
                    StudentMisconception.status.in_([
                        StudentMisconceptionStatus.CONFIRMED,
                        StudentMisconceptionStatus.SUSPECTED,
                    ]),
                )
            ).all()
        )

        known_misconceptions_list: list[dict[str, Any]] = [
            {
                "code": m_def.code,
                "name": m_def.name,
                "category": str(m_def.category),
                "status": str(sm.status),
                "confidence": sm.confidence,
                "occurrence_count": sm.occurrence_count,
            }
            for sm, m_def in known_misconceptions_raw
        ]

        # 5. Curriculum Node Names
        valid_nodes: set[str] = set()
        problem_types = list(
            self.session.scalars(
                select(ProblemType).where(ProblemType.id.in_(list(pt_ids)))
            ).all()
        ) if pt_ids else []
        pts_by_id = {pt.id: pt for pt in problem_types}
        for pt in problem_types:
            valid_nodes.add(pt.name)

        topic_ids = {pt.topic_id for pt in problem_types}
        topics = list(
            self.session.scalars(
                select(Topic).where(Topic.id.in_(list(topic_ids)))
            ).all()
        ) if topic_ids else []
        for t in topics:
            valid_nodes.add(t.name)

        chapter_ids = {t.chapter_id for t in topics}
        chapters = list(
            self.session.scalars(
                select(Chapter).where(Chapter.id.in_(list(chapter_ids)))
            ).all()
        ) if chapter_ids else []
        for ch in chapters:
            valid_nodes.add(ch.name)

        concepts = list(
            self.session.scalars(
                select(Concept).where(Concept.id.in_(list(concept_ids)))
            ).all()
        ) if concept_ids else []
        concepts_by_id = {c.id: c for c in concepts}
        for c in concepts:
            valid_nodes.add(c.name)

        # 6. Response Mapping & Careless Evidence Check
        responses_by_qid = {r.question_id: r for r in attempt.responses}
        incorrect_questions_detail: list[dict[str, Any]] = []
        has_strong_careless_evidence = False

        for qid, q in questions_by_id.items():
            resp = responses_by_qid.get(qid)
            is_c = bool(resp and resp.is_correct)
            if not is_c:
                q_pts = [pts_by_id[l.problem_type_id].name for l in q.problem_type_links if l.problem_type_id in pts_by_id]
                q_concepts = [concepts_by_id[l.concept_id].name for l in q.concept_links if l.concept_id in concepts_by_id]
                ans_time = resp.response_time_seconds if resp else None
                student_ans = resp.student_answer if resp else None

                incorrect_questions_detail.append(
                    {
                        "question_id": str(qid),
                        "difficulty": q.difficulty,
                        "question_type": str(q.question_type),
                        "problem_types": q_pts,
                        "concepts": q_concepts,
                        "student_answer": student_ans,
                        "correct_answer": q.correct_answer,
                        "response_time_seconds": ans_time,
                    }
                )

                # Careless Rule: difficulty < 0.35, response_time < 15.0s, and prior_mastery >= 0.70
                if ans_time is not None and ans_time < 15.0 and q.difficulty < 0.35:
                    for l in q.problem_type_links:
                        pm = prior_pt_map.get(l.problem_type_id)
                        if pm and pm.mastery_score >= 0.70:
                            has_strong_careless_evidence = True
                            break

        prior_pt_list: list[dict[str, Any]] = [
            {
                "problem_type_name": pts_by_id[pm.problem_type_id].name if pm.problem_type_id in pts_by_id else str(pm.problem_type_id),
                "mastery_score": pm.mastery_score,
                "confidence": pm.confidence,
                "attempt_count": pm.attempt_count,
            }
            for pm in pt_mastery_rows
        ]

        prior_c_list: list[dict[str, Any]] = [
            {
                "concept_name": concepts_by_id[cm.concept_id].name if cm.concept_id in concepts_by_id else str(cm.concept_id),
                "mastery_score": cm.mastery_score,
                "confidence": cm.confidence,
                "attempt_count": cm.attempt_count,
            }
            for cm in concept_mastery_rows
        ]

        return ExamAIInputContext(
            attempt_id=attempt.id,
            exam_id=attempt.exam_id,
            student_id=attempt.student_id,
            student_name=student_name,
            exam_title=attempt.exam.title,
            exam_type=str(attempt.exam.exam_type),
            duration_minutes=attempt.exam.duration_minutes,
            actual_duration_seconds=attempt.duration_seconds or 0,
            score=analytics.score,
            score_10=analytics.score_10,
            total_points=analytics.total_points,
            accuracy=analytics.accuracy,
            total_questions=analytics.total_questions,
            correct_count=analytics.correct_count,
            incorrect_count=analytics.incorrect_count,
            unanswered_count=analytics.unanswered_count,
            chapter_performance=[cp.model_dump() for cp in analytics.chapter_performance],
            topic_performance=[tp.model_dump() for tp in analytics.topic_performance],
            problem_type_performance=[pp.model_dump() for pp in analytics.problem_type_performance],
            concept_evidence=[ce.model_dump() for ce in analytics.concept_evidence],
            prior_problem_type_mastery=prior_pt_list,
            prior_concept_mastery=prior_c_list,
            known_misconceptions=known_misconceptions_list,
            time_behavior=analytics.time_per_question.model_dump() | analytics.accuracy_over_time.model_dump(),
            question_order_behavior=analytics.question_order_behavior.model_dump(),
            incorrect_questions_detail=incorrect_questions_detail,
            has_strong_careless_evidence=has_strong_careless_evidence,
            valid_curriculum_nodes=valid_nodes,
        )

    # --------------------------------------------------------------------------
    # 3. Prompt Formatting
    # --------------------------------------------------------------------------

    def _format_prompt_variables(self, ctx: ExamAIInputContext) -> dict[str, str]:
        """Format the input context into string variables matching the v1 prompt template."""
        # Chapter & Topic
        chap_lines = [
            f"- Chương [{cp['chapter_name']}]: đúng {cp['correct_count']}/{cp['total_questions']} câu "
            f"({int(cp['accuracy'] * 100)}%), đạt {cp['score_earned']:.1f}/{cp['max_score']:.1f} điểm"
            for cp in ctx.chapter_performance
        ]
        topic_lines = [
            f"- Chủ đề [{tp['topic_name']}] (Chương {tp['chapter_name']}): đúng {tp['correct_count']}/{tp['total_questions']} "
            f"({int(tp['accuracy'] * 100)}%)"
            for tp in ctx.topic_performance
        ]
        chap_top_str = "\n".join(chap_lines + topic_lines) if (chap_lines or topic_lines) else "Không có phân bổ chi tiết chương chủ đề."

        # ProblemType
        pt_lines = [
            f"- Dạng [{pp['problem_type_name']}]: đúng {pp['correct_count']}/{pp['total_questions']} câu "
            f"({int(pp['accuracy'] * 100)}%)"
            for pp in ctx.problem_type_performance
        ]
        pt_str = "\n".join(pt_lines) if pt_lines else "Không có dữ liệu dạng bài."

        # Concept Evidence
        c_lines = []
        for ce in ctx.concept_evidence:
            sig = f" [CẢNH BÁO: {ce['diagnostic_signal']}]" if ce.get("diagnostic_signal") else ""
            c_lines.append(
                f"- Khái niệm [{ce['concept_name']}]: đúng {ce['correct_count']}/{ce['questions_tested']} "
                f"({int(ce['accuracy'] * 100)}%){sig}"
            )
        c_str = "\n".join(c_lines) if c_lines else "Không ghi nhận tín hiệu khái niệm đặc biệt."

        # Prior ProblemType Mastery
        prior_pt_lines = [
            f"- Dạng [{pm['problem_type_name']}]: mức thành thạo trước đó {pm['mastery_score']:.2f} "
            f"(độ tin cậy {pm['confidence']:.2f}, {pm['attempt_count']} lượt làm)"
            for pm in ctx.prior_problem_type_mastery
        ]
        prior_pt_str = "\n".join(prior_pt_lines) if prior_pt_lines else "Chưa có lịch sử làm các dạng bài này trước bài thi."

        # Prior Concept Mastery
        prior_c_lines = [
            f"- Khái niệm [{cm['concept_name']}]: mức thành thạo trước đó {cm['mastery_score']:.2f} "
            f"(độ tin cậy {cm['confidence']:.2f})"
            for cm in ctx.prior_concept_mastery
        ]
        prior_c_str = "\n".join(prior_c_lines) if prior_c_lines else "Chưa có lịch sử mastery khái niệm trước bài thi."

        # Known Misconceptions
        misc_lines = [
            f"- [{m['category']}] {m['name']} (Mã: {m['code']}, Trạng thái: {m['status']}, Xuất hiện: {m['occurrence_count']} lần)"
            for m in ctx.known_misconceptions
        ]
        misc_str = "\n".join(misc_lines) if misc_lines else "Không ghi nhận ngộ nhận nào trước đó."

        # Time Behavior
        tb = ctx.time_behavior
        time_lines = [
            f"- Thời gian trung bình: {tb.get('average_seconds_per_question', 0.0)} giây/câu (Tổng thời gian: {tb.get('total_time_seconds', 0)}s).",
            f"- Độ chính xác nửa đầu bài thi: {int(tb.get('first_half_accuracy', 0.0) * 100)}%.",
            f"- Độ chính xác nửa sau bài thi: {int(tb.get('second_half_accuracy', 0.0) * 100)}%.",
            f"- Tín hiệu áp lực thời gian / giảm sút tập trung: {'CÓ PHÁT HIỆN' if tb.get('time_pressure_detected') else 'KHÔNG PHÁT HIỆN'}.",
            f"- Nhận định chuỗi thời gian: {tb.get('summary', '')}",
        ]
        time_str = "\n".join(time_lines)

        # Question Order Behavior
        qob = ctx.question_order_behavior
        order_str = (
            f"- Làm tuần tự: {'Có' if qob.get('is_sequential') else 'Không (có nhảy cóc)'}, "
            f"số lượt nhảy câu: {qob.get('skipped_count', 0)}. {qob.get('summary', '')}"
        )

        # Incorrect Questions Detail
        in_lines = []
        for iq in ctx.incorrect_questions_detail[:8]:
            pts = ", ".join(iq["problem_types"]) or "Chưa phân loại"
            t_taken = f"{iq['response_time_seconds']}s" if iq["response_time_seconds"] is not None else "Không rõ"
            in_lines.append(
                f"- Câu hỏi dạng [{pts}]: Độ khó {iq['difficulty']:.2f}, Thời gian làm {t_taken}. "
                f"Học sinh chọn: '{iq['student_answer'] or 'Bỏ trống'}', Đáp án đúng: '{iq['correct_answer']}'."
            )
        incorrect_str = "\n".join(in_lines) if in_lines else "Không có câu hỏi nào làm sai."

        # Careless Evidence Note
        if ctx.has_strong_careless_evidence:
            careless_note = (
                "XÁC NHẬN CÓ BẰNG CHỨNG MẠNH VỀ SỰ BẤT CẨN: Học sinh làm sai câu có độ khó thấp (<0.35) "
                "trong thời gian rất ngắn (<15s) dù đã từng đạt độ thành thạo cao (>=0.70). Có thể nhắc nhở học sinh cẩn thận hơn."
            )
        else:
            careless_note = (
                "KHÔNG CÓ BẰNG CHỨNG MẠNH VỀ SỰ BẤT CẨN: Tuyệt đối KHÔNG gán nhãn học sinh là bất cẩn, ẩu hay thiếu tập trung. "
                "Hãy giải thích nguyên nhân do kiến thức chưa vững hoặc cần hoàn thiện phương pháp giải."
            )

        return {
            "student_name": ctx.student_name,
            "exam_title": ctx.exam_title,
            "exam_type": ctx.exam_type,
            "score": f"{ctx.score_10:.1f}/10.0 (Điểm thô: {ctx.score:.1f}/{ctx.total_points:.1f})",
            "accuracy": f"{int(ctx.accuracy * 100)}%",
            "total_questions": str(ctx.total_questions),
            "correct_count": str(ctx.correct_count),
            "incorrect_count": str(ctx.incorrect_count),
            "unanswered_count": str(ctx.unanswered_count),
            "chapter_topic_summary": chap_top_str,
            "problem_type_performance_summary": pt_str,
            "concept_evidence_summary": c_str,
            "prior_problem_type_mastery_summary": prior_pt_str,
            "prior_concept_mastery_summary": prior_c_str,
            "known_misconceptions_summary": misc_str,
            "time_behavior_summary": time_str,
            "question_order_behavior_summary": order_str,
            "incorrect_questions_detail": incorrect_str,
            "careless_evidence_note": careless_note,
        }

    # --------------------------------------------------------------------------
    # 4. Generation Execution (Async & Sync with Guardrail Enforcement)
    # --------------------------------------------------------------------------

    async def generate_explanation_async(
        self,
        attempt_id: UUID,
        user_id: UUID,
    ) -> ExamAIExplanationRead:
        """Generate AI explanation asynchronously with strict post-processing guardrails."""
        # 1. Authorization check
        self.require_attempt_access(user_id, attempt_id)

        # 2. Context assembly
        ctx = self.build_explanation_context(attempt_id)

        try:
            prompt_vars = self._format_prompt_variables(ctx)
            rendered_prompt = self.prompt_registry.get_prompt("exam_explanation", "v1", prompt_vars)
            messages = [AIMessage(role=AIRole.USER, content=rendered_prompt)]

            response = await self.gateway.generate_structured(
                task_type=AITaskType.EXAM_ANALYSIS,
                messages=messages,
                schema=ExamAIStructuredOutput,
                temperature=0.3,
                prompt_name="exam_explanation",
                prompt_version="v1",
                user_id=user_id,
            )

            ai_out: ExamAIStructuredOutput = response.data

            # ------------------------------------------------------------------
            # Guardrails Post-processing:
            # ------------------------------------------------------------------
            # Guardrail 1: Strictly enforce Careless rule
            # If no strong evidence exists, sanitize careless accusations
            weak_pts = ai_out.weak_problem_types
            recurring_errs = ai_out.recurring_errors
            time_issue = ai_out.possible_time_management_issue
            summary = ai_out.student_friendly_summary

            if not ctx.has_strong_careless_evidence:
                time_issue = CARELESS_PATTERN.sub("cần rà soát kỹ lưỡng hơn", time_issue)
                summary = CARELESS_PATTERN.sub("cần dành thời gian kiểm tra lại các bước làm", summary)
                recurring_errs = [CARELESS_PATTERN.sub("lỗi thiếu bước kiểm tra", err) for err in recurring_errs]

            return ExamAIExplanationRead(
                attempt_id=ctx.attempt_id,
                exam_id=ctx.exam_id,
                student_id=ctx.student_id,
                exam_title=ctx.exam_title,
                score=ctx.score,
                score_10=ctx.score_10,
                accuracy=ctx.accuracy,
                strengths=ai_out.strengths or [f"Hoàn thành tốt các câu hỏi trong đề {ctx.exam_title}."],
                weak_problem_types=weak_pts,
                possible_prerequisite_weaknesses=ai_out.possible_prerequisite_weaknesses,
                recurring_errors=recurring_errs,
                possible_time_management_issue=time_issue,
                review_priorities=ai_out.review_priorities or ["Ôn tập các dạng bài có tỷ lệ chính xác dưới 60%."],
                exam_strategy_suggestions=ai_out.exam_strategy_suggestions or [
                    "Phân bổ thời gian đồng đều và kiểm tra lại câu hỏi trước khi nộp."
                ],
                student_friendly_summary=summary,
                has_strong_careless_evidence=ctx.has_strong_careless_evidence,
                is_fallback=False,
                generated_at=datetime.now(timezone.utc),
            )

        except Exception as exc:
            logger.warning(
                "ExamAIExplanationService: AI generation failed (%s). Falling back to deterministic explanation.",
                exc,
            )
            return self._generate_deterministic_fallback(ctx)

    def generate_explanation(
        self,
        attempt_id: UUID,
        user_id: UUID,
    ) -> ExamAIExplanationRead:
        """Synchronous wrapper for generate_explanation_async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self.generate_explanation_async(attempt_id, user_id),
                )
                return future.result()
        else:
            return asyncio.run(self.generate_explanation_async(attempt_id, user_id))

    # --------------------------------------------------------------------------
    # 5. Deterministic Fallback (Reliability Guarantee)
    # --------------------------------------------------------------------------

    def _generate_deterministic_fallback(self, ctx: ExamAIInputContext) -> ExamAIExplanationRead:
        """Generate high-quality deterministic explanation when AI is unavailable."""
        strengths: list[str] = []
        weak_pts: list[str] = []

        for pp in ctx.problem_type_performance:
            if pp["accuracy"] >= 0.70:
                strengths.append(f"Dạng bài [{pp['problem_type_name']}]: độ chính xác đạt {int(pp['accuracy'] * 100)}%.")
            elif pp["accuracy"] < 0.60:
                weak_pts.append(f"Dạng bài [{pp['problem_type_name']}]: chỉ đạt {int(pp['accuracy'] * 100)}% ({pp['correct_count']}/{pp['total_questions']} câu).")

        if not strengths:
            strengths.append(f"Đã nỗ lực hoàn thành {ctx.total_questions - ctx.unanswered_count}/{ctx.total_questions} câu trong đề thi.")

        if not weak_pts:
            weak_pts.append("Không có dạng bài yếu rõ rệt. Tiếp tục duy trì phong độ hiện tại.")

        # Prerequisite gaps
        prereq_gaps = [
            f"Khái niệm [{ce['concept_name']}]: ghi nhận lỗ hổng kiến thức tiền đề ảnh hưởng đến độ chính xác."
            for ce in ctx.concept_evidence
            if ce.get("diagnostic_signal") == "PREREQUISITE_GAP"
        ]
        if not prereq_gaps:
            prereq_gaps.append("Không phát hiện lỗ hổng tiền đề nghiêm trọng trong bài thi này.")

        # Recurring errors
        recurring = [
            f"Ngộ nhận [{m['name']}]: xuất hiện {m['occurrence_count']} lần trước đó, cần lưu ý khi làm bài."
            for m in ctx.known_misconceptions[:2]
        ]
        if not recurring:
            recurring.append("Chưa ghi nhận ngộ nhận lặp lại đáng kể.")

        # Time management
        tb = ctx.time_behavior
        if tb.get("time_pressure_detected"):
            time_issue = "Độ chính xác giảm ở nửa sau bài thi, cho thấy dấu hiệu áp lực thời gian hoặc giảm sút tập trung."
        else:
            time_issue = f"Tốc độ làm bài tương đối ổn định với thời gian trung bình {tb.get('average_seconds_per_question', 0.0)} giây/câu."

        # Review priorities
        priorities = [
            f"Ưu tiên 1: Củng cố {weak_pts[0]}" if weak_pts else "Ưu tiên 1: Luyện tập nâng cao.",
            f"Ưu tiên 2: Rà soát {prereq_gaps[0]}" if prereq_gaps and "lỗ hổng" in prereq_gaps[0] else "Ưu tiên 2: Rèn luyện kỹ năng phân bổ thời gian.",
            "Ưu tiên 3: Luyện thêm 1 đề thi thử trong điều kiện bấm giờ thực tế.",
        ]

        strategies = [
            "Đọc lướt toàn bộ đề và ưu tiên giải quyết các câu quen thuộc thuộc sở trường trước.",
            "Nếu gặp câu hỏi mất hơn 2 phút mà chưa tìm ra hướng giải, hãy tạm đánh dấu và chuyển sang câu kế tiếp.",
            "Dành ít nhất 3-5 phút cuối giờ để kiểm tra lại các câu đã làm và tô đầy đủ đáp án.",
        ]

        summary = (
            f"Con đã hoàn thành bài thi '{ctx.exam_title}' với điểm số quy đổi {ctx.score_10:.1f}/10.0 ({int(ctx.accuracy * 100)}% độ chính xác). "
            f"Đây là kết quả phản ánh rõ những điểm con đã làm tốt và các dạng bài cần thêm chút thời gian luyện tập. "
            f"Hãy tập trung ôn lại theo các ưu tiên đã gợi ý để tự tin bứt phá ở bài thi tiếp theo nhé!"
        )

        return ExamAIExplanationRead(
            attempt_id=ctx.attempt_id,
            exam_id=ctx.exam_id,
            student_id=ctx.student_id,
            exam_title=ctx.exam_title,
            score=ctx.score,
            score_10=ctx.score_10,
            accuracy=ctx.accuracy,
            strengths=strengths,
            weak_problem_types=weak_pts,
            possible_prerequisite_weaknesses=prereq_gaps,
            recurring_errors=recurring,
            possible_time_management_issue=time_issue,
            review_priorities=priorities,
            exam_strategy_suggestions=strategies,
            student_friendly_summary=summary,
            has_strong_careless_evidence=ctx.has_strong_careless_evidence,
            is_fallback=True,
            generated_at=datetime.now(timezone.utc),
        )
