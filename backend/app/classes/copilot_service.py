from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import datetime, timezone
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway_singleton
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.types import AIMessage, AIRole, AITaskType
from app.classes.analytics_service import ClassAnalyticsService
from app.classes.copilot_schemas import (
    TeacherCopilotAIOutput,
    TeacherCopilotContextInput,
    TeacherCopilotContextSummary,
    TeacherCopilotRead,
    TeacherCopilotRequest,
    TeacherCopilotStudentAttention,
)
from app.classes.models import Classroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.config import get_settings
from app.curriculum.models import ProblemType
from app.mastery.models import StudentConceptMastery
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.subjects.models import Subject
from app.users.models import User

logger = logging.getLogger(__name__)


class TeacherCopilotService:
    """Pedagogical assistant service for teachers to query and understand classroom analytics.

    Strict Architectural & Pedagogical Guarantees:
    - Strictly grounded in supplied data: AI never invents facts or data outside supplied context.
    - Clear distinction between factual OBSERVATIONS and actionable RECOMMENDATIONS.
    - Read-only on TeachingPlan: Never modifies or overwrites TeachingPlan database records.
    - No automatic assignments: Never creates or assigns StudyTasks automatically.
    - No psychological diagnoses: Strictly focuses on academic mastery and behavioral metrics.
    - No invented mastery: Never fabricates scores or competencies.
    - Connects ProblemType with underlying prerequisite Concepts.
    - Resilient Fallback: If AI is unavailable or fails, returns high-quality deterministic response.
    """

    def __init__(
        self,
        session: Session,
        gateway: Any | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.session = session
        self.analytics_service = ClassAnalyticsService(session)
        self.gateway = gateway or get_ai_gateway_singleton(get_settings())
        self.prompt_registry = prompt_registry or default_prompt_registry

    # --------------------------------------------------------------------------
    # 1. Context Builder
    # --------------------------------------------------------------------------

    def build_context(
        self,
        teacher_user_id: UUID,
        classroom_id: UUID,
        query: str,
        subject_id: UUID | None = None,
        include_synthetic: bool = False,
    ) -> TeacherCopilotContextInput:
        """Assemble complete classroom analytics and curriculum context for Copilot."""
        teacher, classroom = self.analytics_service.require_teacher_access(teacher_user_id, classroom_id)

        # 1. Teacher name
        teacher_user = self.session.get(User, teacher_user_id)
        teacher_name = (
            teacher_user.full_name or teacher_user.username or "Giáo viên"
            if teacher_user
            else "Giáo viên"
        )

        # 2. Enrolled students
        students_info = self.analytics_service.get_enrolled_students(classroom_id, include_synthetic)
        student_ids = [s.id for s, _ in students_info]
        student_name_to_id = {name: s.id for s, name in students_info}
        students_by_id = {s.id: name for s, name in students_info}

        # 3. Class Analytics Dashboard
        dashboard = self.analytics_service.get_classroom_dashboard(
            teacher_user_id, classroom_id, include_synthetic
        )

        # 4. Intervention Alerts
        alerts_data = self.analytics_service.get_classroom_alerts(
            teacher_user_id, classroom_id, include_synthetic
        )

        # 5. Subject & Curriculum Context
        subject = None
        if subject_id:
            subject = self.session.get(Subject, subject_id)
        if not subject and dashboard.subject_progress:
            subject = self.session.get(Subject, dashboard.subject_progress[0].subject_id)
        if not subject:
            subject = self.session.scalar(
                select(Subject).where(Subject.grade_level == classroom.grade_level).limit(1)
            )
        subject_name = subject.name if subject else "Toán học"
        curriculum_context = (
            f"Chương trình Khối {classroom.grade_level}, Môn {subject_name} ({classroom.academic_year})"
        )

        # 6. Teaching Plan & Curriculum
        tp_query = select(TeachingPlan).where(
            TeachingPlan.classroom_id == classroom.id,
            TeachingPlan.status == TeachingPlanStatus.ACTIVE,
        )
        if subject_id:
            tp_query = tp_query.where(TeachingPlan.subject_id == subject_id)
        active_tp = self.session.scalar(tp_query.order_by(TeachingPlan.created_at.desc()).limit(1))

        active_tp_name: str | None = None
        tp_summary_lines: list[str] = []
        if active_tp:
            active_tp_name = f"Kế hoạch môn {subject_name} ({active_tp.start_date})"
            tp_items = list(
                self.session.scalars(
                    select(TeachingPlanItem)
                    .where(TeachingPlanItem.teaching_plan_id == active_tp.id)
                    .order_by(TeachingPlanItem.priority.desc(), TeachingPlanItem.order_index.asc())
                ).all()
            )
            item_names: list[str] = []
            for item in tp_items[:4]:
                pt = self.session.get(ProblemType, item.problem_type_id)
                if pt:
                    item_names.append(f"{pt.name} (Độ ưu tiên: {item.priority})")
            if item_names:
                tp_summary_lines.append(
                    f"Kế hoạch giảng dạy đang kích hoạt: [{active_tp_name}] — Các dạng bài trọng tâm: {'; '.join(item_names)}."
                )
            else:
                tp_summary_lines.append(f"Kế hoạch giảng dạy: [{active_tp_name}] (Chưa có dạng bài cụ thể).")
        else:
            tp_summary_lines.append("Lớp học hiện chưa kích hoạt kế hoạch giảng dạy (Teaching Plan) cụ thể.")
        teaching_plan_summary = "\n".join(tp_summary_lines)

        # 7. Class Analytics Summary
        analytics_lines = [
            f"- Sĩ số lớp: {len(students_info)} học sinh",
            (
                f"- Hoạt động 7 ngày qua: {dashboard.recent_trends.total_attempts_past_7_days} lượt làm bài, "
                f"điểm TB: {dashboard.recent_trends.recent_average_score:.2f} "
                f"(Xu hướng: {dashboard.recent_trends.trend_direction})"
            ),
            (
                f"- Tỷ lệ hoàn thành nhiệm vụ tự học: {dashboard.study_completion.completion_rate}% "
                f"({dashboard.study_completion.completed_tasks_count}/{dashboard.study_completion.assigned_tasks_count} nhiệm vụ)"
            ),
        ]
        if dashboard.chapter_progress:
            chp_parts = [f"{c.chapter_name}: {c.average_mastery:.2f}" for c in dashboard.chapter_progress[:3]]
            analytics_lines.append(f"- Tiến độ chương: {'; '.join(chp_parts)}")
        class_analytics_summary = "\n".join(analytics_lines)

        # 8. ProblemType Summaries
        pt_lines: list[str] = []
        weak_problem_types_list: list[str] = []
        if dashboard.weak_problem_types:
            pt_lines.append("Dạng bài YẾU (Điểm thành thạo < 0.50):")
            for w in dashboard.weak_problem_types:
                weak_problem_types_list.append(w.name)
                pt_lines.append(f"  + [{w.name}] ({w.code}): Điểm TB {w.average_score:.2f} ({w.student_count} học sinh)")
        else:
            pt_lines.append("Không có dạng bài nào bị đánh giá yếu (< 0.50).")

        if dashboard.strong_problem_types:
            pt_lines.append("Dạng bài MẠNH (Điểm thành thạo >= 0.70):")
            for s in dashboard.strong_problem_types:
                pt_lines.append(f"  + [{s.name}] ({s.code}): Điểm TB {s.average_score:.2f} ({s.student_count} học sinh)")
        problem_type_summaries = "\n".join(pt_lines)

        # 9. Concept Prerequisite Signals
        prereq_weak_rows = list(
            self.session.execute(
                select(StudentConceptMastery, Concept.name, Concept.code)
                .join(Concept, Concept.id == StudentConceptMastery.concept_id)
                .join(ConceptRelation, ConceptRelation.source_concept_id == Concept.id)
                .where(
                    StudentConceptMastery.student_id.in_(student_ids),
                    StudentConceptMastery.mastery_score < 0.50,
                    ConceptRelation.relation_type == RelationType.PREREQUISITE,
                )
            ).all()
        )
        prereq_by_concept: dict[UUID, dict[str, Any]] = {}
        for cm, cname, ccode in prereq_weak_rows:
            sname = students_by_id.get(cm.student_id, "Học sinh")
            if cm.concept_id not in prereq_by_concept:
                downstream = list(
                    self.session.scalars(
                        select(Concept.name)
                        .join(ConceptRelation, ConceptRelation.target_concept_id == Concept.id)
                        .where(
                            ConceptRelation.source_concept_id == cm.concept_id,
                            ConceptRelation.relation_type == RelationType.PREREQUISITE,
                        )
                    ).all()
                )
                prereq_by_concept[cm.concept_id] = {
                    "id": cm.concept_id,
                    "name": cname,
                    "code": ccode,
                    "downstream": downstream,
                    "affected": [],
                }
            prereq_by_concept[cm.concept_id]["affected"].append(
                {"student_name": sname, "student_id": cm.student_id, "score": round(cm.mastery_score, 2)}
            )

        prereq_lines: list[str] = []
        prereq_gaps_list: list[dict[str, Any]] = []
        if prereq_by_concept:
            for p_info in prereq_by_concept.values():
                prereq_gaps_list.append(p_info)
                downstream_str = (
                    f" (Là tiền đề cho: {', '.join(p_info['downstream'])})"
                    if p_info["downstream"]
                    else ""
                )
                affected_sample = ", ".join(
                    f"{aff['student_name']} ({aff['score']:.2f})" for aff in p_info["affected"][:4]
                )
                prereq_lines.append(
                    f"- Khái niệm [{p_info['name']}]{downstream_str}: "
                    f"{len(p_info['affected'])} học sinh bị hổng kiến thức ({affected_sample})"
                )
        else:
            prereq_lines.append("Không phát hiện lỗ hổng kiến thức tiên quyết nào (< 0.50).")
        prerequisite_signals_summary = "\n".join(prereq_lines)

        # 10. Common Misconceptions
        misc_lines: list[str] = []
        misconceptions_list: list[dict[str, Any]] = []
        if dashboard.common_misconceptions:
            for m in dashboard.common_misconceptions:
                misconceptions_list.append(
                    {
                        "name": m.name,
                        "code": m.code,
                        "affected_count": m.affected_students_count,
                        "student_names": m.affected_student_names,
                    }
                )
                names_str = ", ".join(m.affected_student_names[:4])
                misc_lines.append(
                    f"- Bẫy sai lầm [{m.name}] ({m.code}): {m.affected_students_count} học sinh mắc ({names_str})"
                )
        else:
            misc_lines.append("Không ghi nhận bẫy sai lầm phổ biến nào.")
        misconceptions_summary = "\n".join(misc_lines)

        # 11. Intervention Alerts Summary
        alerts_lines: list[str] = []
        alerts_list: list[dict[str, Any]] = []
        if alerts_data.alerts:
            alerts_lines.append(
                f"Tổng số cảnh báo can thiệp: {alerts_data.total_alerts} "
                f"(Nghiêm trọng: {alerts_data.critical_count}, Cao: {alerts_data.high_count}, Trung bình: {alerts_data.medium_count}):"
            )
            for a in alerts_data.alerts[:8]:
                alerts_list.append(
                    {
                        "rule_code": a.rule_code.value,
                        "severity": a.severity.value,
                        "student_name": a.student_name,
                        "student_id": a.student_id,
                        "title": a.title,
                        "target_name": a.target_name,
                    }
                )
                alerts_lines.append(f"  + [{a.severity.value}] {a.student_name}: {a.title}")
        else:
            alerts_lines.append("Không có cảnh báo can thiệp sư phạm nào đang kích hoạt.")
        intervention_alerts_summary = "\n".join(alerts_lines)

        # 12. Compact Student Attention Summary
        sa_lines: list[str] = []
        if dashboard.students_needing_attention:
            for sa in dashboard.students_needing_attention[:8]:
                sa_lines.append(f"- {sa.student_name} ({sa.highest_severity.value}): {sa.summary_reason}")
        else:
            sa_lines.append("Toàn bộ học sinh đều đang theo kịp tiến độ học tập.")
        students_attention_summary = "\n".join(sa_lines)

        context_summary = TeacherCopilotContextSummary(
            student_count=len(students_info),
            active_teaching_plan=active_tp_name,
            weak_problem_types_count=len(dashboard.weak_problem_types),
            prerequisite_gaps_count=len(prereq_by_concept),
            common_misconceptions_count=len(dashboard.common_misconceptions),
            total_alerts_count=alerts_data.total_alerts,
            critical_alerts_count=alerts_data.critical_count,
        )

        return TeacherCopilotContextInput(
            classroom_id=classroom.id,
            classroom_name=classroom.name,
            grade_level=classroom.grade_level,
            teacher_name=teacher_name,
            query=query,
            subject_name=subject_name,
            teaching_plan_summary=teaching_plan_summary,
            curriculum_context=curriculum_context,
            class_analytics_summary=class_analytics_summary,
            problem_type_summaries=problem_type_summaries,
            prerequisite_signals_summary=prerequisite_signals_summary,
            misconceptions_summary=misconceptions_summary,
            intervention_alerts_summary=intervention_alerts_summary,
            students_attention_summary=students_attention_summary,
            student_name_to_id=student_name_to_id,
            context_summary=context_summary,
            weak_problem_types_list=weak_problem_types_list,
            prerequisite_gaps_list=prereq_gaps_list,
            misconceptions_list=misconceptions_list,
            alerts_list=alerts_list,
        )

    # --------------------------------------------------------------------------
    # 2. Consult Copilot (AI + Fallback)
    # --------------------------------------------------------------------------

    async def consult_copilot_async(
        self,
        teacher_user_id: UUID,
        classroom_id: UUID,
        request: TeacherCopilotRequest,
    ) -> TeacherCopilotRead:
        """Consult Copilot using AI with guaranteed graceful deterministic fallback."""
        ctx = self.build_context(
            teacher_user_id=teacher_user_id,
            classroom_id=classroom_id,
            query=request.query,
            subject_id=request.subject_id,
            include_synthetic=request.include_synthetic,
        )

        try:
            prompt_text = self.prompt_registry.get_prompt(
                "teacher_copilot",
                "v1",
                variables={
                    "teacher_name": ctx.teacher_name,
                    "classroom_name": ctx.classroom_name,
                    "grade_level": ctx.grade_level,
                    "subject_name": ctx.subject_name,
                    "curriculum_context": ctx.curriculum_context,
                    "teaching_plan_summary": ctx.teaching_plan_summary,
                    "class_analytics_summary": ctx.class_analytics_summary,
                    "problem_type_summaries": ctx.problem_type_summaries,
                    "prerequisite_signals_summary": ctx.prerequisite_signals_summary,
                    "misconceptions_summary": ctx.misconceptions_summary,
                    "intervention_alerts_summary": ctx.intervention_alerts_summary,
                    "students_attention_summary": ctx.students_attention_summary,
                    "teacher_query": ctx.query,
                },
            )

            messages = [AIMessage(role=AIRole.USER, content=prompt_text)]
            response = await self.gateway.generate_structured(
                task_type=AITaskType.TEACHER_COPILOT,
                messages=messages,
                schema=TeacherCopilotAIOutput,
                temperature=0.2,
                prompt_name="teacher_copilot",
                prompt_version="v1",
                user_id=teacher_user_id,
            )

            ai_data: TeacherCopilotAIOutput = response.data

            # Resolve student IDs by matched name
            students_attention: list[TeacherCopilotStudentAttention] = []
            for s in ai_data.students_requiring_attention:
                sid = ctx.student_name_to_id.get(s.student_name)
                students_attention.append(
                    TeacherCopilotStudentAttention(
                        student_id=sid,
                        student_name=s.student_name,
                        reason=s.reason,
                        suggested_focus=s.suggested_focus,
                    )
                )

            observations = [obs.strip() for obs in ai_data.observations if obs.strip()]
            priorities = [p.strip() for p in ai_data.priorities if p.strip()]
            recommended_actions = [a.strip() for a in ai_data.recommended_actions if a.strip()]

            if not observations:
                observations = [
                    f"Lớp học [{ctx.classroom_name}] hiện có {ctx.context_summary.student_count} học sinh đang theo học."
                ]
                if ctx.weak_problem_types_list:
                    weak_str = ", ".join(f"[{w}]" for w in ctx.weak_problem_types_list[:3])
                    observations.append(f"Lớp đang gặp khó khăn ở các dạng bài: {weak_str}.")
            if not priorities:
                priorities = ["1. Tiếp tục theo dõi và củng cố các dạng bài theo kế hoạch giảng dạy."]
            if not recommended_actions:
                recommended_actions = ["Dành 10-15 phút đầu giờ để ôn tập và giải đáp thắc mắc cho học sinh."]

            return TeacherCopilotRead(
                classroom_id=ctx.classroom_id,
                classroom_name=ctx.classroom_name,
                teacher_name=ctx.teacher_name,
                query=ctx.query,
                observations=observations,
                priorities=priorities,
                recommended_actions=recommended_actions,
                students_requiring_attention=students_attention,
                context_summary=ctx.context_summary,
                is_fallback=False,
                generated_at=datetime.now(timezone.utc),
            )

        except Exception as exc:
            logger.warning(
                "TeacherCopilotService: AI consultation failed (%s). Falling back to deterministic copilot.",
                exc,
            )
            return self._generate_deterministic_fallback(ctx)

    def consult_copilot(
        self,
        teacher_user_id: UUID,
        classroom_id: UUID,
        request: TeacherCopilotRequest,
    ) -> TeacherCopilotRead:
        """Synchronous wrapper for consult_copilot_async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self.consult_copilot_async(teacher_user_id, classroom_id, request),
                )
                return future.result()
        else:
            return asyncio.run(
                self.consult_copilot_async(teacher_user_id, classroom_id, request)
            )

    # --------------------------------------------------------------------------
    # 3. Deterministic Fallback Generator
    # --------------------------------------------------------------------------

    def _generate_deterministic_fallback(
        self,
        ctx: TeacherCopilotContextInput,
    ) -> TeacherCopilotRead:
        """Generate a fact-based pedagogical response using pure deterministic rules.

        Customizes focus based on query keywords:
        - Weak problem types: 'yếu', 'dạng bài', 'problem'
        - Prerequisite concepts: 'tiền đề', 'tiên quyết', 'prerequisite', 'khái niệm'
        - Next lesson reinforcement: 'tiết sau', 'tiết tới', 'củng cố', 'ngày mai'
        """
        q_lower = ctx.query.lower()
        now = datetime.now(timezone.utc)

        observations: list[str] = []
        priorities: list[str] = []
        recommended_actions: list[str] = []
        students_attention: list[TeacherCopilotStudentAttention] = []

        # 1. Base Observations
        observations.append(
            f"Lớp học [{ctx.classroom_name}] hiện có {ctx.context_summary.student_count} học sinh đang theo học."
        )

        if ctx.weak_problem_types_list:
            weak_str = ", ".join(f"[{w}]" for w in ctx.weak_problem_types_list[:3])
            observations.append(
                f"Lớp đang gặp khó khăn rõ rệt ở {len(ctx.weak_problem_types_list)} dạng bài có điểm thành thạo < 0.50: {weak_str}."
            )
        else:
            observations.append("Lớp học duy trì phong độ tốt, không có dạng bài nào bị đánh giá yếu (< 0.50).")

        if ctx.prerequisite_gaps_list:
            prereq_names = ", ".join(f"[{p['name']}]" for p in ctx.prerequisite_gaps_list[:3])
            total_affected = sum(len(p.get("affected", [])) for p in ctx.prerequisite_gaps_list)
            observations.append(
                f"Phát hiện {len(ctx.prerequisite_gaps_list)} khái niệm tiên quyết bị hổng ({prereq_names}) "
                f"với {total_affected} lượt học sinh chưa đạt điểm chuẩn 0.50."
            )

        if ctx.misconceptions_list:
            top_misc = ctx.misconceptions_list[0]
            observations.append(
                f"Bẫy sai lầm phổ biến nhất trong lớp là [{top_misc['name']}] "
                f"với {top_misc['affected_count']} học sinh mắc phải."
            )

        if ctx.context_summary.total_alerts_count > 0:
            observations.append(
                f"Hệ thống ghi nhận {ctx.context_summary.total_alerts_count} cảnh báo can thiệp sư phạm "
                f"(trong đó có {ctx.context_summary.critical_alerts_count} cảnh báo ở mức Nghiêm trọng)."
            )

        # 2. Extract Students Requiring Attention
        # Priority: Alerts > Prerequisite gaps
        seen_students: set[str] = set()

        for a in ctx.alerts_list:
            sname = a["student_name"]
            if sname not in seen_students and len(students_attention) < 5:
                seen_students.add(sname)
                sid = a.get("student_id") or ctx.student_name_to_id.get(sname)
                rule = a.get("rule_code", "")
                tname = a.get("target_name", "nội dung học")

                if rule == "PREREQUISITE_GAP":
                    reason = f"Bị hổng khái niệm tiên quyết [{tname}] (điểm < 0.50)"
                    focus = f"Ôn tập và làm bài tập nhận biết về [{tname}]"
                elif rule == "LOW_PROBLEM_TYPE_MASTERY":
                    reason = f"Điểm thành thạo thấp kéo dài ở dạng bài [{tname}] sau nhiều lần thử"
                    focus = f"Củng cố phương pháp giải có giàn giáo cho dạng bài [{tname}]"
                elif rule == "FAILED_REPAIR":
                    reason = f"Chưa đạt chuẩn sau liên tiếp 3 phiên sửa lỗi ở [{tname}]"
                    focus = f"Giáo viên trực tiếp kèm cặp 1-1 để tháo gỡ điểm nghẽn ở [{tname}]"
                elif rule == "PERSISTENT_MISCONCEPTION":
                    reason = f"Lặp lại bẫy sai lầm cố định [{tname}]"
                    focus = f"Chỉ rõ ví dụ phản chứng của bẫy [{tname}]"
                else:
                    reason = a.get("title", "Cần can thiệp sư phạm")
                    focus = f"Hỗ trợ ôn tập và kiểm tra lại bài tập ở [{tname}]"

                students_attention.append(
                    TeacherCopilotStudentAttention(
                        student_id=sid,
                        student_name=sname,
                        reason=reason,
                        suggested_focus=focus,
                    )
                )

        # If not enough, fill from prerequisite gaps
        for p in ctx.prerequisite_gaps_list:
            for aff in p.get("affected", []):
                sname = aff["student_name"]
                if sname not in seen_students and len(students_attention) < 5:
                    seen_students.add(sname)
                    sid = aff.get("student_id") or ctx.student_name_to_id.get(sname)
                    students_attention.append(
                        TeacherCopilotStudentAttention(
                            student_id=sid,
                            student_name=sname,
                            reason=f"Hổng khái niệm nền tảng [{p['name']}] (điểm: {aff.get('score', 0):.2f})",
                            suggested_focus=f"Khởi động phiên sửa lỗi củng cố khái niệm [{p['name']}]",
                        )
                    )

        # 3. Tailor Priorities & Recommendations by query type
        is_prereq_query = any(k in q_lower for k in ["tiền đề", "tiên quyết", "prerequisite", "khái niệm"])
        is_weak_pt_query = any(k in q_lower for k in ["yếu dạng", "dạng bài", "problem", "yếu"])
        is_next_lesson_query = any(k in q_lower for k in ["tiết sau", "tiết tới", "củng cố", "ngày mai", "tiết học"])

        if is_prereq_query:
            priorities.append(
                "1. Ưu tiên cao nhất: Khắc phục các lỗ hổng khái niệm tiên quyết trước khi dạy kiến thức mới."
            )
            if ctx.prerequisite_gaps_list:
                top_p = ctx.prerequisite_gaps_list[0]["name"]
                priorities.append(f"2. Tập trung hỗ trợ nhóm học sinh đang hổng kiến thức ở [{top_p}].")
                priorities.append(
                    "3. Đánh giá lại năng lực giải các dạng bài liên quan sau khi đã củng cố khái niệm nền."
                )
            else:
                priorities.append("2. Lớp không có học sinh hổng kiến thức tiền đề nghiêm trọng; tiếp tục lộ trình chính.")

            recommended_actions.append(
                "Dành 10-15 phút đầu giờ chiếu lại sơ đồ tư duy hoặc bảng tóm tắt định nghĩa của khái niệm tiền đề."
            )
            recommended_actions.append(
                "Khởi động các phiên khắc phục lỗ hổng (Repair Session) tập trung vào khái niệm nền tảng bị hổng."
            )
            recommended_actions.append(
                "Phân công học sinh khá giỏi hỗ trợ chéo các bạn đang gặp khó khăn ở bước giải nền tảng."
            )

        elif is_next_lesson_query:
            if ctx.prerequisite_gaps_list:
                top_p = ctx.prerequisite_gaps_list[0]["name"]
                priorities.append(
                    f"1. Dành thời gian khởi động tiết học để nhắc lại và củng cố khái niệm nền tảng [{top_p}]."
                )
            if ctx.misconceptions_list:
                top_m = ctx.misconceptions_list[0]["name"]
                priorities.append(f"2. Phân tích trực tiếp bẫy sai lầm phổ biến [{top_m}] qua một bài toán ví dụ mẫu.")
            if ctx.weak_problem_types_list:
                top_w = ctx.weak_problem_types_list[0]
                priorities.append(
                    f"3. Dành phần lớn thời lượng luyện tập trên lớp cho dạng bài [{top_w}] theo phương pháp phân tầng."
                )
            if not priorities:
                priorities.append("1. Bám sát kế hoạch giảng dạy chính khóa và duy trì nhịp độ làm bài hiện tại.")

            recommended_actions.append(
                "Bắt đầu tiết học bằng 1 câu hỏi trắc nghiệm kiểm tra nhanh bẫy sai lầm thường gặp để học sinh tự nhận diện."
            )
            recommended_actions.append(
                "Chia bài tập luyện tập trên lớp thành 2 mức độ: mức cơ bản củng cố cho nhóm yếu và mức nâng cao cho nhóm khá."
            )
            recommended_actions.append(
                "Gọi các học sinh thuộc danh sách cần quan tâm lên bảng làm các bước nền tảng để kiểm tra độ hiểu bài."
            )

        else:  # General or weak problem types query
            if ctx.weak_problem_types_list:
                top_w = ctx.weak_problem_types_list[0]
                priorities.append(
                    f"1. Ưu tiên tập trung can thiệp dạng bài yếu nhất: [{top_w}]."
                )
            if ctx.prerequisite_gaps_list:
                top_p = ctx.prerequisite_gaps_list[0]["name"]
                priorities.append(
                    f"2. Kiểm tra và củng cố khái niệm nền tảng [{top_p}] là nguyên nhân gốc rễ gây sai sót."
                )
            if ctx.context_summary.critical_alerts_count > 0:
                priorities.append(
                    f"3. Hỗ trợ ngay {ctx.context_summary.critical_alerts_count} học sinh đang có cảnh báo nghiêm trọng."
                )
            if not priorities:
                priorities.append("1. Duy trì kế hoạch học tập hiện tại; toàn bộ học sinh đạt chuẩn thành thạo cơ bản.")

            recommended_actions.append(
                "Cung cấp hướng dẫn giải mẫu từng bước (worked examples) cho dạng bài mà lớp đang gặp nhiều sai sót nhất."
            )
            recommended_actions.append(
                "Kết nối giữa dạng bài đang học và các kỹ năng tiền đề liên quan để học sinh thấy rõ mối liên hệ kiến thức."
            )
            recommended_actions.append(
                "Khuyến khích học sinh xem lại lý thuyết tóm tắt trên hệ thống trước khi làm bài tập tự học."
            )

        return TeacherCopilotRead(
            classroom_id=ctx.classroom_id,
            classroom_name=ctx.classroom_name,
            teacher_name=ctx.teacher_name,
            query=ctx.query,
            observations=observations,
            priorities=priorities,
            recommended_actions=recommended_actions,
            students_requiring_attention=students_attention,
            context_summary=ctx.context_summary,
            is_fallback=True,
            generated_at=now,
        )
