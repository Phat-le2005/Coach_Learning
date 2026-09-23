from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway_singleton
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.types import AIMessage, AIRole, AITaskType
from app.core.config import get_settings
from app.classes.models import EnrollmentStatus, StudentEnrollment
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import ProblemType
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.planning.study_explanation_schemas import (
    StudyPlanExplanationInput,
    StudyPlanExplanationItem,
    StudyPlanExplanationOutput,
    StudyPlanExplanationRead,
)
from app.planning.study_models import (
    StudyPlan,
    StudyPlanStatus,
    StudyTask,
    StudyTaskStatus,
)
from app.students.goal_models import AcademicGoal, AcademicGoalStatus
from app.students.models import StudentProfile
from app.users.models import User

logger = logging.getLogger(__name__)


class StudyPlanExplanationService:
    """Service to generate motivational, pedagogical explanations for daily study plans.

    Strict Architectural Guarantees:
    - AI NEVER mutates, re-orders, adds, or deletes StudyTasks. Tasks are deterministic.
    - AI NEVER invents weaknesses outside the supplied input.
    - When AI is unavailable or fails, a deterministic rule-based explanation is returned gracefully.
    - StudyPlan displays 100% normally regardless of AI availability.
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

    # --------------------------------------------------------------------------
    # Context Gathering (DB -> StudyPlanExplanationInput)
    # --------------------------------------------------------------------------

    def build_context(
        self,
        student_id: UUID,
        current_date: date | None = None,
    ) -> StudyPlanExplanationInput:
        """Collect all necessary context for explaining today's study plan."""
        target_date = current_date or date.today()

        student = self.session.get(StudentProfile, student_id)
        if student is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile not found.")

        student_name = "Học sinh"
        if student.user_id:
            user = self.session.get(User, student.user_id)
            if user:
                student_name = user.full_name or user.username or "Học sinh"

        # 1. Active study plan
        plan = self.session.scalar(
            select(StudyPlan)
            .where(
                StudyPlan.student_id == student_id,
                StudyPlan.status == StudyPlanStatus.ACTIVE,
            )
            .order_by(StudyPlan.created_at.desc())
        )

        # 2. Query today's tasks
        today_tasks_raw: list[StudyTask] = []
        if plan:
            today_tasks_raw = list(
                self.session.scalars(
                    select(StudyTask)
                    .where(
                        StudyTask.study_plan_id == plan.id,
                        StudyTask.planned_date == target_date,
                    )
                    .order_by(StudyTask.priority.desc(), StudyTask.order_index.asc(), StudyTask.id.asc())
                ).all()
            )

        # Build task explanation items
        today_task_items: list[StudyPlanExplanationItem] = []
        pt_ids_in_tasks: set[UUID] = set()
        c_ids_in_tasks: set[UUID] = set()

        for t in today_tasks_raw:
            pt_name: str | None = None
            if t.problem_type_id:
                pt_ids_in_tasks.add(t.problem_type_id)
                pt = self.session.get(ProblemType, t.problem_type_id)
                if pt:
                    pt_name = pt.name

            c_name: str | None = None
            if t.concept_id:
                c_ids_in_tasks.add(t.concept_id)
                c = self.session.get(Concept, t.concept_id)
                if c:
                    c_name = c.name

            display_title = pt_name or c_name or f"Nhiệm vụ {t.task_type.value}"

            today_task_items.append(
                StudyPlanExplanationItem(
                    id=t.id,
                    title=display_title,
                    task_type=t.task_type,
                    priority=t.priority,
                    estimated_duration_minutes=t.estimated_duration_minutes,
                    reason_code=t.reason_code,
                    problem_type_id=t.problem_type_id,
                    problem_type_name=pt_name,
                    concept_id=t.concept_id,
                    concept_name=c_name,
                )
            )

        # 3. Academic Goal & Days remaining
        goal_title: str | None = None
        target_score: float | None = None
        days_remaining: int | None = None

        active_goal = self.session.scalar(
            select(AcademicGoal)
            .where(
                AcademicGoal.student_id == student_id,
                AcademicGoal.status == AcademicGoalStatus.ACTIVE,
            )
            .order_by(AcademicGoal.created_at.desc())
        )
        if active_goal:
            goal_title = f"Mục tiêu {active_goal.target_exam}"
            if active_goal.target_university:
                goal_title += f" ({active_goal.target_university})"
            if active_goal.exam_date:
                days_remaining = (active_goal.exam_date - target_date).days
        elif plan and plan.target_date:
            days_remaining = (plan.target_date - target_date).days

        # 4. Recent progress summary (tasks in past 7 days)
        recent_progress_summary: str = "Mới bắt đầu lộ trình học tập."
        if plan:
            seven_days_ago = target_date - timedelta(days=7)
            completed_recent = self.session.scalar(
                select(func.count(StudyTask.id)).where(
                    StudyTask.study_plan_id == plan.id,
                    StudyTask.planned_date >= seven_days_ago,
                    StudyTask.planned_date <= target_date,
                    StudyTask.status == StudyTaskStatus.COMPLETED,
                )
            ) or 0
            total_recent = self.session.scalar(
                select(func.count(StudyTask.id)).where(
                    StudyTask.study_plan_id == plan.id,
                    StudyTask.planned_date >= seven_days_ago,
                    StudyTask.planned_date <= target_date,
                )
            ) or 0
            if total_recent > 0:
                pct = int((completed_recent / total_recent) * 100)
                recent_progress_summary = (
                    f"Đã hoàn thành {completed_recent}/{total_recent} nhiệm vụ "
                    f"({pct}%) trong 7 ngày gần đây."
                )

        # 5. Weak Problem Types (mastery < 0.50)
        weak_pts = list(
            self.session.scalars(
                select(ProblemType.name)
                .join(StudentProblemTypeMastery, StudentProblemTypeMastery.problem_type_id == ProblemType.id)
                .where(
                    StudentProblemTypeMastery.student_id == student_id,
                    StudentProblemTypeMastery.mastery_score < 0.50,
                )
                .order_by(StudentProblemTypeMastery.mastery_score.asc())
                .limit(5)
            ).all()
        )

        # 6. Relevant Weak Concepts (mastery < 0.60, especially associated with today tasks or prerequisites)
        relevant_weak_concepts: list[str] = []
        weak_concept_rows = list(
            self.session.execute(
                select(Concept.id, Concept.name, StudentConceptMastery.mastery_score)
                .join(StudentConceptMastery, StudentConceptMastery.concept_id == Concept.id)
                .where(
                    StudentConceptMastery.student_id == student_id,
                    StudentConceptMastery.mastery_score < 0.60,
                )
                .order_by(StudentConceptMastery.mastery_score.asc())
            ).all()
        )

        if weak_concept_rows:
            # Check if any weak concepts are prerequisites of today tasks
            prereq_weak_names: list[str] = []
            for cid, cname, _ in weak_concept_rows:
                # Is it directly in today's tasks?
                if cid in c_ids_in_tasks:
                    prereq_weak_names.append(cname)
                    continue

                # Or is it a prerequisite in ConceptRelation?
                is_prereq = self.session.scalar(
                    select(ConceptRelation.id).where(
                        ConceptRelation.source_concept_id == cid,
                        ConceptRelation.relation_type == RelationType.PREREQUISITE,
                    ).limit(1)
                )
                if is_prereq:
                    prereq_weak_names.append(cname)

            if prereq_weak_names:
                relevant_weak_concepts = prereq_weak_names[:5]
            else:
                relevant_weak_concepts = [cname for _, cname, _ in weak_concept_rows[:3]]

        # 7. Teaching Plan context
        teaching_plan_context: str | None = None
        enrolled_class_ids = list(
            self.session.scalars(
                select(StudentEnrollment.classroom_id).where(
                    StudentEnrollment.student_id == student_id,
                    StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                )
            ).all()
        )
        if enrolled_class_ids:
            active_tp_items = list(
                self.session.scalars(
                    select(ProblemType.name)
                    .join(TeachingPlanItem, TeachingPlanItem.problem_type_id == ProblemType.id)
                    .join(TeachingPlan, TeachingPlan.id == TeachingPlanItem.teaching_plan_id)
                    .where(
                        TeachingPlan.classroom_id.in_(enrolled_class_ids),
                        TeachingPlan.status == TeachingPlanStatus.ACTIVE,
                    )
                    .order_by(TeachingPlanItem.priority.desc())
                    .limit(3)
                ).all()
            )
            if active_tp_items:
                teaching_plan_context = f"Đang học trên lớp dạng bài: {', '.join(active_tp_items)}."

        return StudyPlanExplanationInput(
            student_name=student_name,
            today_tasks=today_task_items,
            academic_goal_title=goal_title,
            target_score=target_score,
            days_remaining=days_remaining,
            recent_progress_summary=recent_progress_summary,
            weak_problem_types=weak_pts,
            relevant_weak_concepts=relevant_weak_concepts,
            teaching_plan_context=teaching_plan_context,
        )

    # --------------------------------------------------------------------------
    # Explain Study Plan (AI with Deterministic Fallback)
    # --------------------------------------------------------------------------

    async def explain_study_plan_async(
        self,
        input_data: StudyPlanExplanationInput,
        user_id: UUID | None = None,
    ) -> StudyPlanExplanationRead:
        """Generate pedagogical daily explanation using AI, with resilient deterministic fallback."""
        # 1. Edge case: No tasks today
        if not input_data.today_tasks:
            return StudyPlanExplanationRead(
                concise_daily_overview="Hôm nay bạn không có nhiệm vụ học tập nào được lên lịch.",
                priority_reasoning="Bạn đã hoàn thành tốt các mục tiêu trước đó hoặc hôm nay là ngày nghỉ theo kế hoạch. Bạn có thể dành thời gian thư giãn hoặc tự ôn tập thêm nếu muốn.",
                getting_started_guide="Hãy nghỉ ngơi tái tạo năng lượng hoặc tự chọn một bài kiểm tra ngắn trong mục Luyện tập tự do để duy trì phong độ.",
                is_fallback=False,
                generated_at=datetime.now(timezone.utc),
            )

        # 2. Build prompt variables
        goal_text = input_data.academic_goal_title or "Tự học và nâng cao năng lực toán học"
        if input_data.target_score:
            goal_text += f" (Mục tiêu: {input_data.target_score:.1f} điểm)"

        days_text = (
            f"{input_data.days_remaining} ngày"
            if input_data.days_remaining is not None
            else "Chưa xác định ngày thi cụ thể"
        )

        weak_pts_text = (
            "\n".join(f"- {name}" for name in input_data.weak_problem_types)
            if input_data.weak_problem_types
            else "- Không có dạng bài nào bị đánh giá yếu"
        )

        weak_concepts_text = (
            "\n".join(f"- {name}" for name in input_data.relevant_weak_concepts)
            if input_data.relevant_weak_concepts
            else "- Không có khái niệm nền tảng nào bị yếu"
        )

        task_lines = []
        for idx, t in enumerate(input_data.today_tasks, start=1):
            task_lines.append(
                f"{idx}. [Độ ưu tiên: {t.priority}] {t.title} "
                f"({t.estimated_duration_minutes} phút) — Loại: {t.task_type.value} — Lý do: {t.reason_code}"
            )
        tasks_text = "\n".join(task_lines)

        try:
            prompt_text = self.prompt_registry.get_prompt(
                "study_plan_explainer",
                "v1",
                variables={
                    "student_name": input_data.student_name,
                    "academic_goal": goal_text,
                    "days_remaining": days_text,
                    "recent_progress": input_data.recent_progress_summary or "Đang duy trì lộ trình học tập",
                    "weak_problem_types_summary": weak_pts_text,
                    "relevant_weak_concepts_summary": weak_concepts_text,
                    "teaching_plan_context": input_data.teaching_plan_context or "Không có bài học lớp học cụ thể",
                    "today_tasks_summary": tasks_text,
                },
            )

            messages = [AIMessage(role=AIRole.USER, content=prompt_text)]

            response = await self.gateway.generate_structured(
                task_type=AITaskType.STUDY_PLAN_EXPLANATION,
                messages=messages,
                schema=StudyPlanExplanationOutput,
                temperature=0.3,
                prompt_name="study_plan_explainer",
                prompt_version="v1",
                user_id=user_id,
            )

            ai_data: StudyPlanExplanationOutput = response.data

            return StudyPlanExplanationRead(
                concise_daily_overview=ai_data.concise_daily_overview.strip(),
                priority_reasoning=ai_data.priority_reasoning.strip(),
                getting_started_guide=ai_data.getting_started_guide.strip(),
                is_fallback=False,
                generated_at=datetime.now(timezone.utc),
            )

        except Exception as exc:
            logger.warning(
                "StudyPlanExplanationService: AI consultation failed (%s). Falling back to deterministic explanation.",
                exc,
            )
            return self._generate_deterministic_fallback(input_data)

    def explain_study_plan(
        self,
        input_data: StudyPlanExplanationInput,
        user_id: UUID | None = None,
    ) -> StudyPlanExplanationRead:
        """Synchronous wrapper for explain_study_plan_async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run, self.explain_study_plan_async(input_data, user_id)
                )
                return future.result()
        else:
            return asyncio.run(self.explain_study_plan_async(input_data, user_id))

    # --------------------------------------------------------------------------
    # Deterministic Rule-based Fallback
    # --------------------------------------------------------------------------

    def _generate_deterministic_fallback(
        self,
        input_data: StudyPlanExplanationInput,
    ) -> StudyPlanExplanationRead:
        """Generate high-quality pedagogical explanation strictly using deterministic rules.

        Guarantees:
        - Never invents weaknesses not in input.
        - Accurately references top priority tasks.
        - Provides immediate actionable guidance.
        """
        tasks = input_data.today_tasks
        if not tasks:
            return StudyPlanExplanationRead(
                concise_daily_overview="Hôm nay bạn không có nhiệm vụ học tập nào được lên lịch.",
                priority_reasoning="Lộ trình học tập đang ở trạng thái tối ưu hoặc là ngày nghỉ theo kế hoạch.",
                getting_started_guide="Hãy nghỉ ngơi hoặc tự chọn bài kiểm tra ngắn trong mục Luyện tập tự do.",
                is_fallback=True,
                generated_at=datetime.now(timezone.utc),
            )

        total_tasks = len(tasks)
        total_mins = sum(t.estimated_duration_minutes for t in tasks)
        top_task = max(tasks, key=lambda t: t.priority)

        # 1. Overview
        overview = (
            f"Kế hoạch hôm nay gồm {total_tasks} nhiệm vụ với tổng thời lượng dự kiến "
            f"khoảng {total_mins} phút, được phân bổ phù hợp với năng lực và mục tiêu học tập của bạn."
        )

        # 2. Priority Reasoning (Deterministic)
        prereq_part = ""
        if input_data.relevant_weak_concepts:
            prereq_part = f"; đồng thời củng cố kỹ năng nền tảng [{', '.join(input_data.relevant_weak_concepts[:2])}]"

        if input_data.weak_problem_types:
            weak_names = ", ".join(input_data.weak_problem_types[:2])
            reasoning = (
                f"Hôm nay ưu tiên '{top_task.title}' vì kết quả đánh giá gần đây ở nội dung này còn yếu "
                f"(thuộc nhóm cần lưu ý: {weak_names}){prereq_part}. Việc luyện tập tập trung sẽ giúp khắc phục dứt điểm lỗ hổng."
            )
        elif top_task.reason_code == "CURRENT_TEACHING_PLAN" or input_data.teaching_plan_context:
            reasoning = (
                f"Hôm nay ưu tiên '{top_task.title}' theo sát tiến độ bài học trên lớp để đảm bảo nắm chắc kiến thức "
                f"và hoàn thành tốt yêu cầu của giáo viên{prereq_part}."
            )
        elif top_task.reason_code == "REVIEW_DUE":
            reasoning = (
                f"Hôm nay ưu tiên ôn tập '{top_task.title}' theo chu kỳ lặp lại ngắt quãng (spaced repetition) "
                f"nhằm củng cố trí nhớ dài hạn và chuẩn bị sẵn sàng cho kỳ thi."
            )
        elif top_task.reason_code == "EXAM_PREPARATION":
            days_str = f"còn {input_data.days_remaining} ngày nữa là đến kỳ thi" if input_data.days_remaining else "kỳ thi đang đến gần"
            reasoning = (
                f"Hôm nay ưu tiên luyện đề và kiểm tra tổng hợp '{top_task.title}' vì {days_str}, "
                f"giúp làm quen với áp lực thời gian và rèn luyện kỹ năng giải đề."
            )
        else:
            reasoning = (
                f"Hôm nay ưu tiên '{top_task.title}' với mức ưu tiên hàng đầu để duy trì nhịp độ học tập "
                f"và từng bước hoàn thành mục tiêu đề ra{prereq_part}."
            )

        # 3. Getting Started Guide
        guide = (
            f"Hãy bắt đầu với nhiệm vụ '{top_task.title}' ({top_task.estimated_duration_minutes} phút). "
            f"Hãy chuẩn bị giấy nháp, đọc kỹ yêu cầu đề bài và xem lại các lưu ý trọng tâm trước khi làm bài."
        )

        return StudyPlanExplanationRead(
            concise_daily_overview=overview,
            priority_reasoning=reasoning,
            getting_started_guide=guide,
            is_fallback=True,
            generated_at=datetime.now(timezone.utc),
        )
