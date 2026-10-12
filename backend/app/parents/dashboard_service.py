from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assignments.models import Assignment, StudentAssignment, StudentAssignmentStatus
from app.attempts.models import StudentAttempt, StudySession
from app.classes.analytics_schemas import AlertRuleCode, AlertSeverity
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.parents.dashboard_schemas import (
    DailyStudyTimeItem,
    ParentChapterProgressRead,
    ParentExamTrendItem,
    ParentInterventionAlertRead,
    ParentMajorWeakAreaRead,
    ParentStudentProgressRead,
    ParentStudentSummaryRead,
    ParentStudyPlanCompletionRead,
    ParentSubjectProgressRead,
    ParentTopicProgressRead,
    ParentWeeklyDataRead,
)
from app.parents.models import ParentProfile, ParentStudentRelationship
from app.planning.study_models import StudyPlan, StudyPlanStatus, StudyTask, StudyTaskStatus
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType, QuestionAttempt
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import User

logger = logging.getLogger(__name__)

UtcClock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


DAY_NAMES = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


class ParentDashboardService:
    """Deterministic analytics and reporting service for parents.

    Strict Architectural Guarantees:
    - 100% Deterministic: No AI inference, pure data aggregation.
    - Strict Authorization: Access is permitted ONLY if ParentStudentRelationship exists and is_active=True.
    - High-level Pedagogical Insights: Major weak areas at ProblemType level ("Đang gặp khó khăn ở nhóm bài toán...").
    - Privacy & Safety: Zero private AI conversations, zero raw messages, zero peer comparison, no minor noisy errors.
    """

    def __init__(self, session: Session, *, clock: UtcClock | None = None) -> None:
        self.session = session
        self._clock = clock or utc_now

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("ParentDashboardService clock must return a timezone-aware datetime.")
        return value.astimezone(timezone.utc)

    # --------------------------------------------------------------------------
    # Security & Relationship Authorization
    # --------------------------------------------------------------------------

    def require_parent_profile(self, parent_user_id: UUID) -> ParentProfile:
        parent = self.session.scalar(
            select(ParentProfile).where(ParentProfile.user_id == parent_user_id)
        )
        if parent is None:
            raise ApplicationError(404, "PARENT_PROFILE_NOT_FOUND", "Parent profile was not found.")
        return parent

    def require_active_relationship(
        self, parent_id: UUID, student_id: UUID
    ) -> tuple[ParentStudentRelationship, StudentProfile, User]:
        rel = self.session.scalar(
            select(ParentStudentRelationship).where(
                ParentStudentRelationship.parent_id == parent_id,
                ParentStudentRelationship.student_id == student_id,
            )
        )
        if rel is None:
            raise ApplicationError(
                403,
                "NOT_LINKED_TO_STUDENT",
                "You do not have permission to view this student's data.",
            )
        if not rel.is_active:
            raise ApplicationError(
                403,
                "RELATIONSHIP_INACTIVE",
                "Parent-student relationship is currently inactive.",
            )

        student = self.session.get(StudentProfile, student_id)
        if student is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile not found.")

        user = self.session.get(User, student.user_id)
        if user is None:
            raise ApplicationError(404, "USER_NOT_FOUND", "Student user record not found.")

        return rel, student, user

    # --------------------------------------------------------------------------
    # 1. Linked Students Overview
    # --------------------------------------------------------------------------

    def get_linked_students(self, parent_user_id: UUID) -> list[ParentStudentSummaryRead]:
        parent = self.require_parent_profile(parent_user_id)

        rows = list(
            self.session.execute(
                select(ParentStudentRelationship, StudentProfile, User)
                .join(StudentProfile, StudentProfile.id == ParentStudentRelationship.student_id)
                .join(User, User.id == StudentProfile.user_id)
                .where(
                    ParentStudentRelationship.parent_id == parent.id,
                    ParentStudentRelationship.is_active.is_(True),
                )
                .order_by(User.full_name)
            ).all()
        )

        summaries: list[ParentStudentSummaryRead] = []
        now = self._now()
        week_start = now - timedelta(days=7)

        for rel, student, user in rows:
            weekly_minutes = self._calculate_study_time_minutes(student.id, week_start, now)
            alerts = self._get_important_alerts_for_student(student.id)
            trend_status, _ = self._calculate_overall_trend(student.id, alerts)

            summaries.append(
                ParentStudentSummaryRead(
                    student_id=student.id,
                    student_name=user.full_name,
                    grade_level=student.grade_level,
                    relationship_type=rel.relationship_type,
                    school_name=student.school_name,
                    overall_learning_trend=trend_status,
                    weekly_study_time_minutes=weekly_minutes,
                    active_alerts_count=len(alerts),
                )
            )

        return summaries

    # --------------------------------------------------------------------------
    # 2. Comprehensive Student Progress
    # --------------------------------------------------------------------------

    def get_student_progress(
        self, parent_user_id: UUID, student_id: UUID
    ) -> ParentStudentProgressRead:
        parent = self.require_parent_profile(parent_user_id)
        rel, student, user = self.require_active_relationship(parent.id, student_id)

        # 1. Subject, Chapter, Topic Progress
        subj_prog, chap_prog, top_prog = self._calculate_curriculum_progress(student.id, student.grade_level)

        # 2. Major Weak Areas (ProblemType level with parent-friendly phrasing)
        major_weak_areas = self._calculate_major_weak_areas(student.id)

        # 3. Study Plan Completion
        study_plan_comp = self._calculate_study_plan_completion(student.id)

        # 4. Exam Trend
        exam_trend = self._calculate_exam_trend(student.id)

        # 5. Important Intervention Alerts
        alerts = self._get_important_alerts_for_student(student.id)

        # 6. Overall Learning Trend
        trend_status, trend_desc = self._calculate_overall_trend(student.id, alerts)

        return ParentStudentProgressRead(
            student_id=student.id,
            student_name=user.full_name,
            grade_level=student.grade_level,
            relationship_type=rel.relationship_type,
            subject_progress=subj_prog,
            chapter_progress=chap_prog,
            topic_progress=top_prog,
            major_weak_areas=major_weak_areas,
            study_plan_completion=study_plan_comp,
            exam_trend=exam_trend,
            important_intervention_alerts=alerts,
            overall_learning_trend=trend_status,
            trend_description=trend_desc,
        )

    # --------------------------------------------------------------------------
    # 3. Weekly Data & Daily Breakdown
    # --------------------------------------------------------------------------

    def get_student_weekly_data(
        self,
        parent_user_id: UUID,
        student_id: UUID,
        target_date: date | None = None,
    ) -> ParentWeeklyDataRead:
        parent = self.require_parent_profile(parent_user_id)
        _, student, user = self.require_active_relationship(parent.id, student_id)

        ref_date = target_date or self._now().date()
        # Monday as start of week
        start_of_week = ref_date - timedelta(days=ref_date.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        daily_items: list[DailyStudyTimeItem] = []
        total_week_minutes = 0

        for day_offset in range(7):
            current_day = start_of_week + timedelta(days=day_offset)
            day_start = datetime.combine(current_day, time.min, tzinfo=timezone.utc)
            day_end = datetime.combine(current_day, time.max, tzinfo=timezone.utc)

            minutes = self._calculate_study_time_minutes(student.id, day_start, day_end)
            attempts = self._count_questions_attempted(student.id, day_start, day_end)
            total_week_minutes += minutes

            daily_items.append(
                DailyStudyTimeItem(
                    date=current_day,
                    day_of_week=DAY_NAMES[day_offset],
                    study_time_minutes=minutes,
                    questions_attempted=attempts,
                )
            )

        # Weekly tasks completed
        tasks_sched = list(
            self.session.scalars(
                select(StudyTask)
                .join(StudyPlan, StudyPlan.id == StudyTask.study_plan_id)
                .where(
                    StudyPlan.student_id == student.id,
                    StudyTask.planned_date >= start_of_week,
                    StudyTask.planned_date <= end_of_week,
                )
            ).all()
        )
        tasks_total = len(tasks_sched)
        tasks_comp = sum(1 for t in tasks_sched if t.status == StudyTaskStatus.COMPLETED)
        comp_rate = round(tasks_comp / tasks_total, 2) if tasks_total > 0 else 1.0

        # Exam trend during this week (or recent)
        exam_trend = self._calculate_exam_trend(student.id, limit=5)

        # Parent summary statement
        if total_week_minutes > 0:
            summary_msg = (
                f"Tuần này con đã học tổng cộng {total_week_minutes} phút, "
                f"hoàn thành {tasks_comp}/{tasks_total} nhiệm vụ học tập theo kế hoạch."
            )
        else:
            summary_msg = "Tuần này con chưa ghi nhận thời gian học tập trên hệ thống."

        return ParentWeeklyDataRead(
            student_id=student.id,
            student_name=user.full_name,
            week_start_date=start_of_week,
            week_end_date=end_of_week,
            total_study_time_minutes=total_week_minutes,
            daily_study_time=daily_items,
            tasks_completed_this_week=tasks_comp,
            tasks_total_this_week=tasks_total,
            weekly_completion_rate=comp_rate,
            exam_trend=exam_trend,
            overall_weekly_summary=summary_msg,
        )

    # --------------------------------------------------------------------------
    # Internal Deterministic Calculations
    # --------------------------------------------------------------------------

    @staticmethod
    def _aware(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    def _calculate_study_time_minutes(
        self, student_id: UUID, start_time: datetime, end_time: datetime
    ) -> int:
        """Calculate total study time in minutes from StudySessions, PracticeSessions, and attempts."""
        total_seconds = 0.0

        # 1. Study Sessions
        study_sessions = list(
            self.session.scalars(
                select(StudySession).where(
                    StudySession.student_id == student_id,
                    StudySession.started_at >= start_time,
                    StudySession.started_at <= end_time,
                )
            ).all()
        )
        for s in study_sessions:
            s_end = self._aware(s.ended_at)
            s_start = self._aware(s.started_at)
            if s_end and s_start and s_end > s_start:
                total_seconds += (s_end - s_start).total_seconds()

        # 2. Practice Sessions
        practice_sessions = list(
            self.session.scalars(
                select(PracticeSession).where(
                    PracticeSession.student_id == student_id,
                    PracticeSession.started_at >= start_time,
                    PracticeSession.started_at <= end_time,
                    PracticeSession.completed_at.isnot(None),
                )
            ).all()
        )
        for p in practice_sessions:
            p_comp = self._aware(p.completed_at)
            p_start = self._aware(p.started_at)
            if p_comp and p_start and p_comp > p_start:
                total_seconds += (p_comp - p_start).total_seconds()

        # 3. If no session durations recorded, approximate from QuestionAttempt response times
        if total_seconds == 0.0:
            qa_seconds = self.session.scalar(
                select(func.coalesce(func.sum(QuestionAttempt.response_time_seconds), 0)).where(
                    QuestionAttempt.student_id == student_id,
                    QuestionAttempt.created_at >= start_time,
                    QuestionAttempt.created_at <= end_time,
                )
            )
            sa_seconds = self.session.scalar(
                select(func.coalesce(func.sum(StudentAttempt.response_time_ms), 0)).where(
                    StudentAttempt.student_id == student_id,
                    StudentAttempt.attempted_at >= start_time,
                    StudentAttempt.attempted_at <= end_time,
                )
            )
            total_seconds = float(qa_seconds or 0) + float((sa_seconds or 0) / 1000.0)

        return int(round(total_seconds / 60.0))

    def _count_questions_attempted(
        self, student_id: UUID, start_time: datetime, end_time: datetime
    ) -> int:
        qa_cnt = self.session.scalar(
            select(func.count(QuestionAttempt.id)).where(
                QuestionAttempt.student_id == student_id,
                QuestionAttempt.created_at >= start_time,
                QuestionAttempt.created_at <= end_time,
            )
        ) or 0
        sa_cnt = self.session.scalar(
            select(func.count(StudentAttempt.id)).where(
                StudentAttempt.student_id == student_id,
                StudentAttempt.attempted_at >= start_time,
                StudentAttempt.attempted_at <= end_time,
            )
        ) or 0
        return qa_cnt + sa_cnt

    def _calculate_curriculum_progress(
        self, student_id: UUID, grade_level: int
    ) -> tuple[
        list[ParentSubjectProgressRead],
        list[ParentChapterProgressRead],
        list[ParentTopicProgressRead],
    ]:
        subjects = list(
            self.session.scalars(
                select(Subject).where(Subject.grade_level == grade_level).order_by(Subject.name)
            ).all()
        )
        if not subjects:
            subjects = list(self.session.scalars(select(Subject).order_by(Subject.name)).all())

        subj_progress_list: list[ParentSubjectProgressRead] = []
        chap_progress_list: list[ParentChapterProgressRead] = []
        top_progress_list: list[ParentTopicProgressRead] = []

        for subj in subjects:
            # Query chapters & topics
            chapters = list(
                self.session.scalars(
                    select(Chapter).where(Chapter.subject_id == subj.id).order_by(Chapter.order_index)
                ).all()
            )
            subj_scores: list[float] = []
            total_topics_count = 0
            completed_topics_count = 0

            for chap in chapters:
                topics = list(
                    self.session.scalars(
                        select(Topic).where(Topic.chapter_id == chap.id).order_by(Topic.order_index)
                    ).all()
                )
                chap_scores: list[float] = []

                for top in topics:
                    total_topics_count += 1
                    # Problem types for this topic
                    pts = list(
                        self.session.scalars(
                            select(ProblemType).where(ProblemType.topic_id == top.id)
                        ).all()
                    )
                    if pts:
                        pt_ids = [pt.id for pt in pts]
                        m_scores = list(
                            self.session.scalars(
                                select(StudentProblemTypeMastery.mastery_score).where(
                                    StudentProblemTypeMastery.student_id == student_id,
                                    StudentProblemTypeMastery.problem_type_id.in_(pt_ids),
                                )
                            ).all()
                        )
                        top_mastery = (
                            round(sum(m_scores) / len(m_scores), 2) if m_scores else 0.0
                        )
                    else:
                        top_mastery = 0.0

                    if top_mastery >= 0.70:
                        completed_topics_count += 1

                    chap_scores.append(top_mastery)
                    top_progress_list.append(
                        ParentTopicProgressRead(
                            topic_id=top.id,
                            topic_name=top.name,
                            chapter_name=chap.name,
                            mastery_score=top_mastery,
                        )
                    )

                avg_chap_score = (
                    round(sum(chap_scores) / len(chap_scores), 2) if chap_scores else 0.0
                )
                subj_scores.append(avg_chap_score)

                status = (
                    "MASTERED"
                    if avg_chap_score >= 0.80
                    else ("IN_PROGRESS" if avg_chap_score >= 0.50 else "NEEDS_IMPROVEMENT")
                )
                chap_progress_list.append(
                    ParentChapterProgressRead(
                        chapter_id=chap.id,
                        chapter_name=chap.name,
                        subject_name=subj.name,
                        mastery_score=avg_chap_score,
                        status=status,
                    )
                )

            avg_subj_score = (
                round(sum(subj_scores) / len(subj_scores), 2) if subj_scores else 0.0
            )
            subj_progress_list.append(
                ParentSubjectProgressRead(
                    subject_id=subj.id,
                    subject_name=subj.name,
                    mastery_score=avg_subj_score,
                    completed_topics_count=completed_topics_count,
                    total_topics_count=total_topics_count,
                )
            )

        return subj_progress_list, chap_progress_list, top_progress_list

    def _calculate_major_weak_areas(self, student_id: UUID) -> list[ParentMajorWeakAreaRead]:
        """Find major weak problem types with parent-friendly phrasing."""
        weak_m = list(
            self.session.execute(
                select(StudentProblemTypeMastery, ProblemType, Subject)
                .join(ProblemType, ProblemType.id == StudentProblemTypeMastery.problem_type_id)
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .join(Subject, Subject.id == Chapter.subject_id)
                .where(
                    StudentProblemTypeMastery.student_id == student_id,
                    StudentProblemTypeMastery.mastery_score < 0.50,
                    StudentProblemTypeMastery.attempt_count >= 2,
                )
                .order_by(StudentProblemTypeMastery.mastery_score.asc())
                .limit(5)
            ).all()
        )

        results: list[ParentMajorWeakAreaRead] = []
        for m, pt, subj in weak_m:
            # Check for underlying weak prerequisite concept
            prereq_c = self.session.scalar(
                select(Concept.name)
                .join(ProblemTypeConcept, ProblemTypeConcept.concept_id == Concept.id)
                .join(StudentConceptMastery, StudentConceptMastery.concept_id == Concept.id)
                .where(
                    ProblemTypeConcept.problem_type_id == pt.id,
                    StudentConceptMastery.student_id == student_id,
                    StudentConceptMastery.mastery_score < 0.50,
                )
                .limit(1)
            )

            msg = f"Đang gặp khó khăn ở nhóm bài toán {pt.name}."

            results.append(
                ParentMajorWeakAreaRead(
                    problem_type_id=pt.id,
                    problem_type_name=pt.name,
                    subject_name=subj.name,
                    mastery_score=round(m.mastery_score, 2),
                    parent_friendly_message=msg,
                    related_concept_name=prereq_c,
                    attempt_count=m.attempt_count,
                )
            )

        return results

    def _calculate_study_plan_completion(self, student_id: UUID) -> ParentStudyPlanCompletionRead:
        tasks = list(
            self.session.scalars(
                select(StudyTask)
                .join(StudyPlan, StudyPlan.id == StudyTask.study_plan_id)
                .where(
                    StudyPlan.student_id == student_id,
                    StudyPlan.status == StudyPlanStatus.ACTIVE,
                )
            ).all()
        )
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == StudyTaskStatus.COMPLETED)
        rate = round(completed / total, 2) if total > 0 else 0.0

        return ParentStudyPlanCompletionRead(
            total_tasks=total,
            completed_tasks=completed,
            completion_rate=rate,
        )

    def _calculate_exam_trend(
        self, student_id: UUID, limit: int = 5
    ) -> list[ParentExamTrendItem]:
        """Aggregate recent assignment and exam scores on a 10.0 scale."""
        assignments = list(
            self.session.scalars(
                select(StudentAssignment)
                .join(Assignment, Assignment.id == StudentAssignment.assignment_id)
                .where(
                    StudentAssignment.student_id == student_id,
                    StudentAssignment.status.in_(
                        [StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED]
                    ),
                    StudentAssignment.score.isnot(None),
                )
                .order_by(StudentAssignment.submitted_at.desc())
                .limit(limit)
            ).all()
        )

        items: list[ParentExamTrendItem] = []
        for sa in reversed(assignments):
            items.append(
                ParentExamTrendItem(
                    title=sa.assignment.title,
                    date=sa.submitted_at or sa.assigned_at,
                    score=round(sa.score or 0.0, 1),
                    total_questions=sa.assignment.question_count,
                    assessment_type="ASSIGNMENT",
                    trend_direction="STABLE",
                )
            )

        # Compute trend directions
        for i in range(1, len(items)):
            diff = items[i].score - items[i - 1].score
            if diff >= 0.5:
                items[i].trend_direction = "UP"
            elif diff <= -0.5:
                items[i].trend_direction = "DOWN"
            else:
                items[i].trend_direction = "STABLE"

        return list(reversed(items))

    def _get_important_alerts_for_student(
        self, student_id: UUID
    ) -> list[ParentInterventionAlertRead]:
        """Generate high-level, parent-friendly intervention alerts without developer noise."""
        alerts: list[ParentInterventionAlertRead] = []

        # 1. LOW_PROBLEM_TYPE_MASTERY (Critical/High)
        low_pt = list(
            self.session.execute(
                select(StudentProblemTypeMastery, ProblemType.name)
                .join(ProblemType, ProblemType.id == StudentProblemTypeMastery.problem_type_id)
                .where(
                    StudentProblemTypeMastery.student_id == student_id,
                    StudentProblemTypeMastery.mastery_score < 0.40,
                    StudentProblemTypeMastery.attempt_count >= 3,
                )
                .limit(2)
            ).all()
        )
        for m, pt_name in low_pt:
            alerts.append(
                ParentInterventionAlertRead(
                    rule_code=AlertRuleCode.LOW_PROBLEM_TYPE_MASTERY,
                    severity="CRITICAL" if m.mastery_score < 0.25 else "HIGH",
                    title=f"Khó khăn ở dạng bài [{pt_name}]",
                    message=(
                        f"Con có điểm thành thạo khá thấp ({m.mastery_score:.2f}) "
                        f"ở dạng bài [{pt_name}] sau {m.attempt_count} lần luyện tập."
                    ),
                    suggested_action_for_parent=(
                        "Khích lệ con dành 15-20 phút xem lại các ví dụ mẫu và làm bài tập nhận biết cơ bản."
                    ),
                )
            )

        # 2. PREREQUISITE_GAP
        prereq_weak = list(
            self.session.execute(
                select(StudentConceptMastery, Concept.name)
                .join(Concept, Concept.id == StudentConceptMastery.concept_id)
                .join(ConceptRelation, ConceptRelation.source_concept_id == Concept.id)
                .where(
                    StudentConceptMastery.student_id == student_id,
                    StudentConceptMastery.mastery_score < 0.50,
                    ConceptRelation.relation_type == RelationType.PREREQUISITE,
                )
                .distinct()
                .limit(2)
            ).all()
        )
        for cm, cname in prereq_weak:
            alerts.append(
                ParentInterventionAlertRead(
                    rule_code=AlertRuleCode.PREREQUISITE_GAP,
                    severity="HIGH",
                    title=f"Hổng kiến thức nền tảng: [{cname}]",
                    message=(
                        f"Khái niệm nền tảng [{cname}] của con chưa vững ({cm.mastery_score:.2f}), "
                        f"ảnh hưởng trực tiếp đến khả năng tiếp thu các bài học mới."
                    ),
                    suggested_action_for_parent=(
                        "Động viên con ôn tập lại định nghĩa và các tính chất cơ bản của bài học này."
                    ),
                )
            )

        # 3. INACTIVE_STUDY (> 5 days without activity)
        last_attempt = self.session.scalar(
            select(QuestionAttempt.created_at)
            .where(QuestionAttempt.student_id == student_id)
            .order_by(QuestionAttempt.created_at.desc())
            .limit(1)
        )
        last_sa = self.session.scalar(
            select(StudentAttempt.attempted_at)
            .where(StudentAttempt.student_id == student_id)
            .order_by(StudentAttempt.attempted_at.desc())
            .limit(1)
        )
        dates = [self._aware(d) for d in [last_attempt, last_sa] if d is not None]
        if dates:
            latest = max(dates)
            if latest and self._now() - latest > timedelta(days=5):
                alerts.append(
                    ParentInterventionAlertRead(
                        rule_code=AlertRuleCode.INACTIVE_STUDY,
                        severity="MEDIUM",
                        title="Chưa có hoạt động học tập gần đây",
                        message="Hệ thống ghi nhận con chưa tham gia làm bài trong hơn 5 ngày qua.",
                        suggested_action_for_parent="Khích lệ con duy trì thời lượng học 20-30 phút mỗi ngày.",
                    )
                )

        return alerts

    def _calculate_overall_trend(
        self, student_id: UUID, alerts: list[ParentInterventionAlertRead]
    ) -> tuple[str, str]:
        critical_or_high = sum(1 for a in alerts if a.severity in ("CRITICAL", "HIGH"))

        # Average problem type mastery
        avg_m = self.session.scalar(
            select(func.avg(StudentProblemTypeMastery.mastery_score)).where(
                StudentProblemTypeMastery.student_id == student_id
            )
        )

        if critical_or_high >= 2:
            return (
                "NEEDS_ATTENTION",
                "Cần quan tâm: Con đang gặp khó khăn ở một số dạng bài và cần sự khích lệ, hỗ trợ từ gia đình và giáo viên.",
            )
        elif (avg_m is not None and avg_m >= 0.70) or critical_or_high == 0:
            return (
                "IMPROVING",
                "Tiến bộ tích cực: Con duy trì nhịp độ học tập tốt, hoàn thành nhiệm vụ đều đặn và tiếp thu bài hiệu quả.",
            )
        else:
            return (
                "STABLE",
                "Ổn định: Con đang duy trì phong độ học tập đều đặn, cần tiếp tục phát huy.",
            )
