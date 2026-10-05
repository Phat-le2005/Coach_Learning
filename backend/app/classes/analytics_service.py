from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment,
    AssignmentConcept,
    AssignmentLearningObjective,
    AssignmentMaterialItem,
    AssignmentMaterialItemConcept,
    AssignmentMaterialItemLearningOutcome,
    AssignmentMaterialItemProblemType,
    AssignmentProblemType,
    AssignmentStatus,
    StudentAssignment,
    StudentAssignmentStatus,
)
from app.classes.analytics_schemas import (
    ActiveTeachingPlanSummaryRead,
    AlertRuleCode,
    AlertSeverity,
    AssignmentAnalyticsRead,
    AssignmentCompletionRead,
    AssignmentStudentRowRead,
    AssignmentTargetPerformanceRead,
    ChapterProgressRead,
    ClassroomAlertsRead,
    ClassroomAnalyticsDashboardRead,
    ClassroomHeatmapRead,
    CurrentPlanMasteryRead,
    EvidenceSourceSummaryRead,
    HeatmapCellRead,
    HeatmapColumnRead,
    HeatmapRowRead,
    HeatmapView,
    InterventionAlertRead,
    LearningEvidenceSummaryRead,
    MasteryLevel,
    MetricItemRead,
    MisconceptionMetricRead,
    RecentTrendsRead,
    RepairSummaryRead,
    ReviewDueSummaryRead,
    StudentAssignmentSummaryRead,
    StudentAttentionRead,
    StudentLearningAnalyticsRead,
    StudentMasteryItemRead,
    StudyCompletionRead,
    SubjectProgressRead,
    TopicProgressRead,
    VerifiedRootCauseMetricRead,
)
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, ProblemTypeConcept, Topic
from app.knowledge_gap.models import (
    RootCauseDiagnosis,
    RootCauseDiagnosisType,
    RootCauseVerification,
    RootCauseVerificationOutcome,
    RootCauseVerificationStatus,
    RootCauseVerificationTarget,
    RootCauseVerificationTargetType,
)
from app.learning_evidence.models import (
    LearningEvidenceConcept,
    LearningEvidenceEvent,
    LearningEvidenceProblemType,
    LearningEvidenceSourceKind,
)
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import (
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.planning.study_models import StudyPlan, StudyPlanStatus, StudyTask, StudyTaskStatus
from app.practice.models import EvaluationStatus
from app.repair.models import AdaptiveRepairOutcome, AdaptiveRepairSession, AdaptiveRepairStatus
from app.review.models import ReviewSchedule
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import User

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ClassAnalyticsService:
    """Deterministic analytics engine for teachers and classrooms.

    Strict Architectural Guarantees:
    - 100% Deterministic Metrics: Pure Python/SQL aggregations without AI estimation.
    - Teacher Isolation: Teachers can ONLY access classrooms they are assigned to or own.
    - Synthetic Data Filtering: Automatically excludes synthetic students in production analytics by default.
    - Multi-view Heatmaps: Supports ProblemType, Concept, Topic, and Chapter views with confidence & coverage.
    - Modern Learning Evidence Loop: Real learning evidence, verified root causes, adaptive repair, and spaced reviews.
    - Read-only: Never mutates pedagogy, tasks, plans, or mastery records.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    # --------------------------------------------------------------------------
    # Security & Scope Validation
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

    def require_subject(self, subject_id: UUID | None) -> Subject | None:
        """Validate subject existence if subject_id is provided."""
        if subject_id is None:
            return None
        subject = self.session.get(Subject, subject_id)
        if subject is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject not found.")
        return subject

    def _get_classroom_subject_ids(self, classroom_id: UUID) -> set[UUID]:
        """Classroom subject scope = union of subject IDs explicitly attached to classroom-domain evidence.

        Student mastery/review/misconception state is global per student,
        so teacher analytics must derive allowed subjects from classroom-scoped records.
        """
        tp_subjects = set(
            self.session.scalars(
                select(TeachingPlan.subject_id).where(
                    TeachingPlan.classroom_id == classroom_id,
                    TeachingPlan.subject_id.is_not(None),
                )
            ).all()
        )
        asgn_subjects = set(
            self.session.scalars(
                select(Assignment.subject_id).where(
                    Assignment.classroom_id == classroom_id,
                    Assignment.subject_id.is_not(None),
                )
            ).all()
        )
        ev_subjects = set(
            self.session.scalars(
                select(LearningEvidenceEvent.subject_id).where(
                    LearningEvidenceEvent.classroom_id == classroom_id,
                    LearningEvidenceEvent.subject_id.is_not(None),
                )
            ).all()
        )
        rc_subjects = set(
            self.session.scalars(
                select(RootCauseDiagnosis.subject_id).where(
                    RootCauseDiagnosis.classroom_id == classroom_id,
                    RootCauseDiagnosis.subject_id.is_not(None),
                )
            ).all()
        )
        return tp_subjects | asgn_subjects | ev_subjects | rc_subjects

    def require_subject_in_classroom_scope(
        self,
        classroom_id: UUID,
        subject_id: UUID | None,
    ) -> Subject | None:
        """Validate that subject exists and belongs to the classroom's authorized scope."""
        if subject_id is None:
            return None
        subject = self.session.get(Subject, subject_id)
        if subject is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject not found.")
        classroom_subjects = self._get_classroom_subject_ids(classroom_id)
        if subject_id not in classroom_subjects:
            raise ApplicationError(
                409,
                "ANALYTICS_SUBJECT_NOT_IN_CLASSROOM_SCOPE",
                "Subject is not within this classroom's authorized scope.",
            )
        return subject

    def _resolve_classroom_subject_scope(
        self,
        classroom: Classroom,
        subject_id: UUID | None,
    ) -> set[UUID]:
        """Resolve effective subject IDs for classroom analytics."""
        if subject_id is not None:
            self.require_subject_in_classroom_scope(classroom.id, subject_id)
            return {subject_id}
        return self._get_classroom_subject_ids(classroom.id)

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
        subject_id: UUID | None = None,
        include_synthetic: bool = False,
    ) -> ClassroomAnalyticsDashboardRead:
        """Calculate comprehensive deterministic metrics for the teacher's classroom dashboard."""
        _, classroom = self.require_teacher_access(teacher_user_id, classroom_id)
        scoped_subject_ids = self._resolve_classroom_subject_scope(classroom, subject_id)

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
                    total_evidence_past_7_days=0,
                    scored_evidence_past_7_days=0,
                    recent_average_score=0.0,
                    previous_average_score=None,
                    correct_rate=None,
                    score_delta=None,
                    trend_direction="INSUFFICIENT_DATA",
                ),
                study_completion=StudyCompletionRead(
                    assigned_tasks_count=0,
                    completed_tasks_count=0,
                    completion_rate=100.0,
                ),
                students_needing_attention=[],
                evidence_sources=EvidenceSourceSummaryRead(),
                assignment_completion=AssignmentCompletionRead(),
                review_due=ReviewDueSummaryRead(),
                verified_root_causes=[],
                repair_summary=RepairSummaryRead(),
                evidence_summary=LearningEvidenceSummaryRead(),
                active_teaching_plan=None,
                current_plan_mastery=None,
            )

        student_ids = [s.id for s, _ in students_info]
        students_by_id = {s.id: name for s, name in students_info}
        now = datetime.now(timezone.utc)

        # --------------------------------------------------
        # 1. Subject, Chapter, and Topic Progress
        # --------------------------------------------------
        if scoped_subject_ids:
            subjects = list(
                self.session.scalars(
                    select(Subject)
                    .where(Subject.id.in_(list(scoped_subject_ids)))
                    .order_by(Subject.name.asc())
                ).all()
            )
        else:
            subjects = []

        subject_progress_list: list[SubjectProgressRead] = []
        chapter_progress_list: list[ChapterProgressRead] = []
        topic_progress_list: list[TopicProgressRead] = []

        for sub in subjects:
            if sub is None:
                continue
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
            observed_pairs = 0
            total_pairs = student_count * len(pt_ids)
            if pt_ids:
                avg_val = self.session.scalar(
                    select(func.avg(StudentProblemTypeMastery.mastery_score)).where(
                        StudentProblemTypeMastery.student_id.in_(student_ids),
                        StudentProblemTypeMastery.problem_type_id.in_(pt_ids),
                    )
                )
                if avg_val is not None:
                    sub_score_avg = round(float(avg_val), 2)

                observed_pairs = self.session.scalar(
                    select(func.count(StudentProblemTypeMastery.student_id)).where(
                        StudentProblemTypeMastery.student_id.in_(student_ids),
                        StudentProblemTypeMastery.problem_type_id.in_(pt_ids),
                    )
                ) or 0

            coverage_pct = (
                round(observed_pairs / total_pairs * 100.0, 1) if total_pairs > 0 else 0.0
            )

            subject_progress_list.append(
                SubjectProgressRead(
                    subject_id=sub.id,
                    subject_name=sub.name,
                    subject_code=sub.code,
                    average_mastery=sub_score_avg,
                    completion_percentage=round(sub_score_avg * 100.0, 1),
                    observed_student_target_pairs=observed_pairs,
                    total_possible_student_target_pairs=total_pairs,
                    coverage_percentage=coverage_pct,
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

        # --------------------------------------------------
        # 2. Strong & Weak ProblemTypes
        # --------------------------------------------------
        if scoped_subject_ids:
            pt_mastery_query = (
                select(
                    ProblemType.id,
                    ProblemType.name,
                    ProblemType.code,
                    func.avg(StudentProblemTypeMastery.mastery_score).label("avg_score"),
                    func.count(StudentProblemTypeMastery.student_id).label("cnt"),
                )
                .join(StudentProblemTypeMastery, StudentProblemTypeMastery.problem_type_id == ProblemType.id)
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .where(
                    StudentProblemTypeMastery.student_id.in_(student_ids),
                    Chapter.subject_id.in_(list(scoped_subject_ids)),
                )
            )
            pt_mastery_rows = list(
                self.session.execute(
                    pt_mastery_query.group_by(ProblemType.id, ProblemType.name, ProblemType.code)
                ).all()
            )
        else:
            pt_mastery_rows = []

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

        # --------------------------------------------------
        # 3. Strong & Weak Concepts
        # --------------------------------------------------
        if scoped_subject_ids:
            concept_mastery_query = (
                select(
                    Concept.id,
                    Concept.name,
                    Concept.code,
                    func.avg(StudentConceptMastery.mastery_score).label("avg_score"),
                    func.count(StudentConceptMastery.student_id).label("cnt"),
                )
                .join(StudentConceptMastery, StudentConceptMastery.concept_id == Concept.id)
                .where(
                    StudentConceptMastery.student_id.in_(student_ids),
                    Concept.subject_id.in_(list(scoped_subject_ids)),
                )
            )
            concept_mastery_rows = list(
                self.session.execute(
                    concept_mastery_query.group_by(Concept.id, Concept.name, Concept.code)
                ).all()
            )
        else:
            concept_mastery_rows = []

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

        # --------------------------------------------------
        # 4. Common Misconceptions
        # --------------------------------------------------
        if scoped_subject_ids:
            misc_query = (
                select(StudentMisconception, MisconceptionDefinition)
                .join(
                    MisconceptionDefinition,
                    MisconceptionDefinition.id == StudentMisconception.misconception_definition_id,
                )
                .join(
                    Concept, Concept.id == MisconceptionDefinition.concept_id
                )
                .where(
                    StudentMisconception.student_id.in_(student_ids),
                    StudentMisconception.status.in_([
                        StudentMisconceptionStatus.CONFIRMED,
                        StudentMisconceptionStatus.SUSPECTED,
                    ]),
                    Concept.subject_id.in_(list(scoped_subject_ids)),
                )
            )
            active_misconceptions = list(self.session.execute(misc_query).all())
        else:
            active_misconceptions = []

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

        # --------------------------------------------------
        # 5. Recent Activity Trends (Canonical: LearningEvidenceEvent)
        # --------------------------------------------------
        start_7d = now - timedelta(days=7)
        start_14d = now - timedelta(days=14)

        if scoped_subject_ids:
            base_ev_query = select(LearningEvidenceEvent).where(
                LearningEvidenceEvent.classroom_id == classroom.id,
                LearningEvidenceEvent.student_id.in_(student_ids),
                LearningEvidenceEvent.subject_id.in_(list(scoped_subject_ids)),
            )
            events_14d = list(
                self.session.scalars(
                    base_ev_query.where(LearningEvidenceEvent.occurred_at >= start_14d)
                ).all()
            )
        else:
            base_ev_query = None
            events_14d = []

        recent_events = [e for e in events_14d if _ensure_utc(e.occurred_at) is not None and _ensure_utc(e.occurred_at) >= start_7d]
        total_recent_events = len(recent_events)

        scored_recent = [
            e for e in recent_events
            if e.evaluation_status in (EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED)
            and e.score is not None
        ]
        scored_recent_count = len(scored_recent)
        recent_avg = (
            round(sum(e.score for e in scored_recent) / scored_recent_count, 2)
            if scored_recent_count > 0
            else 0.0
        )
        correct_recent_count = sum(1 for e in scored_recent if e.is_correct is True)
        recent_correct_rate = (
            round(correct_recent_count / scored_recent_count, 2)
            if scored_recent_count > 0
            else None
        )

        prev_events = [e for e in events_14d if _ensure_utc(e.occurred_at) is not None and _ensure_utc(e.occurred_at) < start_7d]
        scored_prev = [
            e for e in prev_events
            if e.evaluation_status in (EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED)
            and e.score is not None
        ]
        scored_prev_count = len(scored_prev)
        prev_avg = (
            round(sum(e.score for e in scored_prev) / scored_prev_count, 2)
            if scored_prev_count > 0
            else None
        )

        if scored_recent_count < 3 or scored_prev_count < 3 or prev_avg is None:
            trend_dir = "INSUFFICIENT_DATA"
            score_delta = None
        else:
            delta = round(recent_avg - prev_avg, 2)
            score_delta = delta
            if delta > 0.05:
                trend_dir = "IMPROVING"
            elif delta < -0.05:
                trend_dir = "DECLINING"
            else:
                trend_dir = "STABLE"

        recent_trends = RecentTrendsRead(
            total_attempts_past_7_days=total_recent_events,
            total_evidence_past_7_days=total_recent_events,
            scored_evidence_past_7_days=scored_recent_count,
            recent_average_score=recent_avg,
            previous_average_score=prev_avg,
            correct_rate=recent_correct_rate,
            score_delta=score_delta,
            trend_direction=trend_dir,
        )

        # --------------------------------------------------
        # 6. Evidence Sources Summary
        # --------------------------------------------------
        if scoped_subject_ids:
            practice_count = self.session.scalar(
                select(func.count(LearningEvidenceEvent.id)).where(
                    LearningEvidenceEvent.classroom_id == classroom.id,
                    LearningEvidenceEvent.student_id.in_(student_ids),
                    LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.PRACTICE_QUESTION,
                    LearningEvidenceEvent.subject_id.in_(list(scoped_subject_ids)),
                )
            ) or 0
            assignment_ev_count = self.session.scalar(
                select(func.count(LearningEvidenceEvent.id)).where(
                    LearningEvidenceEvent.classroom_id == classroom.id,
                    LearningEvidenceEvent.student_id.in_(student_ids),
                    LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION,
                    LearningEvidenceEvent.subject_id.in_(list(scoped_subject_ids)),
                )
            ) or 0
            material_ev_count = self.session.scalar(
                select(func.count(LearningEvidenceEvent.id)).where(
                    LearningEvidenceEvent.classroom_id == classroom.id,
                    LearningEvidenceEvent.student_id.in_(student_ids),
                    LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM,
                    LearningEvidenceEvent.subject_id.in_(list(scoped_subject_ids)),
                )
            ) or 0
        else:
            practice_count = 0
            assignment_ev_count = 0
            material_ev_count = 0

        evidence_sources = EvidenceSourceSummaryRead(
            practice_count=practice_count,
            assignment_question_count=assignment_ev_count,
            teacher_material_count=material_ev_count,
            total_count=practice_count + assignment_ev_count + material_ev_count,
        )

        # --------------------------------------------------
        # 7. Classroom Evidence Summary
        # --------------------------------------------------
        if scoped_subject_ids and base_ev_query is not None:
            all_classroom_events = list(
                self.session.scalars(base_ev_query).all()
            )
        else:
            all_classroom_events = []

        total_ev = len(all_classroom_events)
        scored_ev_list = [
            e for e in all_classroom_events
            if e.evaluation_status in (EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED)
            and e.score is not None
        ]
        scored_ev_count = len(scored_ev_list)
        correct_ev_count = sum(1 for e in scored_ev_list if e.is_correct is True)
        avg_ev_score = (
            round(sum(e.score for e in scored_ev_list) / scored_ev_count, 2)
            if scored_ev_count > 0
            else None
        )
        ev_correct_rate = (
            round(correct_ev_count / scored_ev_count, 2)
            if scored_ev_count > 0
            else None
        )

        resp_times = [
            e.response_time_seconds for e in all_classroom_events
            if e.response_time_seconds is not None and e.response_time_seconds > 0
        ]
        avg_resp_time = round(sum(resp_times) / len(resp_times), 1) if resp_times else None

        hint_counts = [e.hint_count for e in all_classroom_events]
        avg_hint_count = round(sum(hint_counts) / len(hint_counts), 1) if hint_counts else None

        needs_review_c = sum(
            1 for e in all_classroom_events
            if e.evaluation_status == EvaluationStatus.NEEDS_TEACHER_REVIEW
        )
        needs_eval_c = sum(
            1 for e in all_classroom_events
            if e.evaluation_status == EvaluationStatus.NEEDS_EVALUATION
        )

        evidence_summary = LearningEvidenceSummaryRead(
            total_events=total_ev,
            scored_events=scored_ev_count,
            correct_events=correct_ev_count,
            average_score=avg_ev_score,
            correct_rate=ev_correct_rate,
            average_response_time_seconds=avg_resp_time,
            average_hint_count=avg_hint_count,
            needs_teacher_review_count=needs_review_c,
            needs_evaluation_count=needs_eval_c,
        )

        # --------------------------------------------------
        # 8. Assignment Completion
        # --------------------------------------------------
        if scoped_subject_ids:
            asgn_query = select(Assignment).where(
                Assignment.classroom_id == classroom.id,
                Assignment.status.in_([AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED]),
                Assignment.subject_id.in_(list(scoped_subject_ids)),
            )
            published_assignments = list(self.session.scalars(asgn_query).all())
        else:
            published_assignments = []

        pub_asgn_ids = [a.id for a in published_assignments]
        pub_asgn_map = {a.id: a for a in published_assignments}

        student_assignments = []
        if pub_asgn_ids:
            student_assignments = list(
                self.session.scalars(
                    select(StudentAssignment).where(
                        StudentAssignment.assignment_id.in_(pub_asgn_ids),
                        StudentAssignment.student_id.in_(student_ids),
                    )
                ).all()
            )

        asgn_assigned = len(student_assignments)
        asgn_not_started = sum(1 for sa in student_assignments if sa.status == StudentAssignmentStatus.NOT_STARTED)
        asgn_in_prog = sum(1 for sa in student_assignments if sa.status == StudentAssignmentStatus.IN_PROGRESS)
        asgn_submitted = sum(1 for sa in student_assignments if sa.status == StudentAssignmentStatus.SUBMITTED)
        asgn_graded = sum(1 for sa in student_assignments if sa.status == StudentAssignmentStatus.GRADED)
        asgn_overdue = 0
        for sa in student_assignments:
            asgn = pub_asgn_map.get(sa.assignment_id)
            if (
                asgn
                and asgn.due_at is not None
                and _ensure_utc(asgn.due_at) < now
                and sa.status in (StudentAssignmentStatus.NOT_STARTED, StudentAssignmentStatus.IN_PROGRESS)
            ):
                asgn_overdue += 1

        asgn_completed = asgn_submitted + asgn_graded
        asgn_comp_rate = round(asgn_completed / asgn_assigned * 100.0, 1) if asgn_assigned > 0 else 0.0
        asgn_scores = [sa.score for sa in student_assignments if sa.score is not None]
        asgn_avg_score = round(sum(asgn_scores) / len(asgn_scores), 2) if asgn_scores else None

        assignment_completion = AssignmentCompletionRead(
            assignment_count=len(published_assignments),
            assigned_student_count=asgn_assigned,
            not_started_count=asgn_not_started,
            in_progress_count=asgn_in_prog,
            submitted_count=asgn_submitted,
            graded_count=asgn_graded,
            overdue_count=asgn_overdue,
            average_score=asgn_avg_score,
            completion_rate=asgn_comp_rate,
        )

        # --------------------------------------------------
        # 9. Review Due Summary
        # --------------------------------------------------
        if scoped_subject_ids:
            rs_query = (
                select(ReviewSchedule)
                .where(ReviewSchedule.student_id.in_(student_ids))
                .outerjoin(Concept, Concept.id == ReviewSchedule.concept_id)
                .outerjoin(ProblemType, ProblemType.id == ReviewSchedule.problem_type_id)
                .outerjoin(Topic, Topic.id == ProblemType.topic_id)
                .outerjoin(Chapter, Chapter.id == Topic.chapter_id)
                .where(
                    (Concept.subject_id.in_(list(scoped_subject_ids)))
                    | (Chapter.subject_id.in_(list(scoped_subject_ids)))
                )
            )
            all_schedules = list(self.session.scalars(rs_query).all())
        else:
            all_schedules = []

        due_now_schedules = [
            rs for rs in all_schedules
            if rs.next_review_at is not None and _ensure_utc(rs.next_review_at) <= now
        ]
        due_3d_schedules = [
            rs for rs in all_schedules
            if rs.next_review_at is not None and now < _ensure_utc(rs.next_review_at) <= now + timedelta(days=3)
        ]

        review_due = ReviewDueSummaryRead(
            due_now_count=len(due_now_schedules),
            due_next_3_days_count=len(due_3d_schedules),
            students_due_count=len({rs.student_id for rs in due_now_schedules}),
            problem_type_due_count=sum(1 for rs in due_now_schedules if rs.problem_type_id is not None),
            concept_due_count=sum(1 for rs in due_now_schedules if rs.concept_id is not None),
        )

        # --------------------------------------------------
        # 10. Active Teaching Plan & Current Plan Alignment
        # --------------------------------------------------
        if scoped_subject_ids:
            tp_query = select(TeachingPlan).where(
                TeachingPlan.classroom_id == classroom.id,
                TeachingPlan.status == TeachingPlanStatus.ACTIVE,
                TeachingPlan.subject_id.in_(list(scoped_subject_ids)),
            )
            active_tp = self.session.scalar(tp_query.order_by(TeachingPlan.created_at.desc()).limit(1))
        else:
            active_tp = None

        active_tp_summary: ActiveTeachingPlanSummaryRead | None = None
        current_plan_mastery: CurrentPlanMasteryRead | None = None
        active_pt_ids: set[UUID] = set()

        if active_tp:
            tp_items = list(
                self.session.scalars(
                    select(TeachingPlanItem).where(TeachingPlanItem.teaching_plan_id == active_tp.id)
                ).all()
            )
            active_pt_ids = {it.problem_type_id for it in tp_items if it.problem_type_id}
            active_lo_ids = {it.learning_outcome_id for it in tp_items if it.learning_outcome_id}
            active_tp_summary = ActiveTeachingPlanSummaryRead(
                teaching_plan_id=active_tp.id,
                subject_id=active_tp.subject_id,
                active_problem_type_ids=list(active_pt_ids),
                active_learning_outcome_ids=list(active_lo_ids),
            )

            if active_pt_ids:
                pt_avg = self.session.scalar(
                    select(func.avg(StudentProblemTypeMastery.mastery_score)).where(
                        StudentProblemTypeMastery.student_id.in_(student_ids),
                        StudentProblemTypeMastery.problem_type_id.in_(list(active_pt_ids)),
                    )
                )
                plan_subq = (
                    select(
                        StudentProblemTypeMastery.student_id,
                        func.avg(StudentProblemTypeMastery.mastery_score).label("st_avg"),
                    )
                    .where(
                        StudentProblemTypeMastery.student_id.in_(student_ids),
                        StudentProblemTypeMastery.problem_type_id.in_(list(active_pt_ids)),
                    )
                    .group_by(StudentProblemTypeMastery.student_id)
                ).subquery()
                below_6 = self.session.scalar(select(func.count()).where(plan_subq.c.st_avg < 0.60)) or 0
                below_4 = self.session.scalar(select(func.count()).where(plan_subq.c.st_avg < 0.40)) or 0
                current_plan_mastery = CurrentPlanMasteryRead(
                    average_mastery=round(float(pt_avg), 2) if pt_avg is not None else None,
                    students_below_0_6=below_6,
                    students_below_0_4=below_4,
                )

        # --------------------------------------------------
        # 11. Verified Root Causes (SUPPORTED verifications only)
        # --------------------------------------------------
        if scoped_subject_ids:
            v_target_query = (
                select(RootCauseVerificationTarget, RootCauseDiagnosis)
                .join(
                    RootCauseVerification,
                    RootCauseVerification.id == RootCauseVerificationTarget.verification_id,
                )
                .join(
                    RootCauseDiagnosis,
                    RootCauseDiagnosis.id == RootCauseVerification.diagnosis_id,
                )
                .where(
                    RootCauseVerificationTarget.outcome == RootCauseVerificationOutcome.SUPPORTED,
                    RootCauseVerification.status == RootCauseVerificationStatus.COMPLETED,
                    RootCauseDiagnosis.classroom_id == classroom.id,
                    RootCauseDiagnosis.student_id.in_(student_ids),
                    RootCauseDiagnosis.subject_id.in_(list(scoped_subject_ids)),
                )
            )
            verified_targets_rows = list(self.session.execute(v_target_query).all())
        else:
            verified_targets_rows = []

        verified_by_key: dict[tuple[str, UUID], tuple[str, set[UUID]]] = {}
        for vt, diag in verified_targets_rows:
            target_id = vt.target_concept_id or vt.target_problem_type_id or vt.misconception_definition_id or vt.id
            key = (vt.target_type.value, target_id)
            if key not in verified_by_key:
                name = "Nguyên nhân gốc rễ"
                if vt.target_concept_id:
                    c = self.session.get(Concept, vt.target_concept_id)
                    if c:
                        name = c.name
                elif vt.target_problem_type_id:
                    pt = self.session.get(ProblemType, vt.target_problem_type_id)
                    if pt:
                        name = pt.name
                elif vt.misconception_definition_id:
                    md = self.session.get(MisconceptionDefinition, vt.misconception_definition_id)
                    if md:
                        name = md.name
                verified_by_key[key] = (name, set())
            verified_by_key[key][1].add(diag.student_id)

        verified_root_causes: list[VerifiedRootCauseMetricRead] = []
        for (ttype, tid), (tname, sids) in verified_by_key.items():
            affects_plan = False
            if active_pt_ids:
                if ttype == RootCauseVerificationTargetType.PROBLEM_TYPE.value and tid in active_pt_ids:
                    affects_plan = True
                elif ttype == RootCauseVerificationTargetType.CONCEPT.value:
                    has_link = self.session.scalar(
                        select(ProblemTypeConcept.problem_type_id).where(
                            ProblemTypeConcept.concept_id == tid,
                            ProblemTypeConcept.problem_type_id.in_(list(active_pt_ids)),
                        ).limit(1)
                    )
                    if has_link:
                        affects_plan = True

            verified_root_causes.append(
                VerifiedRootCauseMetricRead(
                    target_type=ttype,
                    target_id=tid,
                    target_name=tname,
                    affected_student_count=len(sids),
                    student_ids=sorted(list(sids)),
                    affects_current_plan=affects_plan,
                )
            )
        verified_root_causes.sort(
            key=lambda item: (-item.affected_student_count, item.target_name, str(item.target_id))
        )

        # --------------------------------------------------
        # 12. Adaptive Repair Summary
        # --------------------------------------------------
        if scoped_subject_ids:
            repair_query = (
                select(AdaptiveRepairSession)
                .join(
                    RootCauseDiagnosis,
                    RootCauseDiagnosis.id == AdaptiveRepairSession.diagnosis_id,
                )
                .where(
                    AdaptiveRepairSession.student_id.in_(student_ids),
                    RootCauseDiagnosis.classroom_id == classroom.id,
                    RootCauseDiagnosis.subject_id.in_(list(scoped_subject_ids)),
                )
            )
            classroom_repairs = list(self.session.scalars(repair_query).all())
        else:
            classroom_repairs = []

        rep_active = sum(1 for s in classroom_repairs if s.status == AdaptiveRepairStatus.ACTIVE)
        rep_completed = sum(1 for s in classroom_repairs if s.status == AdaptiveRepairStatus.COMPLETED)
        rep_resolved = sum(1 for s in classroom_repairs if s.outcome == AdaptiveRepairOutcome.RESOLVED)
        rep_needs_more = sum(1 for s in classroom_repairs if s.outcome == AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE)
        rep_exhausted = sum(1 for s in classroom_repairs if s.outcome == AdaptiveRepairOutcome.BANK_EXHAUSTED)
        rep_rate = round(rep_resolved / rep_completed * 100.0, 1) if rep_completed > 0 else 0.0

        repair_summary = RepairSummaryRead(
            active_count=rep_active,
            completed_count=rep_completed,
            resolved_count=rep_resolved,
            needs_more_practice_count=rep_needs_more,
            bank_exhausted_count=rep_exhausted,
            resolution_rate=rep_rate,
        )

        # --------------------------------------------------
        # 13. Study Completion (Backward Compatibility)
        # --------------------------------------------------
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

        # --------------------------------------------------
        # 14. Students Needing Attention (from Intervention Alerts)
        # --------------------------------------------------
        alerts_data = self.get_classroom_alerts(
            teacher_user_id, classroom_id, subject_id=subject_id, include_synthetic=include_synthetic
        )
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

        # Deterministic sorting
        students_attention.sort(
            key=lambda s: (
                -severity_rank[s.highest_severity],
                -s.alert_count,
                s.student_name,
                str(s.student_id),
            )
        )

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
            evidence_sources=evidence_sources,
            assignment_completion=assignment_completion,
            review_due=review_due,
            verified_root_causes=verified_root_causes,
            repair_summary=repair_summary,
            evidence_summary=evidence_summary,
            active_teaching_plan=active_tp_summary,
            current_plan_mastery=current_plan_mastery,
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
        scoped_subject_ids = self._resolve_classroom_subject_scope(classroom, subject_id)

        students_info = self.get_enrolled_students(classroom_id, include_synthetic)
        student_ids = [s.id for s, _ in students_info]

        rows: list[HeatmapRowRead] = [
            HeatmapRowRead(student_id=s.id, student_name=name, is_synthetic=s.is_synthetic)
            for s, name in students_info
        ]

        if not scoped_subject_ids:
            return ClassroomHeatmapRead(
                classroom_id=classroom.id,
                view=view,
                columns=[],
                rows=rows,
                cells=[],
                column_averages={},
                row_averages={},
            )

        columns: list[HeatmapColumnRead] = []
        cells: list[HeatmapCellRead] = []
        col_sum: dict[UUID, float] = {}
        col_cnt: dict[UUID, int] = {}
        row_sum: dict[UUID, float] = {}
        row_cnt: dict[UUID, int] = {}

        if view == HeatmapView.PROBLEM_TYPE:
            query = (
                select(ProblemType, Topic.name.label("topic_name"))
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .where(Chapter.subject_id.in_(list(scoped_subject_ids)))
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
                        confidence = round(m.confidence, 2) if m else None
                        last_prac = m.last_practiced_at if m else None
                        level = self._score_to_level(score)

                        cells.append(
                            HeatmapCellRead(
                                student_id=row.student_id,
                                column_id=col.id,
                                score=score,
                                level=level,
                                attempt_count=attempts,
                                confidence=confidence,
                                last_practiced_at=last_prac,
                                observed_target_count=1 if m else 0,
                                total_target_count=1,
                            )
                        )
                        if score is not None:
                            col_sum[col.id] = col_sum.get(col.id, 0.0) + score
                            col_cnt[col.id] = col_cnt.get(col.id, 0) + 1
                            row_sum[row.student_id] = row_sum.get(row.student_id, 0.0) + score
                            row_cnt[row.student_id] = row_cnt.get(row.student_id, 0) + 1

        elif view == HeatmapView.CONCEPT:
            query = (
                select(Concept)
                .where(Concept.subject_id.in_(list(scoped_subject_ids)))
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
                        confidence = round(m.confidence, 2) if m else None
                        last_prac = m.last_practiced_at if m else None
                        level = self._score_to_level(score)

                        cells.append(
                            HeatmapCellRead(
                                student_id=row.student_id,
                                column_id=col.id,
                                score=score,
                                level=level,
                                attempt_count=attempts,
                                confidence=confidence,
                                last_practiced_at=last_prac,
                                observed_target_count=1 if m else 0,
                                total_target_count=1,
                            )
                        )
                        if score is not None:
                            col_sum[col.id] = col_sum.get(col.id, 0.0) + score
                            col_cnt[col.id] = col_cnt.get(col.id, 0) + 1
                            row_sum[row.student_id] = row_sum.get(row.student_id, 0.0) + score
                            row_cnt[row.student_id] = row_cnt.get(row.student_id, 0) + 1

        elif view == HeatmapView.TOPIC:
            query = (
                select(Topic, Chapter.name.label("chp_name"))
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .where(Chapter.subject_id.in_(list(scoped_subject_ids)))
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
                        confidences = []
                        dates = []
                        total_att = 0
                        for pt_id in child_pts:
                            m = m_lookup.get((row.student_id, pt_id))
                            if m and m.mastery_score is not None:
                                scores.append(m.mastery_score)
                                confidences.append(m.confidence)
                                if m.last_practiced_at:
                                    dates.append(m.last_practiced_at)
                                total_att += m.attempt_count

                        avg_score = round(sum(scores) / len(scores), 2) if scores else None
                        avg_conf = round(sum(confidences) / len(confidences), 2) if confidences else None
                        latest_date = max(dates) if dates else None
                        level = self._score_to_level(avg_score)

                        cells.append(
                            HeatmapCellRead(
                                student_id=row.student_id,
                                column_id=col.id,
                                score=avg_score,
                                level=level,
                                attempt_count=total_att,
                                confidence=avg_conf,
                                last_practiced_at=latest_date,
                                observed_target_count=len(scores),
                                total_target_count=len(child_pts),
                            )
                        )
                        if avg_score is not None:
                            col_sum[col.id] = col_sum.get(col.id, 0.0) + avg_score
                            col_cnt[col.id] = col_cnt.get(col.id, 0) + 1
                            row_sum[row.student_id] = row_sum.get(row.student_id, 0.0) + avg_score
                            row_cnt[row.student_id] = row_cnt.get(row.student_id, 0) + 1

        elif view == HeatmapView.CHAPTER:
            query = (
                select(Chapter, Subject.name.label("sub_name"))
                .join(Subject, Subject.id == Chapter.subject_id)
                .where(Chapter.subject_id.in_(list(scoped_subject_ids)))
            )
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
                        confidences = []
                        dates = []
                        total_att = 0
                        for pt_id in child_pts:
                            m = m_lookup.get((row.student_id, pt_id))
                            if m and m.mastery_score is not None:
                                scores.append(m.mastery_score)
                                confidences.append(m.confidence)
                                if m.last_practiced_at:
                                    dates.append(m.last_practiced_at)
                                total_att += m.attempt_count

                        avg_score = round(sum(scores) / len(scores), 2) if scores else None
                        avg_conf = round(sum(confidences) / len(confidences), 2) if confidences else None
                        latest_date = max(dates) if dates else None
                        level = self._score_to_level(avg_score)

                        cells.append(
                            HeatmapCellRead(
                                student_id=row.student_id,
                                column_id=col.id,
                                score=avg_score,
                                level=level,
                                attempt_count=total_att,
                                confidence=avg_conf,
                                last_practiced_at=latest_date,
                                observed_target_count=len(scores),
                                total_target_count=len(child_pts),
                            )
                        )
                        if avg_score is not None:
                            col_sum[col.id] = col_sum.get(col.id, 0.0) + avg_score
                            col_cnt[col.id] = col_cnt.get(col.id, 0) + 1
                            row_sum[row.student_id] = row_sum.get(row.student_id, 0.0) + avg_score
                            row_cnt[row.student_id] = row_cnt.get(row.student_id, 0) + 1

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
        subject_id: UUID | None = None,
        include_synthetic: bool = False,
    ) -> ClassroomAlertsRead:
        """Run all 8 deterministic intervention rules against enrolled students."""
        _, classroom = self.require_teacher_access(teacher_user_id, classroom_id)
        scoped_subject_ids = self._resolve_classroom_subject_scope(classroom, subject_id)

        students_info = self.get_enrolled_students(classroom_id, include_synthetic)
        student_count = len(students_info)

        if student_count == 0 or not scoped_subject_ids:
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
        # Mastery < 0.40, attempts >= 3, and confidence >= 0.50
        # --------------------------------------------------
        pt_query = (
            select(StudentProblemTypeMastery, ProblemType.name)
            .join(ProblemType, ProblemType.id == StudentProblemTypeMastery.problem_type_id)
            .join(Topic, Topic.id == ProblemType.topic_id)
            .join(Chapter, Chapter.id == Topic.chapter_id)
            .where(
                StudentProblemTypeMastery.student_id.in_(student_ids),
                StudentProblemTypeMastery.mastery_score < 0.40,
                StudentProblemTypeMastery.attempt_count >= 3,
                StudentProblemTypeMastery.confidence >= 0.50,
                Chapter.subject_id.in_(list(scoped_subject_ids)),
            )
        )
        low_pt_rows = list(self.session.execute(pt_query).all())

        for m, pt_name in low_pt_rows:
            sname = students_by_id.get(m.student_id, "Học sinh")
            sev = (
                AlertSeverity.CRITICAL
                if m.mastery_score < 0.25 and m.confidence >= 0.70
                else AlertSeverity.HIGH
            )
            alerts.append(
                InterventionAlertRead(
                    id=f"low_problem_type_mastery-{m.student_id}-{m.problem_type_id}",
                    student_id=m.student_id,
                    student_name=sname,
                    rule_code=AlertRuleCode.LOW_PROBLEM_TYPE_MASTERY,
                    severity=sev,
                    title=f"Khó khăn kéo dài ở dạng bài [{pt_name}]",
                    message=(
                        f"Học sinh {sname} có điểm thành thạo rất thấp ({m.mastery_score:.2f}) "
                        f"sau {m.attempt_count} lượt làm bài ở dạng [{pt_name}] (độ tin cậy: {m.confidence:.2f})."
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
        # Verified root cause: PREREQUISITE_CONCEPT_GAP with verification target SUPPORTED
        # --------------------------------------------------
        prereq_v_query = (
            select(RootCauseVerificationTarget, RootCauseDiagnosis, Concept.name)
            .join(
                RootCauseVerification,
                RootCauseVerification.id == RootCauseVerificationTarget.verification_id,
            )
            .join(
                RootCauseDiagnosis,
                RootCauseDiagnosis.id == RootCauseVerification.diagnosis_id,
            )
            .join(
                Concept,
                Concept.id == RootCauseVerificationTarget.target_concept_id,
            )
            .where(
                RootCauseDiagnosis.classroom_id == classroom.id,
                RootCauseDiagnosis.student_id.in_(student_ids),
                RootCauseDiagnosis.subject_id.in_(list(scoped_subject_ids)),
                RootCauseDiagnosis.diagnosis_type == RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
                RootCauseVerification.status == RootCauseVerificationStatus.COMPLETED,
                RootCauseVerificationTarget.outcome == RootCauseVerificationOutcome.SUPPORTED,
            )
        )
        prereq_targets = list(self.session.execute(prereq_v_query).all())
        for vt, diag, cname in prereq_targets:
            sname = students_by_id.get(diag.student_id, "Học sinh")
            alerts.append(
                InterventionAlertRead(
                    id=f"prerequisite_gap-{diag.student_id}-{vt.target_concept_id}",
                    student_id=diag.student_id,
                    student_name=sname,
                    rule_code=AlertRuleCode.PREREQUISITE_GAP,
                    severity=AlertSeverity.HIGH,
                    title=f"Hổng kiến thức tiên quyết [{cname}]",
                    message=(
                        f"Học sinh {sname} đã được xác minh hổng khái niệm tiên quyết [{cname}] "
                        f"(độ tin cậy chẩn đoán: {diag.confidence:.2f}), "
                        f"đe dọa trực tiếp khả năng tiếp thu bài mới."
                    ),
                    target_id=vt.target_concept_id,
                    target_name=cname,
                    metric_value=round(diag.confidence, 2),
                    detected_at=now,
                    suggested_action="Khởi động phiên khắc phục (Repair Session) tập trung vào khái niệm này.",
                )
            )

        # --------------------------------------------------
        # Rule 3: PERSISTENT_MISCONCEPTION
        # Only status CONFIRMED or verified misconception target SUPPORTED
        # --------------------------------------------------
        # Source A: Confirmed student misconceptions
        misc_source_a_query = (
            select(StudentMisconception, MisconceptionDefinition.name)
            .join(
                MisconceptionDefinition,
                MisconceptionDefinition.id == StudentMisconception.misconception_definition_id,
            )
            .join(
                Concept, Concept.id == MisconceptionDefinition.concept_id
            )
            .where(
                StudentMisconception.student_id.in_(student_ids),
                StudentMisconception.status == StudentMisconceptionStatus.CONFIRMED,
                Concept.subject_id.in_(list(scoped_subject_ids)),
            )
        )
        confirmed_miscs = list(self.session.execute(misc_source_a_query).all())

        # Source B: Verified misconception targets from classroom root-cause diagnoses
        misc_source_b_query = (
            select(
                RootCauseVerificationTarget,
                RootCauseDiagnosis,
                MisconceptionDefinition.name,
            )
            .join(
                RootCauseVerification,
                RootCauseVerification.id == RootCauseVerificationTarget.verification_id,
            )
            .join(
                RootCauseDiagnosis,
                RootCauseDiagnosis.id == RootCauseVerification.diagnosis_id,
            )
            .join(
                MisconceptionDefinition,
                MisconceptionDefinition.id == RootCauseVerificationTarget.misconception_definition_id,
            )
            .where(
                RootCauseDiagnosis.classroom_id == classroom.id,
                RootCauseDiagnosis.student_id.in_(student_ids),
                RootCauseDiagnosis.subject_id.in_(list(scoped_subject_ids)),
                RootCauseVerificationTarget.target_type == RootCauseVerificationTargetType.MISCONCEPTION,
                RootCauseVerificationTarget.outcome == RootCauseVerificationOutcome.SUPPORTED,
                RootCauseVerification.status == RootCauseVerificationStatus.COMPLETED,
            )
        )
        verified_misc_targets = list(self.session.execute(misc_source_b_query).all())

        misc_alerts_map: dict[tuple[UUID, UUID], dict[str, Any]] = {}
        for sm, mname in confirmed_miscs:
            key = (sm.student_id, sm.misconception_definition_id)
            misc_alerts_map[key] = {
                "student_id": sm.student_id,
                "definition_id": sm.misconception_definition_id,
                "name": mname,
                "confidence": sm.confidence,
            }
        for vt, diag, mname in verified_misc_targets:
            key = (diag.student_id, vt.misconception_definition_id)
            if key not in misc_alerts_map:
                misc_alerts_map[key] = {
                    "student_id": diag.student_id,
                    "definition_id": vt.misconception_definition_id,
                    "name": mname,
                    "confidence": diag.confidence,
                }
            else:
                misc_alerts_map[key]["confidence"] = max(
                    misc_alerts_map[key]["confidence"],
                    diag.confidence,
                )

        for (sid, def_id), info in misc_alerts_map.items():
            sname = students_by_id.get(sid, "Học sinh")
            mname = info["name"]
            conf = info["confidence"]
            alerts.append(
                InterventionAlertRead(
                    id=f"persistent_misconception-{sid}-{def_id}",
                    student_id=sid,
                    student_name=sname,
                    rule_code=AlertRuleCode.PERSISTENT_MISCONCEPTION,
                    severity=AlertSeverity.HIGH,
                    title=f"Lỗi sai hiểu lầm cố định [{mname}]",
                    message=(
                        f"Học sinh {sname} lặp lại lỗi sai hiểu lầm [{mname}] "
                        f"(độ tin cậy: {conf:.2f})."
                    ),
                    target_id=def_id,
                    target_name=mname,
                    metric_value=round(conf, 2),
                    detected_at=now,
                    suggested_action="Chỉ rõ bẫy sai lầm này trong bài giảng hoặc hướng dẫn học sinh xem tóm tắt lý thuyết.",
                )
            )

        # --------------------------------------------------
        # Rule 4: FAILED_REPAIR (AdaptiveRepairSession)
        # >= 3 completed repair cycles for same target without RESOLVED outcome
        # --------------------------------------------------
        ars_query = (
            select(AdaptiveRepairSession)
            .join(
                RootCauseDiagnosis,
                RootCauseDiagnosis.id == AdaptiveRepairSession.diagnosis_id,
            )
            .where(
                AdaptiveRepairSession.student_id.in_(student_ids),
                AdaptiveRepairSession.status == AdaptiveRepairStatus.COMPLETED,
                RootCauseDiagnosis.classroom_id == classroom.id,
                RootCauseDiagnosis.subject_id.in_(list(scoped_subject_ids)),
            )
        )
        repairs = list(self.session.scalars(ars_query).all())
        repairs_by_target: dict[tuple[UUID, UUID], list[AdaptiveRepairSession]] = {}
        for r in repairs:
            repairs_by_target.setdefault((r.student_id, r.verification_target_id), []).append(r)

        for (sid, vt_id), sessions in repairs_by_target.items():
            sessions.sort(
                key=lambda s: (
                    s.repair_cycle_index,
                    _ensure_utc(s.completed_at) or datetime.min.replace(tzinfo=timezone.utc),
                    str(s.id),
                )
            )
            latest_session = sessions[-1]
            if latest_session.outcome == AdaptiveRepairOutcome.RESOLVED:
                continue

            trailing_count = 0
            for s in reversed(sessions):
                if s.outcome == AdaptiveRepairOutcome.RESOLVED:
                    break
                if s.outcome in (AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE, AdaptiveRepairOutcome.BANK_EXHAUSTED):
                    trailing_count += 1

            if trailing_count >= 3:
                sname = students_by_id.get(sid, "Học sinh")
                tname = latest_session.target_name or "Nội dung cần sửa"
                alerts.append(
                    InterventionAlertRead(
                        id=f"failed_repair-{sid}-{vt_id}",
                        student_id=sid,
                        student_name=sname,
                        rule_code=AlertRuleCode.FAILED_REPAIR,
                        severity=AlertSeverity.CRITICAL,
                        title=f"Thất bại liên tiếp sau 3 phiên sửa lỗi ở [{tname}]",
                        message=(
                            f"Học sinh {sname} đã hoàn thành {trailing_count} chu kỳ sửa lỗi thích ứng "
                            f"ở [{tname}] nhưng chưa đạt kết quả giải quyết (RESOLVED)."
                        ),
                        target_id=vt_id,
                        target_name=tname,
                        metric_value=float(trailing_count),
                        detected_at=now,
                        suggested_action="Học sinh không thể tự sửa lỗi, giáo viên cần trực tiếp kèm cặp 1-1.",
                    )
                )

        # --------------------------------------------------
        # Rule 5: DECLINING_PERFORMANCE (LearningEvidenceEvent)
        # Last 3 scored events dropped >= 20% compared to previous 3 scored events
        # --------------------------------------------------
        for profile, sname in students_info:
            sid = profile.id
            ev_query = (
                select(LearningEvidenceEvent.score)
                .where(
                    LearningEvidenceEvent.classroom_id == classroom.id,
                    LearningEvidenceEvent.student_id == sid,
                    LearningEvidenceEvent.evaluation_status.in_([
                        EvaluationStatus.AUTO_EVALUATED,
                        EvaluationStatus.EVALUATED,
                    ]),
                    LearningEvidenceEvent.score.is_not(None),
                    LearningEvidenceEvent.subject_id.in_(list(scoped_subject_ids)),
                )
                .order_by(LearningEvidenceEvent.occurred_at.asc())
            )
            scored_events = list(self.session.scalars(ev_query).all())
            if len(scored_events) >= 6:
                recent_3 = scored_events[-3:]
                prev_3 = scored_events[-6:-3]
                avg_recent = sum(recent_3) / 3.0
                avg_prev = sum(prev_3) / 3.0

                if avg_prev >= 0.30 and (avg_prev - avg_recent) / avg_prev >= 0.20:
                    pct_drop = round(((avg_prev - avg_recent) / avg_prev) * 100, 1)
                    alerts.append(
                        InterventionAlertRead(
                            id=f"declining_performance-{sid}",
                            student_id=sid,
                            student_name=sname,
                            rule_code=AlertRuleCode.DECLINING_PERFORMANCE,
                            severity=AlertSeverity.MEDIUM,
                            title=f"Điểm số sụt giảm đáng kể (-{pct_drop}%)",
                            message=(
                                f"Học sinh {sname} có kết quả học tập sụt giảm: điểm trung bình 3 bài gần nhất "
                                f"({avg_recent:.2f}) giảm {pct_drop}% so với chu kỳ trước đó ({avg_prev:.2f})."
                            ),
                            metric_value=pct_drop,
                            detected_at=now,
                            suggested_action="Kiểm tra lại các dạng bài gần đây, khối lượng bài tập và kiến thức tiền đề.",
                        )
                    )

        # --------------------------------------------------
        # Rule 6: INACTIVE_STUDY (LearningEvidenceEvent)
        # No evidence in classroom for >= 7 days
        # --------------------------------------------------
        seven_days_ago = now - timedelta(days=7)
        for profile, sname in students_info:
            sid = profile.id
            lat_query = (
                select(LearningEvidenceEvent.occurred_at)
                .where(
                    LearningEvidenceEvent.classroom_id == classroom.id,
                    LearningEvidenceEvent.student_id == sid,
                    LearningEvidenceEvent.subject_id.in_(list(scoped_subject_ids)),
                )
                .order_by(LearningEvidenceEvent.occurred_at.desc())
                .limit(1)
            )
            latest_event_at = self.session.scalar(lat_query)
            latest_dt = _ensure_utc(latest_event_at)

            if latest_dt is None or latest_dt < seven_days_ago:
                days_inactive = (now - latest_dt).days if latest_dt else 14
                alerts.append(
                    InterventionAlertRead(
                        id=f"inactive_study-{sid}",
                        student_id=sid,
                        student_name=sname,
                        rule_code=AlertRuleCode.INACTIVE_STUDY,
                        severity=AlertSeverity.HIGH,
                        title="Học sinh ngưng trệ việc học",
                        message=f"Học sinh {sname} không có hoạt động học tập được ghi nhận trong {days_inactive} ngày qua.",
                        metric_value=float(days_inactive),
                        detected_at=now,
                        suggested_action="Nhắc nhở học sinh vào làm bài hoặc thông báo cho phụ huynh.",
                    )
                )

        # --------------------------------------------------
        # Rule 7: REVIEW_OVERDUE (ReviewSchedule)
        # >= 3 due now -> MEDIUM, >= 5 -> HIGH
        # --------------------------------------------------
        rs_due_query = (
            select(ReviewSchedule)
            .where(ReviewSchedule.student_id.in_(student_ids))
            .outerjoin(Concept, Concept.id == ReviewSchedule.concept_id)
            .outerjoin(ProblemType, ProblemType.id == ReviewSchedule.problem_type_id)
            .outerjoin(Topic, Topic.id == ProblemType.topic_id)
            .outerjoin(Chapter, Chapter.id == Topic.chapter_id)
            .where(
                (Concept.subject_id.in_(list(scoped_subject_ids)))
                | (Chapter.subject_id.in_(list(scoped_subject_ids)))
            )
        )
        all_due_rs = list(self.session.scalars(rs_due_query).all())
        due_now_all = [
            rs for rs in all_due_rs
            if rs.next_review_at is not None and _ensure_utc(rs.next_review_at) <= now
        ]
        due_by_student: dict[UUID, int] = {}
        for rs in due_now_all:
            due_by_student[rs.student_id] = due_by_student.get(rs.student_id, 0) + 1

        for sid, cnt in due_by_student.items():
            if cnt >= 3:
                sname = students_by_id.get(sid, "Học sinh")
                sev = AlertSeverity.HIGH if cnt >= 5 else AlertSeverity.MEDIUM
                alerts.append(
                    InterventionAlertRead(
                        id=f"review_overdue-{sid}",
                        student_id=sid,
                        student_name=sname,
                        rule_code=AlertRuleCode.REVIEW_OVERDUE,
                        severity=sev,
                        title=f"Học sinh có {cnt} nội dung đến hạn ôn tập",
                        message=f"Học sinh {sname} đang có {cnt} nội dung đến hạn ôn tập nhưng chưa hoàn thành.",
                        metric_value=float(cnt),
                        detected_at=now,
                        suggested_action="Ưu tiên một phiên ôn tập ngắn cho các nội dung đến hạn.",
                    )
                )

        # --------------------------------------------------
        # Rule 8: ASSIGNMENT_OVERDUE (StudentAssignment)
        # overdue count >= 1 -> MEDIUM, >= 2 -> HIGH
        # --------------------------------------------------
        sa_overdue_query = (
            select(StudentAssignment, Assignment.due_at)
            .join(Assignment, Assignment.id == StudentAssignment.assignment_id)
            .where(
                Assignment.classroom_id == classroom.id,
                Assignment.due_at.is_not(None),
                StudentAssignment.student_id.in_(student_ids),
                StudentAssignment.status.in_([
                    StudentAssignmentStatus.NOT_STARTED,
                    StudentAssignmentStatus.IN_PROGRESS,
                ]),
                Assignment.subject_id.in_(list(scoped_subject_ids)),
            )
        )

        overdue_pairs = list(self.session.execute(sa_overdue_query).all())
        overdue_counts: dict[UUID, int] = {}
        for sa, due_at in overdue_pairs:
            if due_at is not None and _ensure_utc(due_at) < now:
                overdue_counts[sa.student_id] = overdue_counts.get(sa.student_id, 0) + 1

        for sid, cnt in overdue_counts.items():
            if cnt >= 1:
                sname = students_by_id.get(sid, "Học sinh")
                sev = AlertSeverity.HIGH if cnt >= 2 else AlertSeverity.MEDIUM
                alerts.append(
                    InterventionAlertRead(
                        id=f"assignment_overdue-{sid}",
                        student_id=sid,
                        student_name=sname,
                        rule_code=AlertRuleCode.ASSIGNMENT_OVERDUE,
                        severity=sev,
                        title=f"Chưa hoàn thành {cnt} bài tập quá hạn",
                        message=f"Học sinh {sname} có {cnt} bài tập đã quá hạn nộp nhưng chưa hoàn thành.",
                        metric_value=float(cnt),
                        detected_at=now,
                        suggested_action="Nhắc nhở học sinh nộp bài hoặc hỗ trợ các câu hỏi chưa giải quyết được.",
                    )
                )

        # Deduplicate alerts by alert id
        deduped_alerts: list[InterventionAlertRead] = []
        seen_ids: set[str] = set()
        for a in alerts:
            if a.id not in seen_ids:
                seen_ids.add(a.id)
                deduped_alerts.append(a)

        # Sort by severity
        severity_rank = {
            AlertSeverity.CRITICAL: 4,
            AlertSeverity.HIGH: 3,
            AlertSeverity.MEDIUM: 2,
            AlertSeverity.LOW: 1,
        }
        deduped_alerts.sort(
            key=lambda a: (-severity_rank[a.severity], a.student_name, str(a.student_id), a.id)
        )

        critical_c = sum(1 for a in deduped_alerts if a.severity == AlertSeverity.CRITICAL)
        high_c = sum(1 for a in deduped_alerts if a.severity == AlertSeverity.HIGH)
        med_c = sum(1 for a in deduped_alerts if a.severity == AlertSeverity.MEDIUM)
        low_c = sum(1 for a in deduped_alerts if a.severity == AlertSeverity.LOW)

        return ClassroomAlertsRead(
            classroom_id=classroom.id,
            total_alerts=len(deduped_alerts),
            critical_count=critical_c,
            high_count=high_c,
            medium_count=med_c,
            low_count=low_c,
            alerts=deduped_alerts,
        )

    # --------------------------------------------------------------------------
    # 4. Student Drilldown Analytics
    # --------------------------------------------------------------------------

    def get_student_learning_analytics(
        self,
        teacher_user_id: UUID,
        classroom_id: UUID,
        student_id: UUID,
        subject_id: UUID | None = None,
    ) -> StudentLearningAnalyticsRead:
        """Detailed academic and behavioural analytics for a single student in a classroom."""
        _, classroom = self.require_teacher_access(teacher_user_id, classroom_id)
        scoped_subject_ids = self._resolve_classroom_subject_scope(classroom, subject_id)

        enrollment = self.session.scalar(
            select(StudentEnrollment).where(
                StudentEnrollment.classroom_id == classroom_id,
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            ).limit(1)
        )
        if enrollment is None:
            raise ApplicationError(404, "STUDENT_NOT_IN_CLASSROOM", "Student is not enrolled in this classroom.")

        student_prof = self.session.get(StudentProfile, student_id)
        if student_prof is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile not found.")

        student_user = self.session.get(User, student_prof.user_id)
        student_name = (
            student_user.full_name or student_user.email or f"Học sinh {str(student_id)[:6]}"
            if student_user
            else f"Học sinh {str(student_id)[:6]}"
        )
        now = datetime.now(timezone.utc)

        if not scoped_subject_ids:
            return StudentLearningAnalyticsRead(
                student_id=student_id,
                student_name=student_name,
                classroom_id=classroom_id,
                subject_id=subject_id,
                problem_type_mastery=[],
                concept_mastery=[],
                recent_evidence=RecentTrendsRead(
                    total_attempts_past_7_days=0,
                    total_evidence_past_7_days=0,
                    scored_evidence_past_7_days=0,
                    recent_average_score=0.0,
                    previous_average_score=None,
                    correct_rate=None,
                    score_delta=None,
                    trend_direction="INSUFFICIENT_DATA",
                ),
                evidence_sources=EvidenceSourceSummaryRead(),
                verified_root_causes=[],
                repair_summary=RepairSummaryRead(),
                reviews_due=ReviewDueSummaryRead(),
                assignment_summary=StudentAssignmentSummaryRead(
                    total_assigned=0,
                    not_started_count=0,
                    in_progress_count=0,
                    submitted_count=0,
                    graded_count=0,
                    overdue_count=0,
                    completion_rate=100.0,
                    average_score=None,
                ),
                alerts=[],
            )

        # 1. ProblemType Mastery
        pt_m_query = (
            select(StudentProblemTypeMastery, ProblemType)
            .join(ProblemType, ProblemType.id == StudentProblemTypeMastery.problem_type_id)
            .join(Topic, Topic.id == ProblemType.topic_id)
            .join(Chapter, Chapter.id == Topic.chapter_id)
            .where(
                StudentProblemTypeMastery.student_id == student_id,
                Chapter.subject_id.in_(list(scoped_subject_ids)),
            )
        )
        pt_rows = list(self.session.execute(pt_m_query).all())
        pt_mastery_list = [
            StudentMasteryItemRead(
                target_id=pt.id,
                target_code=pt.code,
                target_name=pt.name,
                mastery_score=round(m.mastery_score, 2),
                confidence=round(m.confidence, 2),
                attempt_count=m.attempt_count,
                correct_count=m.correct_count,
                last_practiced_at=m.last_practiced_at,
                level=self._score_to_level(m.mastery_score),
            )
            for m, pt in pt_rows
        ]
        pt_mastery_list.sort(key=lambda item: (item.mastery_score, -item.confidence, item.target_code))

        # 2. Concept Mastery
        c_m_query = (
            select(StudentConceptMastery, Concept)
            .join(Concept, Concept.id == StudentConceptMastery.concept_id)
            .where(
                StudentConceptMastery.student_id == student_id,
                Concept.subject_id.in_(list(scoped_subject_ids)),
            )
        )
        c_rows = list(self.session.execute(c_m_query).all())
        c_mastery_list = [
            StudentMasteryItemRead(
                target_id=c.id,
                target_code=c.code,
                target_name=c.name,
                mastery_score=round(m.mastery_score, 2),
                confidence=round(m.confidence, 2),
                attempt_count=m.attempt_count,
                correct_count=m.correct_count,
                last_practiced_at=m.last_practiced_at,
                level=self._score_to_level(m.mastery_score),
            )
            for m, c in c_rows
        ]
        c_mastery_list.sort(key=lambda item: (item.mastery_score, -item.confidence, item.target_code))

        # 3. Recent Evidence
        start_7d = now - timedelta(days=7)
        start_14d = now - timedelta(days=14)
        st_ev_query = select(LearningEvidenceEvent).where(
            LearningEvidenceEvent.classroom_id == classroom.id,
            LearningEvidenceEvent.student_id == student_id,
            LearningEvidenceEvent.subject_id.in_(list(scoped_subject_ids)),
        )

        st_events_14d = list(
            self.session.scalars(
                st_ev_query.where(LearningEvidenceEvent.occurred_at >= start_14d)
            ).all()
        )
        recent_ev = [e for e in st_events_14d if _ensure_utc(e.occurred_at) is not None and _ensure_utc(e.occurred_at) >= start_7d]
        scored_recent = [
            e for e in recent_ev
            if e.evaluation_status in (EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED)
            and e.score is not None
        ]
        recent_avg = (
            round(sum(e.score for e in scored_recent) / len(scored_recent), 2)
            if scored_recent
            else 0.0
        )
        scored_prev = [
            e for e in st_events_14d
            if _ensure_utc(e.occurred_at) is not None
            and _ensure_utc(e.occurred_at) < start_7d
            and e.evaluation_status in (EvaluationStatus.AUTO_EVALUATED, EvaluationStatus.EVALUATED)
            and e.score is not None
        ]
        prev_avg = (
            round(sum(e.score for e in scored_prev) / len(scored_prev), 2)
            if scored_prev
            else None
        )
        correct_recent = sum(1 for e in scored_recent if e.is_correct is True)
        recent_correct_rate = (
            round(correct_recent / len(scored_recent), 2)
            if scored_recent
            else None
        )

        if len(scored_recent) < 3 or len(scored_prev) < 3 or prev_avg is None:
            trend_dir = "INSUFFICIENT_DATA"
            score_delta = None
        else:
            delta = round(recent_avg - prev_avg, 2)
            score_delta = delta
            if delta > 0.05:
                trend_dir = "IMPROVING"
            elif delta < -0.05:
                trend_dir = "DECLINING"
            else:
                trend_dir = "STABLE"

        recent_trends = RecentTrendsRead(
            total_attempts_past_7_days=len(recent_ev),
            total_evidence_past_7_days=len(recent_ev),
            scored_evidence_past_7_days=len(scored_recent),
            recent_average_score=recent_avg,
            previous_average_score=prev_avg,
            correct_rate=recent_correct_rate,
            score_delta=score_delta,
            trend_direction=trend_dir,
        )

        # 4. Evidence Sources
        practice_count = self.session.scalar(
            select(func.count(LearningEvidenceEvent.id)).where(
                LearningEvidenceEvent.classroom_id == classroom.id,
                LearningEvidenceEvent.student_id == student_id,
                LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.PRACTICE_QUESTION,
                LearningEvidenceEvent.subject_id.in_(list(scoped_subject_ids)),
            )
        ) or 0
        asgn_ev_count = self.session.scalar(
            select(func.count(LearningEvidenceEvent.id)).where(
                LearningEvidenceEvent.classroom_id == classroom.id,
                LearningEvidenceEvent.student_id == student_id,
                LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION,
                LearningEvidenceEvent.subject_id.in_(list(scoped_subject_ids)),
            )
        ) or 0
        mat_ev_count = self.session.scalar(
            select(func.count(LearningEvidenceEvent.id)).where(
                LearningEvidenceEvent.classroom_id == classroom.id,
                LearningEvidenceEvent.student_id == student_id,
                LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM,
                LearningEvidenceEvent.subject_id.in_(list(scoped_subject_ids)),
            )
        ) or 0
        evidence_sources = EvidenceSourceSummaryRead(
            practice_count=practice_count,
            assignment_question_count=asgn_ev_count,
            teacher_material_count=mat_ev_count,
            total_count=practice_count + asgn_ev_count + mat_ev_count,
        )

        # 5. Verified Root Causes
        st_v_query = (
            select(RootCauseVerificationTarget, RootCauseDiagnosis)
            .join(
                RootCauseVerification,
                RootCauseVerification.id == RootCauseVerificationTarget.verification_id,
            )
            .join(
                RootCauseDiagnosis,
                RootCauseDiagnosis.id == RootCauseVerification.diagnosis_id,
            )
            .where(
                RootCauseVerificationTarget.outcome == RootCauseVerificationOutcome.SUPPORTED,
                RootCauseVerification.status == RootCauseVerificationStatus.COMPLETED,
                RootCauseDiagnosis.classroom_id == classroom.id,
                RootCauseDiagnosis.student_id == student_id,
                RootCauseDiagnosis.subject_id.in_(list(scoped_subject_ids)),
            )
        )

        v_targets = list(self.session.execute(st_v_query).all())
        verified_root_causes: list[VerifiedRootCauseMetricRead] = []
        for vt, diag in v_targets:
            tid = vt.target_concept_id or vt.target_problem_type_id or vt.misconception_definition_id or vt.id
            tname = "Nguyên nhân gốc rễ"
            if vt.target_concept_id:
                c = self.session.get(Concept, vt.target_concept_id)
                if c:
                    tname = c.name
            elif vt.target_problem_type_id:
                pt = self.session.get(ProblemType, vt.target_problem_type_id)
                if pt:
                    tname = pt.name
            elif vt.misconception_definition_id:
                md = self.session.get(MisconceptionDefinition, vt.misconception_definition_id)
                if md:
                    tname = md.name

            verified_root_causes.append(
                VerifiedRootCauseMetricRead(
                    target_type=vt.target_type.value,
                    target_id=tid,
                    target_name=tname,
                    affected_student_count=1,
                    student_ids=[student_id],
                )
            )

        # 6. Adaptive Repair Summary
        st_rep_query = (
            select(AdaptiveRepairSession)
            .join(
                RootCauseDiagnosis,
                RootCauseDiagnosis.id == AdaptiveRepairSession.diagnosis_id,
            )
            .where(
                AdaptiveRepairSession.student_id == student_id,
                RootCauseDiagnosis.classroom_id == classroom.id,
                RootCauseDiagnosis.subject_id.in_(list(scoped_subject_ids)),
            )
        )
        st_repairs = list(self.session.scalars(st_rep_query).all())
        rep_active = sum(1 for s in st_repairs if s.status == AdaptiveRepairStatus.ACTIVE)
        rep_completed = sum(1 for s in st_repairs if s.status == AdaptiveRepairStatus.COMPLETED)
        rep_resolved = sum(1 for s in st_repairs if s.outcome == AdaptiveRepairOutcome.RESOLVED)
        rep_needs_more = sum(1 for s in st_repairs if s.outcome == AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE)
        rep_exhausted = sum(1 for s in st_repairs if s.outcome == AdaptiveRepairOutcome.BANK_EXHAUSTED)
        rep_rate = round(rep_resolved / rep_completed * 100.0, 1) if rep_completed > 0 else 0.0
        repair_summary = RepairSummaryRead(
            active_count=rep_active,
            completed_count=rep_completed,
            resolved_count=rep_resolved,
            needs_more_practice_count=rep_needs_more,
            bank_exhausted_count=rep_exhausted,
            resolution_rate=rep_rate,
        )

        # 7. Reviews Due
        st_rs_query = (
            select(ReviewSchedule)
            .where(ReviewSchedule.student_id == student_id)
            .outerjoin(Concept, Concept.id == ReviewSchedule.concept_id)
            .outerjoin(ProblemType, ProblemType.id == ReviewSchedule.problem_type_id)
            .outerjoin(Topic, Topic.id == ProblemType.topic_id)
            .outerjoin(Chapter, Chapter.id == Topic.chapter_id)
            .where(
                (Concept.subject_id.in_(list(scoped_subject_ids)))
                | (Chapter.subject_id.in_(list(scoped_subject_ids)))
            )
        )
        st_schedules = list(self.session.scalars(st_rs_query).all())
        due_now_s = [
            rs for rs in st_schedules
            if rs.next_review_at is not None and _ensure_utc(rs.next_review_at) <= now
        ]
        due_3d_s = [
            rs for rs in st_schedules
            if rs.next_review_at is not None and now < _ensure_utc(rs.next_review_at) <= now + timedelta(days=3)
        ]
        reviews_due = ReviewDueSummaryRead(
            due_now_count=len(due_now_s),
            due_next_3_days_count=len(due_3d_s),
            students_due_count=1 if due_now_s else 0,
            problem_type_due_count=sum(1 for rs in due_now_s if rs.problem_type_id is not None),
            concept_due_count=sum(1 for rs in due_now_s if rs.concept_id is not None),
        )

        # 8. Assignment Summary
        st_sa_query = (
            select(StudentAssignment, Assignment)
            .join(Assignment, Assignment.id == StudentAssignment.assignment_id)
            .where(
                Assignment.classroom_id == classroom.id,
                Assignment.status.in_([AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED]),
                StudentAssignment.student_id == student_id,
                Assignment.subject_id.in_(list(scoped_subject_ids)),
            )
        )
        st_asgn_rows = list(self.session.execute(st_sa_query).all())

        st_total_assigned = len(st_asgn_rows)
        st_not_started = sum(1 for sa, _ in st_asgn_rows if sa.status == StudentAssignmentStatus.NOT_STARTED)
        st_in_progress = sum(1 for sa, _ in st_asgn_rows if sa.status == StudentAssignmentStatus.IN_PROGRESS)
        st_submitted = sum(1 for sa, _ in st_asgn_rows if sa.status == StudentAssignmentStatus.SUBMITTED)
        st_graded = sum(1 for sa, _ in st_asgn_rows if sa.status == StudentAssignmentStatus.GRADED)
        st_overdue = 0
        for sa, a in st_asgn_rows:
            if (
                a.due_at is not None
                and _ensure_utc(a.due_at) < now
                and sa.status in (StudentAssignmentStatus.NOT_STARTED, StudentAssignmentStatus.IN_PROGRESS)
            ):
                st_overdue += 1
        st_completed = st_submitted + st_graded
        st_comp_rate = round(st_completed / st_total_assigned * 100.0, 1) if st_total_assigned > 0 else 0.0
        st_scores = [sa.score for sa, _ in st_asgn_rows if sa.score is not None]
        st_avg_score = round(sum(st_scores) / len(st_scores), 2) if st_scores else None
        assignment_summary = StudentAssignmentSummaryRead(
            total_assigned=st_total_assigned,
            not_started_count=st_not_started,
            in_progress_count=st_in_progress,
            submitted_count=st_submitted,
            graded_count=st_graded,
            overdue_count=st_overdue,
            completion_rate=st_comp_rate,
            average_score=st_avg_score,
        )

        # 9. Alerts
        all_alerts = self.get_classroom_alerts(
            teacher_user_id, classroom_id, subject_id=subject_id
        ).alerts
        st_alerts = [a for a in all_alerts if a.student_id == student_id]

        return StudentLearningAnalyticsRead(
            student_id=student_id,
            student_name=student_name,
            classroom_id=classroom_id,
            subject_id=subject_id,
            problem_type_mastery=pt_mastery_list,
            concept_mastery=c_mastery_list,
            recent_evidence=recent_trends,
            evidence_sources=evidence_sources,
            verified_root_causes=verified_root_causes,
            repair_summary=repair_summary,
            reviews_due=reviews_due,
            assignment_summary=assignment_summary,
            alerts=st_alerts,
        )

    # --------------------------------------------------------------------------
    # 5. Assignment Analytics
    # --------------------------------------------------------------------------

    def get_assignment_analytics(
        self,
        teacher_user_id: UUID,
        classroom_id: UUID,
        assignment_id: UUID,
    ) -> AssignmentAnalyticsRead:
        """Detailed assignment performance report for teacher inspection."""
        _, classroom = self.require_teacher_access(teacher_user_id, classroom_id)

        assignment = self.session.get(Assignment, assignment_id)
        if assignment is None:
            raise ApplicationError(404, "ASSIGNMENT_NOT_FOUND", "Assignment not found.")

        if assignment.classroom_id != classroom_id:
            raise ApplicationError(
                404,
                "ASSIGNMENT_NOT_IN_CLASSROOM",
                "Assignment does not belong to this classroom.",
            )

        now = datetime.now(timezone.utc)

        # Student rows
        sa_rows = list(
            self.session.execute(
                select(StudentAssignment, User.full_name, User.email)
                .join(StudentProfile, StudentProfile.id == StudentAssignment.student_id)
                .join(User, User.id == StudentProfile.user_id)
                .where(StudentAssignment.assignment_id == assignment_id)
                .order_by(User.full_name.asc(), User.email.asc())
            ).all()
        )

        student_rows: list[AssignmentStudentRowRead] = []
        assigned_c = len(sa_rows)
        not_started_c = 0
        in_progress_c = 0
        submitted_c = 0
        graded_c = 0
        overdue_c = 0
        scores: list[float] = []

        for sa, fname, email in sa_rows:
            sname = fname or email or f"Học sinh {str(sa.student_id)[:6]}"
            is_overdue = (
                assignment.due_at is not None
                and _ensure_utc(assignment.due_at) < now
                and sa.status in (StudentAssignmentStatus.NOT_STARTED, StudentAssignmentStatus.IN_PROGRESS)
            )
            if sa.status == StudentAssignmentStatus.NOT_STARTED:
                not_started_c += 1
            elif sa.status == StudentAssignmentStatus.IN_PROGRESS:
                in_progress_c += 1
            elif sa.status == StudentAssignmentStatus.SUBMITTED:
                submitted_c += 1
            elif sa.status == StudentAssignmentStatus.GRADED:
                graded_c += 1

            if is_overdue:
                overdue_c += 1

            if sa.score is not None:
                scores.append(sa.score)

            student_rows.append(
                AssignmentStudentRowRead(
                    student_id=sa.student_id,
                    student_name=sname,
                    status=sa.status,
                    score=sa.score,
                    started_at=sa.started_at,
                    submitted_at=sa.submitted_at,
                    is_overdue=is_overdue,
                )
            )

        comp_rate = (
            round((submitted_c + graded_c) / assigned_c * 100.0, 1)
            if assigned_c > 0
            else 0.0
        )
        avg_score = round(sum(scores) / len(scores), 2) if scores else None

        # Target performance from LearningEvidenceEvent
        evidence_events = list(
            self.session.scalars(
                select(LearningEvidenceEvent).where(
                    LearningEvidenceEvent.assignment_id == assignment_id,
                    LearningEvidenceEvent.evaluation_status.in_([
                        EvaluationStatus.AUTO_EVALUATED,
                        EvaluationStatus.EVALUATED,
                    ]),
                    LearningEvidenceEvent.score.is_not(None),
                )
            ).all()
        )
        ev_ids = [e.id for e in evidence_events]
        ev_scores = {e.id: e.score for e in evidence_events if e.score is not None}

        # ProblemType target performance
        target_pts: list[AssignmentTargetPerformanceRead] = []
        if ev_ids:
            pt_links = list(
                self.session.execute(
                    select(
                        LearningEvidenceProblemType.problem_type_id,
                        LearningEvidenceProblemType.event_id,
                        LearningEvidenceProblemType.weight,
                        ProblemType.name,
                        ProblemType.code,
                    )
                    .join(ProblemType, ProblemType.id == LearningEvidenceProblemType.problem_type_id)
                    .where(LearningEvidenceProblemType.event_id.in_(ev_ids))
                ).all()
            )
            pt_accum: dict[UUID, dict[str, Any]] = {}
            for pt_id, ev_id, weight, pt_name, pt_code in pt_links:
                score = ev_scores.get(ev_id)
                if score is not None:
                    if pt_id not in pt_accum:
                        pt_accum[pt_id] = {
                            "name": pt_name,
                            "code": pt_code,
                            "weighted_score": 0.0,
                            "weight_sum": 0.0,
                            "count": 0,
                        }
                    pt_accum[pt_id]["weighted_score"] += score * weight
                    pt_accum[pt_id]["weight_sum"] += weight
                    pt_accum[pt_id]["count"] += 1

            for pt_id, data in pt_accum.items():
                avg = (
                    round(data["weighted_score"] / data["weight_sum"], 2)
                    if data["weight_sum"] > 0
                    else None
                )
                target_pts.append(
                    AssignmentTargetPerformanceRead(
                        target_id=pt_id,
                        target_name=data["name"],
                        target_code=data["code"],
                        average_score=avg,
                        evidence_count=data["count"],
                    )
                )

        # Concept target performance
        target_concepts: list[AssignmentTargetPerformanceRead] = []
        if ev_ids:
            c_links = list(
                self.session.execute(
                    select(
                        LearningEvidenceConcept.concept_id,
                        LearningEvidenceConcept.event_id,
                        LearningEvidenceConcept.weight,
                        Concept.name,
                        Concept.code,
                    )
                    .join(Concept, Concept.id == LearningEvidenceConcept.concept_id)
                    .where(LearningEvidenceConcept.event_id.in_(ev_ids))
                ).all()
            )
            c_accum: dict[UUID, dict[str, Any]] = {}
            for c_id, ev_id, weight, c_name, c_code in c_links:
                score = ev_scores.get(ev_id)
                if score is not None:
                    if c_id not in c_accum:
                        c_accum[c_id] = {
                            "name": c_name,
                            "code": c_code,
                            "weighted_score": 0.0,
                            "weight_sum": 0.0,
                            "count": 0,
                        }
                    c_accum[c_id]["weighted_score"] += score * weight
                    c_accum[c_id]["weight_sum"] += weight
                    c_accum[c_id]["count"] += 1

            for c_id, data in c_accum.items():
                avg = (
                    round(data["weighted_score"] / data["weight_sum"], 2)
                    if data["weight_sum"] > 0
                    else None
                )
                target_concepts.append(
                    AssignmentTargetPerformanceRead(
                        target_id=c_id,
                        target_name=data["name"],
                        target_code=data["code"],
                        average_score=avg,
                        evidence_count=data["count"],
                    )
                )

        # LearningOutcome target performance
        alo_lo_ids = set(
            self.session.scalars(
                select(AssignmentLearningObjective.learning_outcome_id).where(
                    AssignmentLearningObjective.assignment_id == assignment_id
                )
            ).all()
        )
        amilo_lo_ids = set(
            self.session.scalars(
                select(AssignmentMaterialItemLearningOutcome.learning_outcome_id)
                .join(
                    AssignmentMaterialItem,
                    AssignmentMaterialItem.id == AssignmentMaterialItemLearningOutcome.assignment_material_item_id,
                )
                .where(AssignmentMaterialItem.assignment_id == assignment_id)
            ).all()
        )
        lo_ids = list(alo_lo_ids | amilo_lo_ids)
        target_los: list[AssignmentTargetPerformanceRead] = []
        if lo_ids:
            los = list(
                self.session.scalars(
                    select(LearningOutcome)
                    .where(LearningOutcome.id.in_(lo_ids))
                    .order_by(
                        LearningOutcome.order_index.nulls_last(),
                        LearningOutcome.code.asc(),
                        LearningOutcome.id.asc(),
                    )
                ).all()
            )
            for lo in los:
                # Direct LearningEvidence currently maps Concept/ProblemType only; LO performance is intentionally not inferred.
                target_los.append(
                    AssignmentTargetPerformanceRead(
                        target_id=lo.id,
                        target_name=lo.description,
                        target_code=lo.code,
                        average_score=None,
                        evidence_count=0,
                    )
                )

        return AssignmentAnalyticsRead(
            assignment_id=assignment_id,
            title=assignment.title,
            status=assignment.status,
            due_at=assignment.due_at,
            assigned_count=assigned_c,
            not_started_count=not_started_c,
            in_progress_count=in_progress_c,
            submitted_count=submitted_c,
            graded_count=graded_c,
            overdue_count=overdue_c,
            completion_rate=comp_rate,
            average_score=avg_score,
            target_problem_types=target_pts,
            target_concepts=target_concepts,
            target_learning_outcomes=target_los,
            student_rows=student_rows,
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
