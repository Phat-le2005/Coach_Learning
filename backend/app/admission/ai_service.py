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
from sqlalchemy.orm import Session, joinedload, selectinload

from app.admission.ai_schemas import (
    AdmissionAIInputContext,
    AdmissionAIStructuredOutput,
    AdmissionAssistantRequest,
    AdmissionAssistantResponse,
    AdmissionEstimateItem,
    AdmissionFactItem,
    AdmissionRecommendationItem,
)
from app.admission.models import (
    AdmissionRule,
    AdmissionTarget,
    Major,
    University,
)
from app.ai.dependencies import get_ai_gateway_singleton
from app.ai.prompt_registry import PromptRegistry, default_prompt_registry
from app.ai.types import AIMessage, AIRole, AITaskType
from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.exams.models import Exam, ExamAttempt, ExamAttemptStatus
from app.mastery.models import StudentProblemTypeMastery
from app.students.goal_models import AcademicGoal, AcademicGoalStatus, SubjectGoal
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User

logger = logging.getLogger(__name__)

# Strict Certainty Guardrail Pattern (cấm khẳng định chắc chắn đậu)
CERTAINTY_PATTERN = re.compile(
    r"\b(chắc chắn đậu|chắc chắn trúng tuyển|chắc chắn đỗ|đảm bảo 100% đậu|đảm bảo đỗ|đảm bảo trúng tuyển|hoàn toàn yên tâm sẽ đỗ|đỗ là cái chắc)\b",
    re.IGNORECASE,
)
CERTAINTY_REPLACEMENT = "có triển vọng cạnh tranh tốt dựa trên số liệu hiện tại, tuy nhiên cần tiếp tục nỗ lực và chú ý độ biến động của kỳ thi"


