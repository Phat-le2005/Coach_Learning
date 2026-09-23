from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.classes.analytics_schemas import (
    AlertRuleCode,
    AlertSeverity,
    ChapterProgressRead,
    ClassroomAlertsRead,
    ClassroomAnalyticsDashboardRead,
    ClassroomHeatmapRead,
    HeatmapCellRead,
    HeatmapColumnRead,
    HeatmapRowRead,
    HeatmapView,
    InterventionAlertRead,
    MasteryLevel,
    MetricItemRead,
    MisconceptionMetricRead,
    RecentTrendsRead,
    StudentAttentionRead,
    StudyCompletionRead,
    SubjectProgressRead,
    TopicProgressRead,
)
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import (
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.practice.models import (
    PracticeSession,
    PracticeSessionConcept,
    PracticeSessionProblemType,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.planning.study_models import StudyPlan, StudyPlanStatus, StudyTask, StudyTaskStatus
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import User

logger = logging.getLogger(__name__)


class ClassAnalyticsService:
    """Deterministic analytics engine for teachers and classrooms.

    Strict Architectural Guarantees:
    - 100% Deterministic Metrics: Pure Python/SQL aggregations without AI estimation.
    - Teacher Isolation: Teachers can ONLY access classrooms they are assigned to or own.
    - Synthetic Data Filtering: Automatically excludes synthetic students in production analytics by default.
    - Multi-view Heatmaps: Supports ProblemType, Concept, Topic, and Chapter views.
    - Comprehensive Intervention Alerts: Flags 6 critical pedagogical risk patterns.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    # --------------------------------------------------------------------------
    # Security & Classroom Scope Validation
    # --------------------------------------------------------------------------

    def require_teacher_access(
        self,
        teacher_user_id: UUID,
        classroom_id: UUID,
    ) -> tuple[TeacherProfile, Classroom]:
        """Verify that teacher exists and has access to the target classroom."""
        teacher = self.session.scalar(
            select(TeacherProfile).where(TeacherProfile.user_id == teacher_user_id)
        )
        if teacher is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Teacher profile not found.")

        classroom = self.session.get(Classroom, classroom_id)
        if classroom is None:
            raise ApplicationError(404, "CLASSROOM_NOT_FOUND", "Classroom not found.")

        # Check authorization via assignment or ownership
        has_assignment = self.session.scalar(
            select(TeacherClassroom.teacher_id).where(
                TeacherClassroom.teacher_id == teacher.id,
                TeacherClassroom.classroom_id == classroom_id,
            ).limit(1)
        )
        if has_assignment is None and classroom.created_by != teacher_user_id:
            raise ApplicationError(403, "FORBIDDEN", "Teacher does not have access to this classroom.")

        return teacher, classroom

    def get_enrolled_students(
        self,
        classroom_id: UUID,
        include_synthetic: bool = False,
    ) -> list[tuple[StudentProfile, str]]:
        """Retrieve active students and their names, with synthetic data filtering."""
        query = (
            select(StudentProfile, User.full_name, User.email)
            .join(StudentEnrollment, StudentEnrollment.student_id == StudentProfile.id)
            .join(User, User.id == StudentProfile.user_id)
            .where(
                StudentEnrollment.classroom_id == classroom_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            )
            .order_by(User.full_name.asc(), User.email.asc())
        )

        if not include_synthetic:
            query = query.where(StudentProfile.is_synthetic.is_(False))

        rows = self.session.execute(query).all()
        result: list[tuple[StudentProfile, str]] = []
        for profile, full_name, email in rows:
            name = full_name or email or f"Học sinh {str(profile.id)[:6]}"
            result.append((profile, name))
        return result

    # --------------------------------------------------------------------------
    # 1. Dashboard Analytics
    # --------------------------------------------------------------------------

    def get_classroom_dashboard(
        self,
        teacher_user_id: UUID,
        classroom_id: UUID,
        include_synthetic: bool = False,
    ) -> ClassroomAnalyticsDashboardRead:
        """Calculate comprehensive deterministic metrics for the teacher's classroom dashboard."""
        _, classroom = self.require_teacher_access(teacher_user_id, classroom_id)
        students_info = self.get_enrolled_students(classroom_id, include_synthetic)
        student_count = len(students_info)

        if student_count == 0:
            return ClassroomAnalyticsDashboardRead(
                classroom_id=classroom.id,
                classroom_name=classroom.name,
                student_count=0,
                subject_progress=[],
                chapter_progress=[],
                topic_progress=[],
                strong_problem_types=[],
                weak_problem_types=[],
                strong_concepts=[],
                weak_concepts=[],
                common_misconceptions=[],
                recent_trends=RecentTrendsRead(
                    total_attempts_past_7_days=0,
                    recent_average_score=0.0,
                    previous_average_score=None,
                    trend_direction="STABLE",
                ),
                study_completion=StudyCompletionRead(
                    assigned_tasks_count=0,
                    completed_tasks_count=0,
                    completion_rate=100.0,
                ),
                students_needing_attention=[],
            )

        student_ids = [s.id for s, _ in students_info]

        # 1. Subject, Chapter, and Topic progress
        # Query curriculum entities matching classroom's grade level
        subjects = list(
            self.session.scalars(
                select(Subject).where(Subject.grade_level == classroom.grade_level)
            ).all()
        )
        if not subjects:
            subjects = list(self.session.scalars(select(Subject).limit(3)).all())

        subject_progress_list: list[SubjectProgressRead] = []
        chapter_progress_list: list[ChapterProgressRead] = []
        topic_progress_list: list[TopicProgressRead] = []

        for sub in subjects:
            # Query ProblemTypes belonging to this subject
            pts = list(
                self.session.scalars(
                    select(ProblemType)
                    .join(Topic, Topic.id == ProblemType.topic_id)
                    .join(Chapter, Chapter.id == Topic.chapter_id)
                    .where(Chapter.subject_id == sub.id)
                ).all()
            )
            pt_ids = [pt.id for pt in pts]

            sub_score_avg = 0.0
            if pt_ids:
                avg_val = self.session.scalar(
                    select(func.avg(StudentProblemTypeMastery.mastery_score)).where(
                        StudentProblemTypeMastery.student_id.in_(student_ids),
                        StudentProblemTypeMastery.problem_type_id.in_(pt_ids),
                    )
                )
                if avg_val is not None:
                    sub_score_avg = round(float(avg_val), 2)

            subject_progress_list.append(
                SubjectProgressRead(
                    subject_id=sub.id,
                    subject_name=sub.name,
                    subject_code=sub.code,
                    average_mastery=sub_score_avg,
                    completion_percentage=round(sub_score_avg * 100.0, 1),
                )
            )

            # Chapters under subject
            chapters = list(
                self.session.scalars(
                    select(Chapter).where(Chapter.subject_id == sub.id).order_by(Chapter.order_index)
                ).all()
            )
            for chp in chapters:
                chp_pts = list(
                    self.session.scalars(
                        select(ProblemType.id)
                        .join(Topic, Topic.id == ProblemType.topic_id)
                        .where(Topic.chapter_id == chp.id)
                    ).all()
                )
                chp_avg = 0.0
                proficient_students = 0
                if chp_pts:
                    c_avg = self.session.scalar(
                        select(func.avg(StudentProblemTypeMastery.mastery_score)).where(
                            StudentProblemTypeMastery.student_id.in_(student_ids),
                            StudentProblemTypeMastery.problem_type_id.in_(chp_pts),
                        )
                    )
                    if c_avg is not None:
                        chp_avg = round(float(c_avg), 2)

                    # Count students with average chapter mastery >= 0.60
                    subq = (
                        select(
                            StudentProblemTypeMastery.student_id,
                            func.avg(StudentProblemTypeMastery.mastery_score).label("st_avg"),
                        )
                        .where(
                            StudentProblemTypeMastery.student_id.in_(student_ids),
                            StudentProblemTypeMastery.problem_type_id.in_(chp_pts),
                        )
                        .group_by(StudentProblemTypeMastery.student_id)
                    ).subquery()
                    proficient_students = self.session.scalar(
                        select(func.count()).where(subq.c.st_avg >= 0.60)
                    ) or 0

                chapter_progress_list.append(
                    ChapterProgressRead(
                        chapter_id=chp.id,
                        chapter_name=chp.name,
                        chapter_code=chp.code,
                        subject_name=sub.name,
                        average_mastery=chp_avg,
                        proficient_student_count=proficient_students,
                        total_student_count=student_count,
                    )
                )

                # Topics under chapter
                topics = list(
                    self.session.scalars(
                        select(Topic).where(Topic.chapter_id == chp.id).order_by(Topic.order_index)
                    ).all()
                )
                for top in topics:
                    top_pts = list(
                        self.session.scalars(
                            select(ProblemType.id).where(ProblemType.topic_id == top.id)
                        ).all()
                    )
                    top_avg = 0.0
                    if top_pts:
                        t_avg = self.session.scalar(
                            select(func.avg(StudentProblemTypeMastery.mastery_score)).where(
                                StudentProblemTypeMastery.student_id.in_(student_ids),
                                StudentProblemTypeMastery.problem_type_id.in_(top_pts),
                            )
                        )
                        if t_avg is not None:
                            top_avg = round(float(t_avg), 2)

                    topic_progress_list.append(
                        TopicProgressRead(
                            topic_id=top.id,
                            topic_name=top.name,
                            topic_code=top.code,
                            chapter_name=chp.name,
                            average_mastery=top_avg,
                        )
                    )

        # 2. Strong & Weak ProblemTypes across the classroom
        pt_mastery_rows = list(
            self.session.execute(
                select(
                    ProblemType.id,
                    ProblemType.name,
                    ProblemType.code,
                    func.avg(StudentProblemTypeMastery.mastery_score).label("avg_score"),
                    func.count(StudentProblemTypeMastery.student_id).label("cnt"),
                )
                .join(StudentProblemTypeMastery, StudentProblemTypeMastery.problem_type_id == ProblemType.id)
                .where(StudentProblemTypeMastery.student_id.in_(student_ids))
                .group_by(ProblemType.id, ProblemType.name, ProblemType.code)
            ).all()
        )

        strong_pts: list[MetricItemRead] = []
        weak_pts: list[MetricItemRead] = []

        if pt_mastery_rows:
            sorted_by_score = sorted(pt_mastery_rows, key=lambda r: float(r.avg_score), reverse=True)
            for r in sorted_by_score:
                item = MetricItemRead(
                    id=r.id,
                    name=r.name,
                    code=r.code,
                    average_score=round(float(r.avg_score), 2),
                    student_count=int(r.cnt),
                )
                if item.average_score >= 0.70 and len(strong_pts) < 5:
                    strong_pts.append(item)

            for r in reversed(sorted_by_score):
                item = MetricItemRead(
                    id=r.id,
                    name=r.name,
                    code=r.code,
                    average_score=round(float(r.avg_score), 2),
                    student_count=int(r.cnt),
                )
                if item.average_score < 0.50 and len(weak_pts) < 5:
                    weak_pts.append(item)

        # 3. Strong & Weak Concepts across the classroom
        concept_mastery_rows = list(
            self.session.execute(
                select(
                    Concept.id,
                    Concept.name,
                    Concept.code,
                    func.avg(StudentConceptMastery.mastery_score).label("avg_score"),
                    func.count(StudentConceptMastery.student_id).label("cnt"),
                )
                .join(StudentConceptMastery, StudentConceptMastery.concept_id == Concept.id)
                .where(StudentConceptMastery.student_id.in_(student_ids))
                .group_by(Concept.id, Concept.name, Concept.code)
            ).all()
        )

        strong_concepts: list[MetricItemRead] = []
        weak_concepts: list[MetricItemRead] = []

        if concept_mastery_rows:
            sorted_concepts = sorted(concept_mastery_rows, key=lambda r: float(r.avg_score), reverse=True)
            for r in sorted_concepts:
                item = MetricItemRead(
                    id=r.id,
                    name=r.name,
                    code=r.code,
                    average_score=round(float(r.avg_score), 2),
                    student_count=int(r.cnt),
                )
                if item.average_score >= 0.70 and len(strong_concepts) < 5:
                    strong_concepts.append(item)

            for r in reversed(sorted_concepts):
                item = MetricItemRead(
                    id=r.id,
                    name=r.name,
                    code=r.code,
                    average_score=round(float(r.avg_score), 2),
                    student_count=int(r.cnt),
                )
                if item.average_score < 0.50 and len(weak_concepts) < 5:
                    weak_concepts.append(item)

        # 4. Common Misconceptions
        students_by_id = {s.id: name for s, name in students_info}
        active_misconceptions = list(
            self.session.execute(
                select(StudentMisconception, MisconceptionDefinition)
                .join(
                    MisconceptionDefinition,
                    MisconceptionDefinition.id == StudentMisconception.misconception_definition_id,
                )
                .where(
                    StudentMisconception.student_id.in_(student_ids),
                    StudentMisconception.status.in_([
                        StudentMisconceptionStatus.CONFIRMED,
                        StudentMisconceptionStatus.SUSPECTED,
                    ]),
                )
            ).all()
        )

        misc_map: dict[UUID, tuple[MisconceptionDefinition, set[UUID]]] = {}
        for sm, md in active_misconceptions:
            if md.id not in misc_map:
                misc_map[md.id] = (md, set())
            misc_map[md.id][1].add(sm.student_id)

        common_misconceptions: list[MisconceptionMetricRead] = []
        sorted_misc = sorted(misc_map.values(), key=lambda pair: len(pair[1]), reverse=True)
        for md, affected_sids in sorted_misc[:5]:
            affected_names = [students_by_id[sid] for sid in affected_sids if sid in students_by_id]
            common_misconceptions.append(
                MisconceptionMetricRead(
                    definition_id=md.id,
                    code=md.code,
                    name=md.name,
                    affected_students_count=len(affected_sids),
                    affected_student_names=affected_names,
                )
            )

        # 5. Recent Activity Trends (7 days vs previous 7 days)
        now = datetime.now(timezone.utc)
        start_7d = now - timedelta(days=7)
        start_14d = now - timedelta(days=14)

        recent_attempts = list(
            self.session.scalars(
                select(QuestionAttempt.score).where(
                    QuestionAttempt.student_id.in_(student_ids),
                    QuestionAttempt.created_at >= start_7d,
                    QuestionAttempt.score.is_not(None),
                )
            ).all()
        )
        total_recent_attempts = len(recent_attempts)
        recent_avg = round(float(sum(recent_attempts) / len(recent_attempts)), 2) if recent_attempts else 0.0

        prev_attempts = list(
            self.session.scalars(
                select(QuestionAttempt.score).where(
                    QuestionAttempt.student_id.in_(student_ids),
                    QuestionAttempt.created_at >= start_14d,
                    QuestionAttempt.created_at < start_7d,
                    QuestionAttempt.score.is_not(None),
                )
            ).all()
        )
        prev_avg = round(float(sum(prev_attempts) / len(prev_attempts)), 2) if prev_attempts else None

        trend_dir = "STABLE"
        if prev_avg is not None and recent_attempts:
            if recent_avg > prev_avg + 0.05:
                trend_dir = "IMPROVING"
            elif recent_avg < prev_avg - 0.05:
                trend_dir = "DECLINING"

        recent_trends = RecentTrendsRead(
            total_attempts_past_7_days=total_recent_attempts,
            recent_average_score=recent_avg,
            previous_average_score=prev_avg,
            trend_direction=trend_dir,
        )

        # 6. Study Completion
        study_plans = list(
            self.session.scalars(
                select(StudyPlan.id).where(StudyPlan.student_id.in_(student_ids))
            ).all()
        )
        assigned_tasks = 0
        completed_tasks = 0
        if study_plans:
            assigned_tasks = self.session.scalar(
                select(func.count(StudyTask.id)).where(StudyTask.study_plan_id.in_(study_plans))
            ) or 0
            completed_tasks = self.session.scalar(
                select(func.count(StudyTask.id)).where(
                    StudyTask.study_plan_id.in_(study_plans),
                    StudyTask.status == StudyTaskStatus.COMPLETED,
                )
            ) or 0

        comp_rate = round((completed_tasks / assigned_tasks * 100.0), 1) if assigned_tasks > 0 else 100.0
        study_completion = StudyCompletionRead(
            assigned_tasks_count=assigned_tasks,
            completed_tasks_count=completed_tasks,
            completion_rate=comp_rate,
        )

        # 7. Students Needing Attention (from Intervention Alerts)
        alerts_data = self.get_classroom_alerts(teacher_user_id, classroom_id, include_synthetic)
        alerts_by_student: dict[UUID, list[InterventionAlertRead]] = {}
        for a in alerts_data.alerts:
            alerts_by_student.setdefault(a.student_id, []).append(a)

        severity_rank = {
            AlertSeverity.CRITICAL: 4,
            AlertSeverity.HIGH: 3,
            AlertSeverity.MEDIUM: 2,
            AlertSeverity.LOW: 1,
        }

        students_attention: list[StudentAttentionRead] = []
        for sid, s_alerts in alerts_by_student.items():
            highest_sev = max(s_alerts, key=lambda a: severity_rank[a.severity]).severity
            codes = list({a.rule_code for a in s_alerts})
            summaries = [a.title for a in s_alerts]
            summary_str = "; ".join(summaries[:2])
            if len(summaries) > 2:
                summary_str += f" (và {len(summaries) - 2} vấn đề khác)"

            students_attention.append(
                StudentAttentionRead(
                    student_id=sid,
                    student_name=s_alerts[0].student_name,
                    alert_codes=codes,
                    highest_severity=highest_sev,
                    summary_reason=summary_str,
                    alert_count=len(s_alerts),
                )
            )

        # Sort attention list by severity then alert count
        students_attention.sort(key=lambda s: (severity_rank[s.highest_severity], s.alert_count), reverse=True)

        return ClassroomAnalyticsDashboardRead(
            classroom_id=classroom.id,
            classroom_name=classroom.name,
            student_count=student_count,
            subject_progress=subject_progress_list,
            chapter_progress=chapter_progress_list,
            topic_progress=topic_progress_list,
            strong_problem_types=strong_pts,
            weak_problem_types=weak_pts,
            strong_concepts=strong_concepts,
            weak_concepts=weak_concepts,
            common_misconceptions=common_misconceptions,
            recent_trends=recent_trends,
            study_completion=study_completion,
            students_needing_attention=students_attention,
        )

    # --------------------------------------------------------------------------
    # 2. Multi-view Heatmap Engine
    # --------------------------------------------------------------------------

    def get_classroom_heatmap(
        self,
        teacher_user_id: UUID,
        classroom_id: UUID,
        view: HeatmapView = HeatmapView.PROBLEM_TYPE,
        subject_id: UUID | None = None,
        include_synthetic: bool = False,
    ) -> ClassroomHeatmapRead:
        """Generate a 2D multi-view competency matrix (student x entity)."""
        _, classroom = self.require_teacher_access(teacher_user_id, classroom_id)
        students_info = self.get_enrolled_students(classroom_id, include_synthetic)
        student_ids = [s.id for s, _ in students_info]

        rows: list[HeatmapRowRead] = [
            HeatmapRowRead(student_id=s.id, student_name=name, is_synthetic=s.is_synthetic)
            for s, name in students_info
        ]

        columns: list[HeatmapColumnRead] = []
        cells: list[HeatmapCellRead] = []
        col_sum: dict[UUID, float] = {}
        col_cnt: dict[UUID, int] = {}
        row_sum: dict[UUID, float] = {}
        row_cnt: dict[UUID, int] = {}

        # --------------------------------------------------
        # View 1: ProblemType Heatmap
        # --------------------------------------------------
        if view == HeatmapView.PROBLEM_TYPE:
            query = (
                select(ProblemType, Topic.name.label("topic_name"))
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
            )
            if subject_id:
                query = query.where(Chapter.subject_id == subject_id)
            else:
                query = query.join(Subject, Subject.id == Chapter.subject_id).where(
                    Subject.grade_level == classroom.grade_level
                )
            pt_rows = list(self.session.execute(query.order_by(ProblemType.order_index)).all())

            for pt, tname in pt_rows:
                columns.append(
                    HeatmapColumnRead(
                        id=pt.id,
                        name=pt.name,
                        code=pt.code,
                        parent_name=tname,
                        order_index=pt.order_index,
                    )
                )

            # Query student problem type mastery
            if student_ids and columns:
                mastery_records = list(
                    self.session.scalars(
                        select(StudentProblemTypeMastery).where(
                            StudentProblemTypeMastery.student_id.in_(student_ids),
                            StudentProblemTypeMastery.problem_type_id.in_([c.id for c in columns]),
                        )
                    ).all()
                )
                m_lookup = {(m.student_id, m.problem_type_id): m for m in mastery_records}

                for row in rows:
                    for col in columns:
                        m = m_lookup.get((row.student_id, col.id))
                        score = round(m.mastery_score, 2) if m else None
                        attempts = m.attempt_count if m else 0
                        level = self._score_to_level(score)

                        cells.append(
                            HeatmapCellRead(
                                student_id=row.student_id,
                                column_id=col.id,
                                score=score,
                                level=level,
                                attempt_count=attempts,
                            )
                        )
                        if score is not None:
                            col_sum[col.id] = col_sum.get(col.id, 0.0) + score
                            col_cnt[col.id] = col_cnt.get(col.id, 0) + 1
                            row_sum[row.student_id] = row_sum.get(row.student_id, 0.0) + score
                            row_cnt[row.student_id] = row_cnt.get(row.student_id, 0) + 1

        # --------------------------------------------------
        # View 2: Concept Heatmap (for prerequisite diagnosis)
        # --------------------------------------------------
        elif view == HeatmapView.CONCEPT:
            query = select(Concept)
            if subject_id:
                query = query.where(Concept.subject_id == subject_id)
            else:
                query = query.join(Subject, Subject.id == Concept.subject_id).where(
                    Subject.grade_level == classroom.grade_level
                )
            concepts = list(self.session.scalars(query.order_by(Concept.order_index)).all())

            for c in concepts:
                columns.append(
                    HeatmapColumnRead(
                        id=c.id,
                        name=c.name,
                        code=c.code,
                        parent_name=None,
                        order_index=c.order_index,
                    )
                )

            if student_ids and columns:
                mastery_records = list(
                    self.session.scalars(
                        select(StudentConceptMastery).where(
                            StudentConceptMastery.student_id.in_(student_ids),
                            StudentConceptMastery.concept_id.in_([c.id for c in columns]),
                        )
                    ).all()
                )
                m_lookup = {(m.student_id, m.concept_id): m for m in mastery_records}

                for row in rows:
                    for col in columns:
                        m = m_lookup.get((row.student_id, col.id))
                        score = round(m.mastery_score, 2) if m else None
                        attempts = m.attempt_count if m else 0
                        level = self._score_to_level(score)

                        cells.append(
                            HeatmapCellRead(
                                student_id=row.student_id,
                                column_id=col.id,
                                score=score,
                                level=level,
                                attempt_count=attempts,
                            )
                        )
                        if score is not None:
                            col_sum[col.id] = col_sum.get(col.id, 0.0) + score
                            col_cnt[col.id] = col_cnt.get(col.id, 0) + 1
                            row_sum[row.student_id] = row_sum.get(row.student_id, 0.0) + score
                            row_cnt[row.student_id] = row_cnt.get(row.student_id, 0) + 1

        # --------------------------------------------------
        # View 3: Topic Aggregate Heatmap
        # --------------------------------------------------
        elif view == HeatmapView.TOPIC:
            query = select(Topic, Chapter.name.label("chp_name")).join(Chapter, Chapter.id == Topic.chapter_id)
            if subject_id:
                query = query.where(Chapter.subject_id == subject_id)
            else:
                query = query.join(Subject, Subject.id == Chapter.subject_id).where(
                    Subject.grade_level == classroom.grade_level
                )
            topic_rows = list(self.session.execute(query.order_by(Topic.order_index)).all())

            for top, cname in topic_rows:
                columns.append(
                    HeatmapColumnRead(
                        id=top.id,
                        name=top.name,
                        code=top.code,
                        parent_name=cname,
                        order_index=top.order_index,
                    )
                )

            if student_ids and columns:
                # Map Topic to its ProblemTypes
                pts = list(
                    self.session.execute(
                        select(ProblemType.id, ProblemType.topic_id).where(
                            ProblemType.topic_id.in_([c.id for c in columns])
                        )
                    ).all()
                )
                topic_pts: dict[UUID, list[UUID]] = {}
                for pt_id, top_id in pts:
                    topic_pts.setdefault(top_id, []).append(pt_id)

                all_pt_ids = [pt_id for pt_id, _ in pts]
                m_records = list(
                    self.session.scalars(
                        select(StudentProblemTypeMastery).where(
                            StudentProblemTypeMastery.student_id.in_(student_ids),
                            StudentProblemTypeMastery.problem_type_id.in_(all_pt_ids),
                        )
                    ).all()
                )
                m_lookup = {(m.student_id, m.problem_type_id): m for m in m_records}

                for row in rows:
                    for col in columns:
                        child_pts = topic_pts.get(col.id, [])
                        scores = []
                        total_att = 0
                        for pt_id in child_pts:
                            m = m_lookup.get((row.student_id, pt_id))
                            if m and m.mastery_score is not None:
                                scores.append(m.mastery_score)
                                total_att += m.attempt_count

                        avg_score = round(sum(scores) / len(scores), 2) if scores else None
                        level = self._score_to_level(avg_score)

                        cells.append(
                            HeatmapCellRead(
                                student_id=row.student_id,
                                column_id=col.id,
                                score=avg_score,
                                level=level,
                                attempt_count=total_att,
                            )
                        )
                        if avg_score is not None:
                            col_sum[col.id] = col_sum.get(col.id, 0.0) + avg_score
                            col_cnt[col.id] = col_cnt.get(col.id, 0) + 1
                            row_sum[row.student_id] = row_sum.get(row.student_id, 0.0) + avg_score
                            row_cnt[row.student_id] = row_cnt.get(row.student_id, 0) + 1

        # --------------------------------------------------
        # View 4: Chapter Aggregate Heatmap
        # --------------------------------------------------
        elif view == HeatmapView.CHAPTER:
            query = select(Chapter, Subject.name.label("sub_name")).join(Subject, Subject.id == Chapter.subject_id)
            if subject_id:
                query = query.where(Chapter.subject_id == subject_id)
            else:
                query = query.where(Subject.grade_level == classroom.grade_level)
            chp_rows = list(self.session.execute(query.order_by(Chapter.order_index)).all())

            for chp, sname in chp_rows:
                columns.append(
                    HeatmapColumnRead(
                        id=chp.id,
                        name=chp.name,
                        code=chp.code,
                        parent_name=sname,
                        order_index=chp.order_index,
                    )
                )

            if student_ids and columns:
                # Map Chapter to its ProblemTypes
                pts = list(
                    self.session.execute(
                        select(ProblemType.id, Chapter.id.label("chp_id"))
                        .join(Topic, Topic.id == ProblemType.topic_id)
                        .join(Chapter, Chapter.id == Topic.chapter_id)
                        .where(Chapter.id.in_([c.id for c in columns]))
                    ).all()
                )
                chapter_pts: dict[UUID, list[UUID]] = {}
                for pt_id, chp_id in pts:
                    chapter_pts.setdefault(chp_id, []).append(pt_id)

                all_pt_ids = [pt_id for pt_id, _ in pts]
                m_records = list(
                    self.session.scalars(
                        select(StudentProblemTypeMastery).where(
                            StudentProblemTypeMastery.student_id.in_(student_ids),
                            StudentProblemTypeMastery.problem_type_id.in_(all_pt_ids),
                        )
                    ).all()
                )
                m_lookup = {(m.student_id, m.problem_type_id): m for m in m_records}

                for row in rows:
                    for col in columns:
                        child_pts = chapter_pts.get(col.id, [])
                        scores = []
                        total_att = 0
                        for pt_id in child_pts:
                            m = m_lookup.get((row.student_id, pt_id))
                            if m and m.mastery_score is not None:
                                scores.append(m.mastery_score)
                                total_att += m.attempt_count

                        avg_score = round(sum(scores) / len(scores), 2) if scores else None
                        level = self._score_to_level(avg_score)

                        cells.append(
                            HeatmapCellRead(
                                student_id=row.student_id,
                                column_id=col.id,
                                score=avg_score,
                                level=level,
                                attempt_count=total_att,
                            )
                        )
                        if avg_score is not None:
                            col_sum[col.id] = col_sum.get(col.id, 0.0) + avg_score
                            col_cnt[col.id] = col_cnt.get(col.id, 0) + 1
                            row_sum[row.student_id] = row_sum.get(row.student_id, 0.0) + avg_score
                            row_cnt[row.student_id] = row_cnt.get(row.student_id, 0) + 1

        # Calculate averages
        column_averages = {
            str(cid): round(col_sum[cid] / col_cnt[cid], 2)
            for cid in col_sum
            if col_cnt.get(cid, 0) > 0
        }
        row_averages = {
            str(sid): round(row_sum[sid] / row_cnt[sid], 2)
            for sid in row_sum
            if row_cnt.get(sid, 0) > 0
        }

        return ClassroomHeatmapRead(
            classroom_id=classroom.id,
            view=view,
            columns=columns,
            rows=rows,
            cells=cells,
            column_averages=column_averages,
            row_averages=row_averages,
        )

    # --------------------------------------------------------------------------
    # 3. Deterministic Intervention Rules Engine
    # --------------------------------------------------------------------------

    def get_classroom_alerts(
        self,
        teacher_user_id: UUID,
        classroom_id: UUID,
        include_synthetic: bool = False,
    ) -> ClassroomAlertsRead:
        """Run all 6 deterministic intervention rules against enrolled students."""
        _, classroom = self.require_teacher_access(teacher_user_id, classroom_id)
        students_info = self.get_enrolled_students(classroom_id, include_synthetic)
        student_count = len(students_info)

        if student_count == 0:
            return ClassroomAlertsRead(
                classroom_id=classroom.id,
                total_alerts=0,
                critical_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
                alerts=[],
            )

        student_ids = [s.id for s, _ in students_info]
        students_by_id = {s.id: name for s, name in students_info}

        alerts: list[InterventionAlertRead] = []
        now = datetime.now(timezone.utc)

        # --------------------------------------------------
        # Rule 1: LOW_PROBLEM_TYPE_MASTERY
        # Mastery < 0.40 and attempts >= 3
        # --------------------------------------------------
        low_pt_rows = list(
            self.session.execute(
                select(StudentProblemTypeMastery, ProblemType.name)
                .join(ProblemType, ProblemType.id == StudentProblemTypeMastery.problem_type_id)
                .where(
                    StudentProblemTypeMastery.student_id.in_(student_ids),
                    StudentProblemTypeMastery.mastery_score < 0.40,
                    StudentProblemTypeMastery.attempt_count >= 3,
                )
            ).all()
        )
        for m, pt_name in low_pt_rows:
            sname = students_by_id.get(m.student_id, "Học sinh")
            sev = AlertSeverity.CRITICAL if m.mastery_score < 0.25 else AlertSeverity.HIGH
            alerts.append(
                InterventionAlertRead(
                    id=f"low-pt-{m.student_id}-{m.problem_type_id}",
                    student_id=m.student_id,
                    student_name=sname,
                    rule_code=AlertRuleCode.LOW_PROBLEM_TYPE_MASTERY,
                    severity=sev,
                    title=f"Khó khăn kéo dài ở dạng bài [{pt_name}]",
                    message=(
                        f"Học sinh {sname} có điểm thành thạo rất thấp ({m.mastery_score:.2f}) "
                        f"sau {m.attempt_count} lượt làm bài ở dạng [{pt_name}]."
                    ),
                    target_id=m.problem_type_id,
                    target_name=pt_name,
                    metric_value=round(m.mastery_score, 2),
                    detected_at=now,
                    suggested_action="Giao bài tập bổ trợ nhận biết hoặc phân công học sinh hỗ trợ 1-1.",
                )
            )

        # --------------------------------------------------
        # Rule 2: PREREQUISITE_GAP
        # Concept mastery < 0.50 for a concept marked as PREREQUISITE
        # --------------------------------------------------
        prereq_weak_rows = list(
            self.session.execute(
                select(StudentConceptMastery, Concept.name)
                .join(Concept, Concept.id == StudentConceptMastery.concept_id)
                .join(ConceptRelation, ConceptRelation.source_concept_id == Concept.id)
                .where(
                    StudentConceptMastery.student_id.in_(student_ids),
                    StudentConceptMastery.mastery_score < 0.50,
                    ConceptRelation.relation_type == RelationType.PREREQUISITE,
                )
                .distinct()
            ).all()
        )
        for cm, cname in prereq_weak_rows:
            sname = students_by_id.get(cm.student_id, "Học sinh")
            alerts.append(
                InterventionAlertRead(
                    id=f"prereq-gap-{cm.student_id}-{cm.concept_id}",
                    student_id=cm.student_id,
                    student_name=sname,
                    rule_code=AlertRuleCode.PREREQUISITE_GAP,
                    severity=AlertSeverity.HIGH,
                    title=f"Hổng kiến thức tiên quyết [{cname}]",
                    message=(
                        f"Học sinh {sname} bị hổng khái niệm tiên quyết [{cname}] "
                        f"(điểm thành thạo: {cm.mastery_score:.2f} < 0.50), "
                        f"đe dọa trực tiếp khả năng tiếp thu các dạng bài liên quan."
                    ),
                    target_id=cm.concept_id,
                    target_name=cname,
                    metric_value=round(cm.mastery_score, 2),
                    detected_at=now,
                    suggested_action="Khởi động phiên khắc phục (Repair Session) tập trung vào khái niệm này.",
                )
            )

        # --------------------------------------------------
        # Rule 3: PERSISTENT_MISCONCEPTION
        # Status CONFIRMED or occurrence_count >= 2
        # --------------------------------------------------
        misc_rows = list(
            self.session.execute(
                select(StudentMisconception, MisconceptionDefinition.name)
                .join(
                    MisconceptionDefinition,
                    MisconceptionDefinition.id == StudentMisconception.misconception_definition_id,
                )
                .where(
                    StudentMisconception.student_id.in_(student_ids),
                    StudentMisconception.status != StudentMisconceptionStatus.RESOLVED,
                    (
                        (StudentMisconception.status == StudentMisconceptionStatus.CONFIRMED)
                        | (StudentMisconception.occurrence_count >= 2)
                    ),
                )
            ).all()
        )
        for sm, mname in misc_rows:
            sname = students_by_id.get(sm.student_id, "Học sinh")
            alerts.append(
                InterventionAlertRead(
                    id=f"misc-{sm.student_id}-{sm.misconception_definition_id}",
                    student_id=sm.student_id,
                    student_name=sname,
                    rule_code=AlertRuleCode.PERSISTENT_MISCONCEPTION,
                    severity=AlertSeverity.HIGH,
                    title=f"Lỗi sai hiểu lầm cố định [{mname}]",
                    message=(
                        f"Học sinh {sname} lặp lại lỗi sai hiểu lầm [{mname}] "
                        f"({sm.occurrence_count} lần ghi nhận, độ tin cậy: {sm.confidence:.2f})."
                    ),
                    target_id=sm.misconception_definition_id,
                    target_name=mname,
                    metric_value=round(sm.confidence, 2),
                    detected_at=now,
                    suggested_action="Chỉ rõ bẫy sai lầm này trong bài giảng hoặc hướng dẫn học sinh xem tóm tắt lý thuyết.",
                )
            )

        # --------------------------------------------------
        # Rule 4: FAILED_REPAIR
        # >= 3 repair sessions targeting the same ProblemType or Concept that failed
        # (average session score < 0.70 or last attempt incorrect)
        # --------------------------------------------------
        repair_sessions = list(
            self.session.scalars(
                select(PracticeSession).where(
                    PracticeSession.student_id.in_(student_ids),
                    PracticeSession.session_type == PracticeSessionType.REPAIR,
                )
            ).all()
        )
        # Group repair sessions by (student_id, target_problem_type_id or target_concept_id)
        repairs_by_target: dict[tuple[UUID, UUID], list[PracticeSession]] = {}
        for ps in repair_sessions:
            pt_link = self.session.scalar(
                select(PracticeSessionProblemType.problem_type_id).where(
                    PracticeSessionProblemType.practice_session_id == ps.id
                ).limit(1)
            )
            c_link = self.session.scalar(
                select(PracticeSessionConcept.concept_id).where(
                    PracticeSessionConcept.practice_session_id == ps.id
                ).limit(1)
            )
            target_id = pt_link or c_link
            if target_id:
                repairs_by_target.setdefault((ps.student_id, target_id), []).append(ps)

        for (sid, tid), sessions in repairs_by_target.items():
            if len(sessions) >= 3:
                # Check how many sessions were unsuccessful
                unsuccessful_count = 0
                for ps in sessions:
                    attempts = list(
                        self.session.scalars(
                            select(QuestionAttempt)
                            .where(QuestionAttempt.practice_session_id == ps.id)
                            .order_by(QuestionAttempt.attempt_number.asc())
                        ).all()
                    )
                    if not attempts:
                        unsuccessful_count += 1
                        continue

                    avg_score = sum(a.score or 0.0 for a in attempts) / len(attempts)
                    last_correct = attempts[-1].is_correct is True
                    if avg_score < 0.70 or not last_correct:
                        unsuccessful_count += 1

                if unsuccessful_count >= 3:
                    sname = students_by_id.get(sid, "Học sinh")
                    # Try to resolve target name
                    target_name = "Nội dung cần sửa"
                    pt = self.session.get(ProblemType, tid)
                    if pt:
                        target_name = pt.name
                    else:
                        c = self.session.get(Concept, tid)
                        if c:
                            target_name = c.name

                    alerts.append(
                        InterventionAlertRead(
                            id=f"failed-repair-{sid}-{tid}",
                            student_id=sid,
                            student_name=sname,
                            rule_code=AlertRuleCode.FAILED_REPAIR,
                            severity=AlertSeverity.CRITICAL,
                            title=f"Thất bại liên tiếp sau 3 phiên sửa lỗi ở [{target_name}]",
                            message=(
                                f"Học sinh {sname} đã hoàn thành {unsuccessful_count} phiên khắc phục lỗ hổng "
                                f"ở [{target_name}] nhưng đều chưa đạt chuẩn đầu ra."
                            ),
                            target_id=tid,
                            target_name=target_name,
                            metric_value=float(unsuccessful_count),
                            detected_at=now,
                            suggested_action="Học sinh không thể tự sửa lỗi, giáo viên cần trực tiếp kèm cặp 1-1.",
                        )
                    )

        # --------------------------------------------------
        # Rule 5: DECLINING_PERFORMANCE
        # Last 3 attempts average dropped >= 20% compared to previous 3 attempts
        # (Requires at least 6 attempts)
        # --------------------------------------------------
        for profile, sname in students_info:
            sid = profile.id
            attempts = list(
                self.session.scalars(
                    select(QuestionAttempt)
                    .where(
                        QuestionAttempt.student_id == sid,
                        QuestionAttempt.score.is_not(None),
                    )
                    .order_by(QuestionAttempt.created_at.asc())
                ).all()
            )
            if len(attempts) >= 6:
                recent_3 = attempts[-3:]
                prev_3 = attempts[-6:-3]
                avg_recent = sum(a.score or 0.0 for a in recent_3) / 3.0
                avg_prev = sum(a.score or 0.0 for a in prev_3) / 3.0

                if avg_prev > 0.0 and (avg_prev - avg_recent) / avg_prev >= 0.20:
                    pct_drop = round(((avg_prev - avg_recent) / avg_prev) * 100, 1)
                    alerts.append(
                        InterventionAlertRead(
                            id=f"declining-{sid}",
                            student_id=sid,
                            student_name=sname,
                            rule_code=AlertRuleCode.DECLINING_PERFORMANCE,
                            severity=AlertSeverity.MEDIUM,
                            title=f"Điểm số sụt giảm đáng kể (-{pct_drop}%)",
                            message=(
                                f"Học sinh {sname} có dấu hiệu sa sút phong độ: điểm trung bình 3 lần gần nhất "
                                f"({avg_recent:.2f}) giảm {pct_drop}% so với chu kỳ trước đó ({avg_prev:.2f})."
                            ),
                            metric_value=pct_drop,
                            detected_at=now,
                            suggested_action="Kiểm tra mức độ tập trung, thời gian tự học hoặc rào cản tâm lý của học sinh.",
                        )
                    )

        # --------------------------------------------------
        # Rule 6: INACTIVE_STUDY
        # No attempts in >= 7 days OR StudyTask completion < 30% with >= 3 assigned
        # --------------------------------------------------
        seven_days_ago = now - timedelta(days=7)
        for profile, sname in students_info:
            sid = profile.id
            latest_attempt = self.session.scalar(
                select(QuestionAttempt.created_at)
                .where(QuestionAttempt.student_id == sid)
                .order_by(QuestionAttempt.created_at.desc())
                .limit(1)
            )
            is_inactive = False
            reason_txt = ""

            if latest_attempt is not None and latest_attempt.tzinfo is None:
                latest_attempt = latest_attempt.replace(tzinfo=timezone.utc)

            if latest_attempt is None or latest_attempt < seven_days_ago:
                is_inactive = True
                days_inactive = (now - latest_attempt).days if latest_attempt else 14
                reason_txt = f"không nộp bất kỳ bài tập nào trong {days_inactive} ngày qua"
            else:
                # Check task completion
                plan = self.session.scalar(
                    select(StudyPlan.id).where(
                        StudyPlan.student_id == sid,
                        StudyPlan.status == StudyPlanStatus.ACTIVE,
                    ).order_by(StudyPlan.created_at.desc()).limit(1)
                )
                if plan:
                    assigned = self.session.scalar(
                        select(func.count(StudyTask.id)).where(
                            StudyTask.study_plan_id == plan,
                            StudyTask.planned_date >= seven_days_ago.date(),
                        )
                    ) or 0
                    completed = self.session.scalar(
                        select(func.count(StudyTask.id)).where(
                            StudyTask.study_plan_id == plan,
                            StudyTask.planned_date >= seven_days_ago.date(),
                            StudyTask.status == StudyTaskStatus.COMPLETED,
                        )
                    ) or 0
                    if assigned >= 3 and (completed / assigned) < 0.30:
                        is_inactive = True
                        comp_pct = round((completed / assigned) * 100, 1)
                        reason_txt = f"chỉ hoàn thành {completed}/{assigned} nhiệm vụ ({comp_pct}%) trong 7 ngày qua"

            if is_inactive:
                alerts.append(
                    InterventionAlertRead(
                        id=f"inactive-{sid}",
                        student_id=sid,
                        student_name=sname,
                        rule_code=AlertRuleCode.INACTIVE_STUDY,
                        severity=AlertSeverity.HIGH,
                        title=f"Học sinh ngưng trệ việc học",
                        message=f"Học sinh {sname} {reason_txt}.",
                        detected_at=now,
                        suggested_action="Nhắc nhở học sinh vào làm bài hoặc thông báo cho phụ huynh.",
                    )
                )

        # Sort alerts by severity
        severity_rank = {
            AlertSeverity.CRITICAL: 4,
            AlertSeverity.HIGH: 3,
            AlertSeverity.MEDIUM: 2,
            AlertSeverity.LOW: 1,
        }
        alerts.sort(key=lambda a: severity_rank[a.severity], reverse=True)

        critical_c = sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL)
        high_c = sum(1 for a in alerts if a.severity == AlertSeverity.HIGH)
        med_c = sum(1 for a in alerts if a.severity == AlertSeverity.MEDIUM)
        low_c = sum(1 for a in alerts if a.severity == AlertSeverity.LOW)

        return ClassroomAlertsRead(
            classroom_id=classroom.id,
            total_alerts=len(alerts),
            critical_count=critical_c,
            high_count=high_c,
            medium_count=med_c,
            low_count=low_c,
            alerts=alerts,
        )

    # --------------------------------------------------------------------------
    # Private Helpers
    # --------------------------------------------------------------------------

    @staticmethod
    def _score_to_level(score: float | None) -> MasteryLevel:
        if score is None:
            return MasteryLevel.NOT_STARTED
        if score >= 0.80:
            return MasteryLevel.MASTERED
        if score >= 0.60:
            return MasteryLevel.PROFICIENT
        if score >= 0.40:
            return MasteryLevel.STRUGGLING
        return MasteryLevel.CRITICAL
