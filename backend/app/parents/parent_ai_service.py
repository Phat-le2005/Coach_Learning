from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import date, datetime, timezone
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_gateway_singleton
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.types import AIMessage, AIRole, AITaskType
from app.core.config import get_settings
from app.parents.dashboard_schemas import (
    ParentWeeklyAIInput,
    ParentWeeklyAIOutput,
    ParentWeeklyAISummaryRead,
)
from app.parents.dashboard_service import ParentDashboardService
from app.users.models import User

logger = logging.getLogger(__name__)


class ParentAISummaryService:
    """Service to generate pedagogical, constructive weekly AI summaries for parents.

    Strict Architectural & Pedagogical Guarantees:
    - Input strictly limited to aggregated weekly data (no tutor chats, no raw messages, no private conversations).
    - Clear structured output: PROGRESS, CURRENT_CHALLENGE, NEXT_WEEK, HOW_PARENT_CAN_HELP.
    - Pedagogical tone: simple, non-judgmental, constructive.
    - Zero psychological speculation (no diagnosis, no assuming laziness/depression).
    - No alarmism over a single wrong answer.
    - Distinguishes between temporary new difficulties and persistent prerequisite gaps.
    - At most 2 parent recommendations (HOW_PARENT_CAN_HELP <= 2).
    - Grounded strictly in supplied data (no hallucinated weaknesses).
    - Resilient fallback: if AI is unavailable or fails, returns deterministic summary seamlessly.
    """

    def __init__(
        self,
        session: Session,
        gateway: Any | None = None,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.session = session
        self.dashboard_service = ParentDashboardService(session)
        self.gateway = gateway or get_ai_gateway_singleton(get_settings())
        self.prompt_registry = prompt_registry or default_prompt_registry

    # --------------------------------------------------------------------------
    # 1. Context Assembly (Strictly Aggregated Data - Zero Chat / Raw Logs)
    # --------------------------------------------------------------------------

    def build_weekly_context(
        self,
        parent_user_id: UUID,
        student_id: UUID,
        target_date: date | None = None,
    ) -> tuple[ParentWeeklyAIInput, str]:
        """Collect aggregated weekly performance metrics for AI summary generation."""
        parent = self.dashboard_service.require_parent_profile(parent_user_id)
        _, student, user = self.dashboard_service.require_active_relationship(parent.id, student_id)

        parent_user = self.session.get(User, parent.user_id)
        parent_name = (
            parent_user.full_name or parent_user.username or "Phụ huynh"
            if parent_user
            else "Phụ huynh"
        )

        weekly_data = self.dashboard_service.get_student_weekly_data(
            parent_user_id=parent_user_id,
            student_id=student_id,
            target_date=target_date,
        )
        progress_data = self.dashboard_service.get_student_progress(
            parent_user_id=parent_user_id,
            student_id=student_id,
        )

        active_days = sum(
            1
            for d in weekly_data.daily_study_time
            if d.study_time_minutes > 0 or d.questions_attempted > 0
        )

        # Chapter & Topic trends
        chapter_topic_trends: list[dict[str, Any]] = []
        for cp in progress_data.chapter_progress[:5]:
            chapter_topic_trends.append(
                {
                    "chapter_name": cp.chapter_name,
                    "subject_name": cp.subject_name,
                    "mastery_score": cp.mastery_score,
                    "status": cp.status,
                }
            )
        for tp in progress_data.topic_progress[:5]:
            chapter_topic_trends.append(
                {
                    "topic_name": tp.topic_name,
                    "chapter_name": tp.chapter_name,
                    "mastery_score": tp.mastery_score,
                }
            )

        # Major weak problem types
        major_weak_pts: list[dict[str, Any]] = []
        for wa in progress_data.major_weak_areas:
            major_weak_pts.append(
                {
                    "problem_type_name": wa.problem_type_name,
                    "subject_name": wa.subject_name,
                    "mastery_score": wa.mastery_score,
                    "attempt_count": wa.attempt_count,
                    "parent_message": wa.parent_friendly_message,
                    "related_concept": wa.related_concept_name,
                }
            )

        # Persistent prerequisite issues
        persistent_prereqs: list[dict[str, Any]] = []
        for wa in progress_data.major_weak_areas:
            if wa.related_concept_name:
                persistent_prereqs.append(
                    {
                        "concept_name": wa.related_concept_name,
                        "related_problem_type": wa.problem_type_name,
                        "note": "Khái niệm nền tảng cần củng cố lại trước khi tiếp tục dạng bài.",
                    }
                )
        for alert in progress_data.important_intervention_alerts:
            if alert.rule_code == "PREREQUISITE_GAP":
                persistent_prereqs.append(
                    {
                        "title": alert.title,
                        "message": alert.message,
                    }
                )

        # Important intervention alerts
        alerts_summary: list[dict[str, Any]] = []
        for al in progress_data.important_intervention_alerts:
            alerts_summary.append(
                {
                    "rule_code": al.rule_code,
                    "severity": al.severity,
                    "title": al.title,
                    "message": al.message,
                }
            )

        # Exam trend
        exam_trend_summary: list[dict[str, Any]] = []
        for et in weekly_data.exam_trend:
            exam_trend_summary.append(
                {
                    "title": et.title,
                    "date": et.date.strftime("%d/%m/%Y"),
                    "score": et.score,
                    "trend_direction": et.trend_direction,
                }
            )

        context_input = ParentWeeklyAIInput(
            student_name=user.full_name,
            grade_level=student.grade_level,
            week_start_date=weekly_data.week_start_date,
            week_end_date=weekly_data.week_end_date,
            weekly_learning_time_minutes=weekly_data.total_study_time_minutes,
            active_days_count=active_days,
            study_plan_total_tasks=weekly_data.tasks_total_this_week,
            study_plan_completed_tasks=weekly_data.tasks_completed_this_week,
            study_plan_completion_rate=weekly_data.weekly_completion_rate,
            chapter_topic_trends=chapter_topic_trends,
            major_weak_problem_types=major_weak_pts,
            persistent_prerequisite_issues=persistent_prereqs,
            important_intervention_alerts=alerts_summary,
            exam_trend=exam_trend_summary,
        )

        return context_input, parent_name

    # --------------------------------------------------------------------------
    # 2. AI Prompt Formatting
    # --------------------------------------------------------------------------

    def _format_prompt_variables(
        self,
        input_data: ParentWeeklyAIInput,
        parent_name: str,
    ) -> dict[str, str]:
        # Reporting period
        period_str = (
            f"Từ ngày {input_data.week_start_date.strftime('%d/%m/%Y')} "
            f"đến ngày {input_data.week_end_date.strftime('%d/%m/%Y')}"
        )

        # Weekly learning time
        learning_time_str = (
            f"Tổng thời gian học: {input_data.weekly_learning_time_minutes} phút "
            f"qua {input_data.active_days_count}/7 ngày có hoạt động học tập."
        )

        # Study plan completion
        if input_data.study_plan_total_tasks > 0:
            pct = int(round(input_data.study_plan_completion_rate * 100))
            plan_str = (
                f"Đã hoàn thành {input_data.study_plan_completed_tasks}/"
                f"{input_data.study_plan_total_tasks} nhiệm vụ theo kế hoạch ({pct}%)."
            )
        else:
            plan_str = "Chưa có nhiệm vụ học tập theo kế hoạch được giao trong tuần này."

        # Chapter & topic trends
        if input_data.chapter_topic_trends:
            chap_lines = [
                f"- {item.get('chapter_name', item.get('topic_name'))}: "
                f"Mức độ thành thạo {item.get('mastery_score', 0.0):.2f}"
                + (f" ({item['status']})" if "status" in item else "")
                for item in input_data.chapter_topic_trends[:6]
            ]
            chap_trend_str = "\n".join(chap_lines)
        else:
            chap_trend_str = "Đang tiếp thu theo tiến độ chương trình học tiêu chuẩn."

        # Major weak problem types
        if input_data.major_weak_problem_types:
            weak_lines = [
                f"- Dạng bài [{pt['problem_type_name']}]: mức thành thạo {pt['mastery_score']:.2f} "
                f"sau {pt['attempt_count']} lượt làm. ({pt['parent_message']})"
                for pt in input_data.major_weak_problem_types
            ]
            weak_pts_str = "\n".join(weak_lines)
        else:
            weak_pts_str = (
                "Không ghi nhận dạng bài yếu đáng kể. Con tiếp thu đều và đáp ứng yêu cầu các dạng bài."
            )

        # Persistent prerequisite issues
        if input_data.persistent_prerequisite_issues:
            prereq_lines = []
            for item in input_data.persistent_prerequisite_issues:
                if "concept_name" in item:
                    prereq_lines.append(
                        f"- Khái niệm nền tảng [{item['concept_name']}]: liên quan đến dạng [{item.get('related_problem_type', '')}]. "
                        f"{item.get('note', '')}"
                    )
                elif "title" in item:
                    prereq_lines.append(f"- Cảnh báo nền tảng: {item['title']} - {item.get('message', '')}")
            prereq_str = "\n".join(prereq_lines)
        else:
            prereq_str = "Không ghi nhận lỗ hổng kiến thức nền tảng kéo dài."

        # Important intervention alerts
        if input_data.important_intervention_alerts:
            alert_lines = [
                f"- [{al['severity']}] {al['title']}: {al['message']}"
                for al in input_data.important_intervention_alerts
            ]
            alerts_str = "\n".join(alert_lines)
        else:
            alerts_str = "Không có cảnh báo can thiệp nghiêm trọng nào."

        # Exam trend
        if input_data.exam_trend:
            exam_lines = [
                f"- {et['title']} ({et['date']}): {et['score']}/10.0 (Xu hướng: {et['trend_direction']})"
                for et in input_data.exam_trend
            ]
            exam_str = "\n".join(exam_lines)
        else:
            exam_str = "Chưa có bài kiểm tra hoặc bài tập đánh giá mới trong tuần này."

        return {
            "parent_name": parent_name,
            "student_name": input_data.student_name,
            "grade_level": str(input_data.grade_level),
            "reporting_period": period_str,
            "weekly_learning_time_summary": learning_time_str,
            "study_plan_completion_summary": plan_str,
            "chapter_topic_trend_summary": chap_trend_str,
            "major_weak_problem_types_summary": weak_pts_str,
            "persistent_prerequisite_issues_summary": prereq_str,
            "important_intervention_alerts_summary": alerts_str,
            "exam_trend_summary": exam_str,
        }

    # --------------------------------------------------------------------------
    # 3. Execution (Async & Sync)
    # --------------------------------------------------------------------------

    async def generate_weekly_summary_async(
        self,
        parent_user_id: UUID,
        student_id: UUID,
        target_date: date | None = None,
    ) -> ParentWeeklyAISummaryRead:
        """Generate AI weekly summary asynchronously with deterministic fallback."""
        input_data, parent_name = self.build_weekly_context(parent_user_id, student_id, target_date)

        try:
            prompt_vars = self._format_prompt_variables(input_data, parent_name)
            rendered_prompt = self.prompt_registry.get_prompt("parent_summary", "v1", prompt_vars)
            messages = [AIMessage(role=AIRole.USER, content=rendered_prompt)]

            response = await self.gateway.generate_structured(
                task_type=AITaskType.PARENT_SUMMARY,
                messages=messages,
                schema=ParentWeeklyAIOutput,
                temperature=0.3,
                prompt_name="parent_summary",
                prompt_version="v1",
                user_id=parent_user_id,
            )

            ai_output: ParentWeeklyAIOutput = response.data

            # Guardrail: strictly enforce maximum 2 parent recommendations
            cleaned_recommendations = [
                rec.strip() for rec in ai_output.how_parent_can_help if rec.strip()
            ][:2]

            if not cleaned_recommendations:
                cleaned_recommendations = [
                    "Khen ngợi nỗ lực học tập của con trong tuần qua.",
                    "Khích lệ con duy trì thời lượng học 20-30 phút mỗi ngày.",
                ]

            return ParentWeeklyAISummaryRead(
                student_id=student_id,
                student_name=input_data.student_name,
                week_start_date=input_data.week_start_date,
                week_end_date=input_data.week_end_date,
                progress=ai_output.progress.strip(),
                current_challenge=ai_output.current_challenge.strip(),
                next_week=ai_output.next_week.strip(),
                how_parent_can_help=cleaned_recommendations,
                is_fallback=False,
                generated_at=datetime.now(timezone.utc),
            )

        except Exception as exc:
            logger.warning(
                "ParentAISummaryService: AI generation failed (%s). Falling back to deterministic summary.",
                exc,
            )
            return self._generate_deterministic_fallback(student_id, input_data)

    def generate_weekly_summary(
        self,
        parent_user_id: UUID,
        student_id: UUID,
        target_date: date | None = None,
    ) -> ParentWeeklyAISummaryRead:
        """Synchronous wrapper for generate_weekly_summary_async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self.generate_weekly_summary_async(parent_user_id, student_id, target_date),
                )
                return future.result()
        else:
            return asyncio.run(
                self.generate_weekly_summary_async(parent_user_id, student_id, target_date)
            )

    # --------------------------------------------------------------------------
    # 4. Deterministic Fallback (Reliability Guarantee)
    # --------------------------------------------------------------------------

    def _generate_deterministic_fallback(
        self,
        student_id: UUID,
        input_data: ParentWeeklyAIInput,
    ) -> ParentWeeklyAISummaryRead:
        """Produce a constructive, reliable weekly summary deterministically when AI is offline.

        Adheres strictly to all pedagogical guardrails:
        - Non-judgmental tone.
        - Zero psychological speculation.
        - Maximum 2 parent recommendations.
        - Purely derived from supplied aggregated metrics.
        """
        # 1. Progress
        if input_data.weekly_learning_time_minutes > 0:
            progress = (
                f"Trong tuần qua, {input_data.student_name} đã dành tổng cộng {input_data.weekly_learning_time_minutes} "
                f"phút tự học và hoàn thành {input_data.study_plan_completed_tasks}/{input_data.study_plan_total_tasks} "
                f"nhiệm vụ theo kế hoạch học tập."
            )
        else:
            progress = (
                f"Trong tuần qua, hệ thống chưa ghi nhận nhiều thời gian tự học của {input_data.student_name} trên nền tảng. "
                f"Con cần sắp xếp thời gian hợp lý hơn để vào học đều đặn."
            )

        # 2. Current Challenge
        if input_data.major_weak_problem_types:
            top_pt = input_data.major_weak_problem_types[0]
            pt_name = top_pt["problem_type_name"]
            score_pct = int(round(top_pt["mastery_score"] * 100))
            if top_pt.get("related_concept"):
                c_name = top_pt["related_concept"]
                current_challenge = (
                    f"Con đang gặp khó khăn ở dạng bài [{pt_name}] (mức thành thạo {score_pct}%), "
                    f"chủ yếu do cần củng cố thêm khái niệm nền tảng [{c_name}]."
                )
            else:
                current_challenge = (
                    f"Con đang gặp khó khăn ở dạng bài [{pt_name}] (mức thành thạo {score_pct}%), "
                    f"cần thêm thời gian luyện tập với các bài tập vừa sức."
                )
        elif input_data.persistent_prerequisite_issues:
            prereq_item = input_data.persistent_prerequisite_issues[0]
            name = prereq_item.get("concept_name", prereq_item.get("title", "nền tảng"))
            current_challenge = (
                f"Con có một số khái niệm nền tảng [{name}] cần được ôn tập lại để tiếp thu kiến thức mới vững chắc hơn."
            )
        else:
            current_challenge = (
                "Hiện tại con đang tiếp thu tốt chương trình và chưa gặp trở ngại học tập lớn nào."
            )

        # 3. Next Week
        if input_data.major_weak_problem_types:
            top_pt = input_data.major_weak_problem_types[0]
            next_week = (
                f"Mục tiêu tuần tới là tập trung củng cố lại dạng bài [{top_pt['problem_type_name']}], "
                f"đồng thời duy trì nhịp độ làm bài tập đều đặn 20-30 phút mỗi ngày."
            )
        else:
            next_week = (
                "Tuần tới, con nên tiếp tục duy trì nhịp học đều đặn và hoàn thành đúng hạn các nhiệm vụ học tập được giao."
            )

        # 4. How Parent Can Help (Strictly max 2 recommendations)
        if input_data.major_weak_problem_types:
            how_parent_can_help = [
                "Khích lệ con duy trì thời gian học đều đặn khoảng 20-30 phút mỗi ngày trong không gian yên tĩnh.",
                "Động viên con xem lại các ví dụ mẫu cơ bản trước khi làm bài tập để nắm chắc phương pháp.",
            ]
        elif input_data.weekly_learning_time_minutes == 0:
            how_parent_can_help = [
                "Hỏi thăm nhẹ nhàng và cùng con thống nhất một khung giờ tự học cố định trong ngày.",
                "Nhắc nhở con mở ứng dụng hoàn thành các bài tập nhỏ để bắt nhịp lại việc học.",
            ]
        else:
            how_parent_can_help = [
                "Khen ngợi tinh thần tự giác và sự kiên trì học tập của con trong tuần qua.",
                "Tạo không gian sinh hoạt thoải mái để con giữ vững phong độ học tập tốt.",
            ]

        return ParentWeeklyAISummaryRead(
            student_id=student_id,
            student_name=input_data.student_name,
            week_start_date=input_data.week_start_date,
            week_end_date=input_data.week_end_date,
            progress=progress,
            current_challenge=current_challenge,
            next_week=next_week,
            how_parent_can_help=how_parent_can_help[:2],
            is_fallback=True,
            generated_at=datetime.now(timezone.utc),
        )