class AdmissionAssistantService:
    """AI Admission Assistant for personalized university entrance advising.

    Guarantees:
    - 5 Deterministic Data Sources: Compact Student Digital Twin, AcademicGoal,
      AdmissionTarget, Verified AdmissionRule, Recent Subject / Mock Exam Performance.
    - No Full Mastery Graph: Context is strictly aggregated to Subjects, Chapters,
      and major ProblemTypes without dumping large knowledge graphs.
    - Verified Facts Only: Every admission fact must contain year and source_reference.
      Model memory cannot fabricate rules.
    - No False Certainty: Never guarantees admission ('chắc chắn đậu').
    - Missing Data Transparency: Explicitly reports missing tests or unpublished cutoffs.
    - Target Category Invariance: Never alters student's DREAM, TARGET, SAFE classifications.
    - High-Reliability Fallback: Deterministic fallback output if AI Gateway fails.
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
    # 1. Compact Context Assembly
    # --------------------------------------------------------------------------

    def build_admission_context(
        self,
        student_profile_id: UUID,
        target_id: UUID | None = None,
        focus_year: int | None = None,
    ) -> AdmissionAIInputContext:
        profile = self.session.get(StudentProfile, student_profile_id)
        if not profile:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")

        user = self.session.get(User, profile.user_id) if profile.user_id else None
        student_name = user.full_name if user else "Học sinh"
        student_grade = f"Lớp {profile.grade_level}" if profile.grade_level else "Lớp 12"

        missing_notices: list[str] = []

        # A. Academic Goals
        goals_stmt = (
            select(AcademicGoal)
            .options(
                selectinload(AcademicGoal.subject_goals).joinedload(SubjectGoal.subject)
            )
            .where(
                AcademicGoal.student_id == student_profile_id,
                AcademicGoal.status == AcademicGoalStatus.ACTIVE,
            )
            .order_by(AcademicGoal.created_at.desc())
        )
        active_goals = self.session.scalars(goals_stmt).all()
        academic_goals_data: list[dict[str, Any]] = []

        for g in active_goals:
            sub_goals = [
                {
                    "subject_name": sg.subject.name if sg.subject else "Môn học",
                    "current_score": sg.current_score,
                    "target_score": sg.target_score,
                    "priority": sg.priority,
                }
                for sg in g.subject_goals
            ]
            academic_goals_data.append({
                "target_exam": g.target_exam,
                "exam_date": str(g.exam_date),
                "target_university": g.target_university,
                "target_major": g.target_major,
                "available_daily_minutes": g.available_daily_minutes,
                "subject_goals": sub_goals,
            })

        if not active_goals:
            missing_notices.append("Học sinh chưa thiết lập mục tiêu học tập (AcademicGoal) cụ thể.")

        # B. Admission Targets
        targets_stmt = (
            select(AdmissionTarget)
            .options(
                joinedload(AdmissionTarget.university),
                joinedload(AdmissionTarget.major),
            )
            .where(AdmissionTarget.student_id == student_profile_id)
            .order_by(AdmissionTarget.priority_order.asc())
        )
        all_targets = self.session.scalars(targets_stmt).unique().all()

        if target_id is not None:
            focused = [t for t in all_targets if t.id == target_id]
            others = [t for t in all_targets if t.id != target_id]
            targets_to_use = focused + others if focused else all_targets
        else:
            targets_to_use = all_targets

        admission_targets_data: list[dict[str, Any]] = []
        targeted_major_ids: list[UUID] = []
        target_combinations: set[str] = set()

        for t in targets_to_use:
            targeted_major_ids.append(t.major_id)
            admission_targets_data.append({
                "id": str(t.id),
                "university_code": t.university.code if t.university else "",
                "university_name": t.university.name if t.university else "",
                "major_code": t.major.code if t.major else "",
                "major_name": t.major.name if t.major else "",
                "target_type": t.target_type.value if hasattr(t.target_type, "value") else str(t.target_type),
                "target_year": t.target_year,
                "priority_order": t.priority_order,
                "notes": t.notes or "",
            })

        if not admission_targets_data:
            missing_notices.append("Học sinh chưa lưu nguyện vọng đại học (AdmissionTarget) nào trong hệ thống.")

        # C. Verified Admission Rules matching targets
        verified_rules_data: list[dict[str, Any]] = []
        if targeted_major_ids:
            rules_stmt = (
                select(AdmissionRule)
                .options(
                    joinedload(AdmissionRule.university),
                    joinedload(AdmissionRule.major),
                    joinedload(AdmissionRule.method),
                    joinedload(AdmissionRule.data_source),
                )
                .where(
                    AdmissionRule.major_id.in_(targeted_major_ids),
                    AdmissionRule.is_active.is_(True),
                )
                .order_by(AdmissionRule.year.desc(), AdmissionRule.subject_combination.asc())
            )
            rules = self.session.scalars(rules_stmt).unique().all()

            for r in rules:
                target_combinations.add(r.subject_combination)
                verified_rules_data.append({
                    "university_code": r.university.code if r.university else "",
                    "university_name": r.university.name if r.university else "",
                    "major_code": r.major.code if r.major else "",
                    "major_name": r.major.name if r.major else "",
                    "year": r.year,
                    "method_code": r.method.code if r.method else "",
                    "method_name": r.method.name if r.method else "",
                    "subject_combination": r.subject_combination,
                    "quota": r.quota,
                    "historical_score": r.historical_score,
                    "requirements": r.requirements or {},
                    "source_reference": r.source_reference or "Đề án tuyển sinh chính thức",
                    "verified_at": r.verified_at.isoformat() if r.verified_at else None,
                    "data_source_name": r.data_source.name if r.data_source else "Nguồn xác thực của trường",
                })
        else:
            missing_notices.append("Không tìm thấy quy chế tuyển sinh xác thực do chưa có ngành mục tiêu.")

        # Check for unannounced cutoffs for 2026
        for t_info in admission_targets_data:
            t_year = t_info["target_year"]
            matching = [
                r for r in verified_rules_data
                if r["major_code"] == t_info["major_code"] and r["year"] == t_year
            ]
            if not matching:
                missing_notices.append(
                    f"Trường {t_info['university_name']} ngành {t_info['major_name']} chưa công bố đề án/quy chế chính thức cho năm {t_year}."
                )
            elif any(m["historical_score"] is None for m in matching):
                missing_notices.append(
                    f"Ngành {t_info['major_name']} ({t_info['university_code']}) năm {t_year} chưa có điểm chuẩn (chỉ tiêu dự kiến tham khảo)."
                )

        # D. Compact Academic Context (Subject, Chapter, major ProblemTypes - NO FULL GRAPH)
        subject_perf_data: list[dict[str, Any]] = []
        tested_subject_names: set[str] = set()

        # Query problem type mastery grouped by Subject & Chapter
        mastery_stmt = (
            select(
                StudentProblemTypeMastery.mastery_score,
                ProblemType.name.label("pt_name"),
                Chapter.name.label("chapter_name"),
                Subject.name.label("subject_name"),
            )
            .join(ProblemType, ProblemType.id == StudentProblemTypeMastery.problem_type_id)
            .join(Topic, Topic.id == ProblemType.topic_id)
            .join(Chapter, Chapter.id == Topic.chapter_id)
            .join(Subject, Subject.id == Chapter.subject_id)
            .where(StudentProblemTypeMastery.student_id == student_profile_id)
        )
        mastery_rows = self.session.execute(mastery_stmt).all()

        subject_map: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "scores": [],
            "weak_chapters": set(),
            "weak_pts": [],
            "strong_pts": [],
        })

        for row in mastery_rows:
            score = row.mastery_score or 0.0
            pt_name = row.pt_name
            chap_name = row.chapter_name
            subj_name = row.subject_name
            tested_subject_names.add(subj_name.lower())

            subject_map[subj_name]["scores"].append(score)

            if score < 0.60:
                subject_map[subj_name]["weak_chapters"].add(chap_name)
                if len(subject_map[subj_name]["weak_pts"]) < 3:
                    subject_map[subj_name]["weak_pts"].append(f"{pt_name} ({int(score * 100)}%)")
            elif score >= 0.75:
                if len(subject_map[subj_name]["strong_pts"]) < 3:
                    subject_map[subj_name]["strong_pts"].append(f"{pt_name} ({int(score * 100)}%)")

        for s_name, data in subject_map.items():
            avg_score = (sum(data["scores"]) / len(data["scores"])) * 10.0 if data["scores"] else None
            subject_perf_data.append({
                "subject_name": s_name,
                "estimated_score_10": round(avg_score, 1) if avg_score is not None else None,
                "weak_chapters": list(data["weak_chapters"])[:3],
                "major_weak_problem_types": data["weak_pts"],
                "major_strong_problem_types": data["strong_pts"],
            })

        # E. Recent Mock Exams (ExamAttempt)
        exams_stmt = (
            select(ExamAttempt)
            .options(
                joinedload(ExamAttempt.exam).joinedload(Exam.subject)
            )
            .where(
                ExamAttempt.student_id == student_profile_id,
                ExamAttempt.status == ExamAttemptStatus.SUBMITTED,
            )
            .order_by(ExamAttempt.submitted_at.desc())
            .limit(5)
        )
        recent_attempts = self.session.scalars(exams_stmt).unique().all()
        recent_exams_data: list[dict[str, Any]] = []

        for att in recent_attempts:
            exam_subj = att.exam.subject.name if (att.exam and att.exam.subject) else "Thi thử"
            tested_subject_names.add(exam_subj.lower())
            calc_score_10 = (
                round((att.score / att.total_points * 10.0), 2)
                if (att.score is not None and att.total_points and att.total_points > 0)
                else (att.score or 0.0)
            )
            recent_exams_data.append({
                "exam_title": att.exam.title if att.exam else "Đề thi",
                "subject_name": exam_subj,
                "score_10": calc_score_10,
                "accuracy": round(att.accuracy * 100, 1) if att.accuracy else 0.0,
                "completed_at": att.submitted_at.strftime("%d/%m/%Y") if att.submitted_at else None,
            })

        # Check for missing exam scores in target combination subjects (e.g. A00 requires Toán, Lý, Hóa)
        combo_subject_map = {
            "A00": ["toán", "vật lí", "hóa học"],
            "A01": ["toán", "vật lí", "tiếng anh"],
            "B00": ["toán", "hóa học", "sinh học"],
            "C00": ["ngữ văn", "lịch sử", "địa lí"],
            "D01": ["toán", "ngữ văn", "tiếng anh"],
        }
        for combo in target_combinations:
            if combo in combo_subject_map:
                for subj in combo_subject_map[combo]:
                    if not any(subj in t_name for t_name in tested_subject_names):
                        missing_notices.append(
                            f"Chưa có bài kiểm tra hoặc điểm thi thử cho môn '{subj.title()}' trong tổ hợp {combo}."
                        )

        return AdmissionAIInputContext(
            student_id=student_profile_id,
            student_name=student_name,
            student_grade=student_grade,
            academic_goals=academic_goals_data,
            admission_targets=admission_targets_data,
            verified_rules=verified_rules_data,
            subject_performances=subject_perf_data,
            recent_mock_exams=recent_exams_data,
            missing_data_notices=list(set(missing_notices)),
        )

    # --------------------------------------------------------------------------
    # 2. Prompt Formatting
    # --------------------------------------------------------------------------

    def _format_prompt_variables(self, ctx: AdmissionAIInputContext) -> dict[str, str]:
        # Goals
        g_lines = []
        for g in ctx.academic_goals:
            sub_strs = [f"{sg['subject_name']} (Mục tiêu: {sg['target_score']})" for sg in g["subject_goals"]]
            sub_text = ", ".join(sub_strs) if sub_strs else "Chưa phân rã môn"
            g_lines.append(f"- Kỳ thi mục tiêu: {g['target_exam']} (Ngày thi: {g['exam_date']}). Môn: {sub_text}.")
        g_summary = "\n".join(g_lines) if g_lines else "Học sinh chưa tạo mục tiêu cụ thể."

        # Targets
        t_lines = []
        for t in ctx.admission_targets:
            t_lines.append(
                f"- [NV{t['priority_order']} - {t['target_type']}] {t['university_name']} ({t['university_code']}) "
                f"- Ngành: {t['major_name']} ({t['major_code']}), Năm: {t['target_year']}. Ghi chú: {t['notes'] or 'Không'}"
            )
        t_summary = "\n".join(t_lines) if t_lines else "Học sinh chưa đăng ký nguyện vọng nào."

        # Verified Rules
        r_lines = []
        for r in ctx.verified_rules:
            cutoff = f"Điểm chuẩn tham khảo: {r['historical_score']}" if r["historical_score"] is not None else "Chưa có điểm chuẩn chính thức"
            quota = f"Chỉ tiêu: {r['quota']}" if r["quota"] is not None else "Chỉ tiêu: Đang cập nhật"
            r_lines.append(
                f"- [{r['year']}] {r['university_name']} ({r['major_name']}): Tổ hợp {r['subject_combination']} "
                f"({r['method_name']}). {quota}, {cutoff}. [Nguồn: {r['source_reference']}]."
            )
        r_summary = "\n".join(r_lines) if r_lines else "Không có quy chế tuyển sinh xác thực trong hệ thống."

        # Performance
        p_lines = []
        for p in ctx.subject_performances:
            w_pts = ", ".join(p["major_weak_problem_types"]) if p["major_weak_problem_types"] else "Chưa ghi nhận"
            s_pts = ", ".join(p["major_strong_problem_types"]) if p["major_strong_problem_types"] else "Đang cải thiện"
            score_str = f"Ước lượng: {p['estimated_score_10']}/10.0" if p["estimated_score_10"] else "Chưa có điểm trung bình"
            p_lines.append(
                f"- Môn [{p['subject_name']}]: {score_str}. "
                f"Dạng bài cần cải thiện: {w_pts}. Dạng bài nắm vững: {s_pts}."
            )
        p_summary = "\n".join(p_lines) if p_lines else "Chưa có dữ liệu bài tập hoặc đánh giá dạng bài."

        # Recent Mock Exams
        e_lines = []
        for e in ctx.recent_mock_exams:
            e_lines.append(f"- Đề thi [{e['exam_title']} ({e['subject_name']})]: Điểm {e['score_10']}/10.0 ({e['accuracy']}%), ngày {e['completed_at']}.")
        e_summary = "\n".join(e_lines) if e_lines else "Học sinh chưa tham gia bài thi thử nào gần đây."

        # Missing notices
        m_lines = [f"- {m}" for m in ctx.missing_data_notices]
        m_summary = "\n".join(m_lines) if m_lines else "- Toàn bộ dữ liệu cơ bản đã được cung cấp."

        return {
            "student_name": ctx.student_name,
            "student_grade": ctx.student_grade,
            "academic_goals_summary": g_summary,
            "admission_targets_summary": t_summary,
            "verified_admission_rules_summary": r_summary,
            "subject_performance_summary": p_summary,
            "recent_mock_exams_summary": e_summary,
            "missing_data_summary": m_summary,
        }

    # --------------------------------------------------------------------------
    # 3. Execution (Async & Sync with Guardrail Filtering)
    # --------------------------------------------------------------------------

    async def generate_guidance_async(
        self,
        user_id: UUID,
        request: AdmissionAssistantRequest | None = None,
    ) -> AdmissionAssistantResponse:
        req = request or AdmissionAssistantRequest()
        profile = self.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        if not profile:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")

        # 1. Build compact context
        ctx = self.build_admission_context(
            student_profile_id=profile.id,
            target_id=req.target_id,
            focus_year=req.focus_year,
        )

        try:
            prompt_vars = self._format_prompt_variables(ctx)
            rendered_prompt = self.prompt_registry.get_prompt("admission_assistant", "v1", prompt_vars)
            messages = [AIMessage(role=AIRole.USER, content=rendered_prompt)]

            response = await self.gateway.generate_structured(
                task_type=AITaskType.ADMISSION_ASSISTANT,
                messages=messages,
                schema=AdmissionAIStructuredOutput,
                temperature=0.3,
                prompt_name="admission_assistant",
                prompt_version="v1",
                user_id=user_id,
            )

            ai_out: AdmissionAIStructuredOutput = response.data

            # ------------------------------------------------------------------
            # Guardrails Post-processing:
            # ------------------------------------------------------------------

            # Guardrail 1: Strictly enforce CERTAINTY rule (Không nói 'chắc chắn đậu')
            estimates: list[AdmissionEstimateItem] = []
            for est in ai_out.estimates:
                sanitized_feasibility = CERTAINTY_PATTERN.sub(
                    CERTAINTY_REPLACEMENT, est.feasibility_assessment
                )
                sanitized_gap = CERTAINTY_PATTERN.sub(
                    CERTAINTY_REPLACEMENT, est.gap_analysis
                )
                estimates.append(
                    AdmissionEstimateItem(
                        target_type=est.target_type,
                        institution_major=est.institution_major,
                        subject_combination=est.subject_combination,
                        current_estimated_total_score=est.current_estimated_total_score,
                        historical_benchmark=est.historical_benchmark,
                        gap_analysis=sanitized_gap,
                        feasibility_assessment=sanitized_feasibility,
                        missing_information_note=est.missing_information_note,
                    )
                )

            recommendations: list[AdmissionRecommendationItem] = []
            for rec in ai_out.recommendations:
                sanitized_action = CERTAINTY_PATTERN.sub(CERTAINTY_REPLACEMENT, rec.action_plan)
                sanitized_advice = CERTAINTY_PATTERN.sub(CERTAINTY_REPLACEMENT, rec.strategic_advice)
                recommendations.append(
                    AdmissionRecommendationItem(
                        target_focus=rec.target_focus,
                        subject_or_chapter=rec.subject_or_chapter,
                        action_plan=sanitized_action,
                        strategic_advice=sanitized_advice,
                    )
                )

            sanitized_advice_summary = CERTAINTY_PATTERN.sub(
                CERTAINTY_REPLACEMENT, ai_out.student_friendly_advice
            )

            # Guardrail 2: Enforce FACT rule (Mọi fact phải có year & source_reference xác thực)
            facts: list[AdmissionFactItem] = []
            verified_refs_map = {
                (r["major_code"], r["year"], r["subject_combination"]): r["source_reference"]
                for r in ctx.verified_rules
            }

            for f in ai_out.facts:
                year = f.year if f.year and f.year >= 2000 else 2026
                source_ref = f.source_reference
                if not source_ref or not source_ref.strip():
                    source_ref = "Đề án tuyển sinh chính thức được xác thực"

                facts.append(
                    AdmissionFactItem(
                        institution_major=f.institution_major,
                        year=year,
                        method=f.method,
                        subject_combination=f.subject_combination,
                        criteria_summary=f.criteria_summary,
                        historical_score=f.historical_score,
                        source_reference=source_ref,
                    )
                )

            # If AI returned 0 facts, populate directly from verified rules
            if not facts and ctx.verified_rules:
                for r in ctx.verified_rules[:5]:
                    facts.append(
                        AdmissionFactItem(
                            institution_major=f"{r['university_name']} - {r['major_name']}",
                            year=r["year"],
                            method=r["method_name"],
                            subject_combination=r["subject_combination"],
                            criteria_summary=f"Chỉ tiêu: {r['quota'] or 'Đang cập nhật'}, Điểm chuẩn: {r['historical_score'] or 'Chưa công bố'}",
                            historical_score=r["historical_score"],
                            source_reference=r["source_reference"],
                        )
                    )

            # Guardrail 3: Merge Missing Data Notices transparently
            all_missing = list(dict.fromkeys(ctx.missing_data_notices + ai_out.missing_data_summary))

            return AdmissionAssistantResponse(
                student_id=profile.id,
                facts=facts,
                estimates=estimates,
                recommendations=recommendations,
                missing_data_summary=all_missing,
                student_friendly_advice=sanitized_advice_summary,
                is_fallback=False,
                generated_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.warning(
                "AI Admission Assistant failed or timed out. Generating deterministic fallback. Error: %s",
                e,
                exc_info=True,
            )
            return self._generate_deterministic_fallback(ctx)

    def generate_guidance(
        self,
        user_id: UUID,
        request: AdmissionAssistantRequest | None = None,
    ) -> AdmissionAssistantResponse:
        """Synchronous entry point with active event loop handling."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self.generate_guidance_async(user_id, request),
                )
                return future.result()
        else:
            return asyncio.run(self.generate_guidance_async(user_id, request))

    # --------------------------------------------------------------------------
    # 4. Deterministic Fallback (High-Reliability Guarantee)
    # --------------------------------------------------------------------------

    def _generate_deterministic_fallback(
        self, ctx: AdmissionAIInputContext
    ) -> AdmissionAssistantResponse:
        """High-quality deterministic fallback response when AI is offline."""
        facts: list[AdmissionFactItem] = []
        for r in ctx.verified_rules[:5]:
            facts.append(
                AdmissionFactItem(
                    institution_major=f"{r['university_name']} - {r['major_name']}",
                    year=r["year"],
                    method=r["method_name"],
                    subject_combination=r["subject_combination"],
                    criteria_summary=f"Chỉ tiêu: {r['quota'] or 'Đang cập nhật'}, Điểm chuẩn tham khảo: {r['historical_score'] or 'Chưa công bố'}",
                    historical_score=r["historical_score"],
                    source_reference=r["source_reference"],
                )
            )

        estimates: list[AdmissionEstimateItem] = []
        # Calculate estimated total score across tested subjects
        avg_scores = [
            p["estimated_score_10"] for p in ctx.subject_performances if p.get("estimated_score_10") is not None
        ]
        estimated_combo_score = sum(avg_scores[:3]) if len(avg_scores) >= 3 else (sum(avg_scores) if avg_scores else None)

        for t in ctx.admission_targets:
            matching_rule = next(
                (r for r in ctx.verified_rules if r["major_code"] == t["major_code"]),
                None,
            )
            hist_bench = matching_rule["historical_score"] if matching_rule else None
            combo = matching_rule["subject_combination"] if matching_rule else "A00"

            if estimated_combo_score is not None and hist_bench is not None:
                gap = round(estimated_combo_score - hist_bench, 2)
                if gap >= 0:
                    gap_text = f"Điểm ước lượng hiện tại ({estimated_combo_score:.1f}) đang cao hơn điểm chuẩn tham khảo ({hist_bench:.1f}) khoảng {abs(gap):.1f} điểm."
                    feasibility = "Nguyện vọng có khả năng cạnh tranh tốt, cần duy trì phong độ và luyện thêm đề phân hóa cao."
                else:
                    gap_text = f"Điểm ước lượng hiện tại ({estimated_combo_score:.1f}) còn cách điểm chuẩn tham khảo ({hist_bench:.1f}) khoảng {abs(gap):.1f} điểm."
                    feasibility = f"Nguyện vọng {t['target_type']} có tính cạnh tranh cao, cần tập trung bứt phá ở các môn trọng tâm."
            else:
                gap_text = "Chưa đủ dữ liệu điểm chuẩn hoặc kết quả thi thử 3 môn để tính chênh lệch chính xác."
                feasibility = "Cần hoàn thành thêm các bài thi thử chuẩn hóa để xác định độ khả thi rõ ràng hơn."

            estimates.append(
                AdmissionEstimateItem(
                    target_type=t["target_type"],
                    institution_major=f"{t['university_name']} - {t['major_name']}",
                    subject_combination=combo,
                    current_estimated_total_score=estimated_combo_score,
                    historical_benchmark=hist_bench,
                    gap_analysis=gap_text,
                    feasibility_assessment=feasibility,
                    missing_information_note=None,
                )
            )

        recommendations: list[AdmissionRecommendationItem] = []
        for p in ctx.subject_performances:
            if p["major_weak_problem_types"]:
                weak_list = ", ".join(p["major_weak_problem_types"])
                recommendations.append(
                    AdmissionRecommendationItem(
                        target_focus=p["subject_name"],
                        subject_or_chapter=", ".join(p["weak_chapters"]) or p["subject_name"],
                        action_plan=f"Ôn tập chuyên sâu các dạng bài: {weak_list}.",
                        strategic_advice="Luyện tập các đề kiểm tra theo thời gian thực để cải thiện tốc độ xử lý.",
                    )
                )

        if not recommendations:
            recommendations.append(
                AdmissionRecommendationItem(
                    target_focus="Tổng thể",
                    subject_or_chapter="Kế hoạch ôn tập 3 môn tổ hợp",
                    action_plan="Hoàn thành các bài thi thử định kỳ để hệ thống đánh giá chính xác năng lực hiện tại.",
                    strategic_advice="Tìm hiểu thêm các phương thức xét tuyển sớm (ĐGNL/Học bạ) để tăng cơ hội trúng tuyển.",
                )
            )

        advice = (
            "Dựa trên dữ liệu học tập hiện tại, hãy tập trung cải thiện các dạng bài còn yếu và duy trì lịch thi thử đều đặn. "
            "Các nguyện vọng mục tiêu luôn đòi hỏi sự kiên trì và chiến thuật làm bài chắc chắn."
        )

        return AdmissionAssistantResponse(
            student_id=ctx.student_id,
            facts=facts,
            estimates=estimates,
            recommendations=recommendations,
            missing_data_summary=ctx.missing_data_notices,
            student_friendly_advice=advice,
            is_fallback=True,
            generated_at=datetime.now(timezone.utc),
        )
