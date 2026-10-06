from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment,
    AssignmentStatus,
    StudentAssignment,
    StudentAssignmentStatus,
)
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment
from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.knowledge_gap.models import (
    RootCauseDiagnosis,
    RootCauseVerification,
    RootCauseVerificationOutcome,
    RootCauseVerificationStatus,
    RootCauseVerificationTarget,
)
from app.misconceptions.models import MisconceptionDefinition
from app.learning.feedback_service import LearningFeedbackService
from app.learning_evidence.models import LearningEvidenceEvent
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.mastery.state import DerivedMasteryState, derive_mastery_state
from app.planning.models import TeachingPlan, TeachingPlanStatus
from app.planning.study_models import StudyPlan, StudyTask, StudyTaskStatus
from app.planning.study_schemas import StudyDayRead, StudyTaskRead
from app.planning.study_service import StudyPlanService
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.recommendations.priority_service import LearningPriorityService
from app.repair.models import (
    AdaptiveRepairOutcome,
    AdaptiveRepairSession,
    AdaptiveRepairStatus,
)
from app.review.models import ReviewSchedule
from app.review.service import ReviewScheduleService
from app.student_learning_state.schemas import (
    StudentActiveLearningRead,
    StudentAssignmentStateItemRead,
    StudentAssignmentStateRead,
    StudentClassContextRead,
    StudentCurrentActionRead,
    StudentCurrentActionType,
    StudentLearningStateRead,
    StudentLearningSubjectRead,
    StudentMasterySummaryRead,
    StudentPriorityTargetRead,
    StudentRepairStateRead,
    StudentReviewStateRead,
    StudentReviewTargetRead,
    StudentVerifiedRootCauseRead,
    StudentWeakTargetRead,
)
from app.students.goal_models import AcademicGoal, AcademicGoalStatus, SubjectGoal
from app.students.models import StudentProfile
from app.subjects.models import Subject

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class StudentLearningStateService:
    """Read-model projection service for student learning state."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_learning_state(
        self,
        student_id: UUID,
        *,
        subject_id: UUID | None = None,
        as_of: datetime | None = None,
    ) -> StudentLearningStateRead:
        student = self.session.get(StudentProfile, student_id)
        if student is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile was not found.")

        now = as_of or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # 1. Discover available subjects for this student
        available_subjects = self._resolve_available_subjects(student_id)
        available_subject_ids = {s.id for s in available_subjects}

        # 2. Validate explicit subject_id if provided
        if subject_id is not None:
            db_subject = self.session.get(Subject, subject_id)
            if db_subject is None:
                raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
            if subject_id not in available_subject_ids:
                raise ApplicationError(
                    409,
                    "STUDENT_SUBJECT_NOT_IN_SCOPE",
                    "Subject is not within student's authorized scope.",
                )
            focus_subject_id = subject_id
        else:
            focus_subject_id = self._resolve_focus_subject(
                student_id, available_subjects, now=now
            )

        # 3. Class context for student
        class_contexts = self._resolve_class_contexts(student_id, focus_subject_id)

        # 4. Active learning components query
        active_repair = self._get_active_repair(student_id, focus_subject_id)
        active_verification, active_verification_diag = self._get_active_verification(
            student_id, focus_subject_id
        )
        in_progress_assignment, in_prog_assign_model = self._get_in_progress_assignment(
            student_id, focus_subject_id, now=now
        )
        overdue_assignment, overdue_assign_model = self._get_overdue_assignment(
            student_id, focus_subject_id, now=now
        )
        active_practice = self._get_active_practice(student_id, focus_subject_id)

        # 5. Reviews
        review_state = self._resolve_review_state(student_id, focus_subject_id, now=now)

        # 6. Today study plan snapshot (strictly read-only)
        today_plan = self._resolve_today_plan_snapshot(student_id, focus_subject_id, now=now)

        # 7. Learning priorities
        priority_targets = self._resolve_priority_targets(student_id, focus_subject_id)

        # 8. Determine current action following deterministic precedence
        current_action = self._determine_current_action(
            focus_subject_id=focus_subject_id,
            active_repair=active_repair,
            active_verification=active_verification,
            active_verification_diag=active_verification_diag,
            in_progress_assignment=in_progress_assignment,
            in_prog_assign_model=in_prog_assign_model,
            overdue_assignment=overdue_assignment,
            overdue_assign_model=overdue_assign_model,
            active_practice=active_practice,
            review_state=review_state,
            today_plan=today_plan,
            priority_targets=priority_targets,
        )

        # 9. Active learning summary
        active_learning = self._build_active_learning(
            active_repair=active_repair,
            active_verification=active_verification,
            in_prog_assign_model=in_prog_assign_model,
            active_practice=active_practice,
        )

        # 10. Repair state projection
        repair_state = self._build_repair_state(active_repair)

        # 11. Assignments state projection
        assignment_state = self._resolve_assignment_state(
            student_id, focus_subject_id, now=now
        )

        # 12. Compact mastery summary
        mastery_summary = self._resolve_mastery_summary(
            student_id, focus_subject_id, now=now
        )

        # 13. Verified root causes
        verified_root_causes = self._resolve_verified_root_causes(
            student_id, focus_subject_id
        )

        # 14. Latest feedback
        latest_feedback = None
        if focus_subject_id is not None:
            feedback_svc = LearningFeedbackService(self.session)
            latest_feedback = feedback_svc.get_latest_feedback(
                student_id, subject_id=focus_subject_id
            )

        return StudentLearningStateRead(
            student_id=student_id,
            as_of=now,
            available_subjects=available_subjects,
            focus_subject_id=focus_subject_id,
            current_action=current_action,
            mastery_summary=mastery_summary,
            priority_targets=priority_targets,
            active_learning=active_learning,
            verified_root_causes=verified_root_causes,
            repair=repair_state,
            review=review_state,
            assignments=assignment_state,
            today_plan=today_plan,
            latest_feedback=latest_feedback,
            class_contexts=class_contexts,
        )

    def _resolve_available_subjects(
        self, student_id: UUID
    ) -> list[StudentLearningSubjectRead]:
        """Derive subjects genuinely related to the student across evidence, mastery, assignments, goals."""
        subject_ids: set[UUID] = set()

        # 1. LearningEvidenceEvent
        evidence_sids = self.session.scalars(
            select(LearningEvidenceEvent.subject_id).where(
                LearningEvidenceEvent.student_id == student_id
            )
        )
        subject_ids.update(evidence_sids)

        # 2. StudentProblemTypeMastery
        pt_mastery_sids = self.session.scalars(
            select(Chapter.subject_id)
            .join(Topic, Topic.chapter_id == Chapter.id)
            .join(ProblemType, ProblemType.topic_id == Topic.id)
            .join(
                StudentProblemTypeMastery,
                StudentProblemTypeMastery.problem_type_id == ProblemType.id,
            )
            .where(StudentProblemTypeMastery.student_id == student_id)
        )
        subject_ids.update(pt_mastery_sids)

        # 3. StudentConceptMastery
        concept_mastery_sids = self.session.scalars(
            select(Concept.subject_id)
            .join(
                StudentConceptMastery,
                StudentConceptMastery.concept_id == Concept.id,
            )
            .where(StudentConceptMastery.student_id == student_id)
        )
        subject_ids.update(concept_mastery_sids)

        # 4. Assignment JOIN StudentAssignment
        assignment_sids = self.session.scalars(
            select(Assignment.subject_id)
            .join(
                StudentAssignment,
                StudentAssignment.assignment_id == Assignment.id,
            )
            .where(StudentAssignment.student_id == student_id)
        )
        subject_ids.update(assignment_sids)

        # 5. Active enrollment TeachingPlan
        enrollment_sids = self.session.scalars(
            select(TeachingPlan.subject_id)
            .join(
                StudentEnrollment,
                StudentEnrollment.classroom_id == TeachingPlan.classroom_id,
            )
            .where(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                TeachingPlan.status == TeachingPlanStatus.ACTIVE,
            )
        )
        subject_ids.update(enrollment_sids)

        # 6. AcademicGoal subject targets
        goal_sids = self.session.scalars(
            select(SubjectGoal.subject_id)
            .join(AcademicGoal, AcademicGoal.id == SubjectGoal.academic_goal_id)
            .where(
                AcademicGoal.student_id == student_id,
                AcademicGoal.status == AcademicGoalStatus.ACTIVE,
            )
        )
        subject_ids.update(goal_sids)

        # 7. Adaptive repair sessions
        repair_sids = self.session.scalars(
            select(AdaptiveRepairSession.subject_id).where(
                AdaptiveRepairSession.student_id == student_id
            )
        )
        subject_ids.update(repair_sids)

        # 8. Root cause diagnoses
        diagnosis_sids = self.session.scalars(
            select(RootCauseDiagnosis.subject_id).where(
                RootCauseDiagnosis.student_id == student_id
            )
        )
        subject_ids.update(diagnosis_sids)

        # 9. PracticeSession
        practice_sids = self.session.scalars(
            select(PracticeSession.subject_id).where(
                PracticeSession.student_id == student_id
            )
        )
        subject_ids.update(practice_sids)

        # 10. ReviewSchedule
        rev_pt_sids = self.session.scalars(
            select(Chapter.subject_id)
            .join(Topic, Topic.chapter_id == Chapter.id)
            .join(ProblemType, ProblemType.topic_id == Topic.id)
            .join(ReviewSchedule, ReviewSchedule.problem_type_id == ProblemType.id)
            .where(ReviewSchedule.student_id == student_id)
        )
        subject_ids.update(rev_pt_sids)

        rev_concept_sids = self.session.scalars(
            select(Concept.subject_id)
            .join(ReviewSchedule, ReviewSchedule.concept_id == Concept.id)
            .where(ReviewSchedule.student_id == student_id)
        )
        subject_ids.update(rev_concept_sids)

        # 11. StudyTask
        task_sids = self.session.scalars(
            select(StudyTask.subject_id)
            .join(StudyPlan, StudyPlan.id == StudyTask.study_plan_id)
            .where(
                StudyPlan.student_id == student_id,
                StudyTask.subject_id.is_not(None),
            )
        )
        subject_ids.update(task_sids)

        if not subject_ids:
            return []

        subjects = list(
            self.session.scalars(
                select(Subject)
                .where(Subject.id.in_(subject_ids))
                .order_by(Subject.name.asc(), Subject.code.asc(), Subject.id.asc())
            )
        )
        return [
            StudentLearningSubjectRead(id=s.id, code=s.code, name=s.name)
            for s in subjects
        ]

    def _resolve_focus_subject(
        self,
        student_id: UUID,
        available_subjects: list[StudentLearningSubjectRead],
        *,
        now: datetime,
    ) -> UUID | None:
        """Deterministically determine focus subject when none is explicitly requested."""
        if not available_subjects:
            return None

        # 1. ACTIVE AdaptiveRepairSession subject
        active_repair = self.session.scalar(
            select(AdaptiveRepairSession)
            .where(
                AdaptiveRepairSession.student_id == student_id,
                AdaptiveRepairSession.status == AdaptiveRepairStatus.ACTIVE,
                AdaptiveRepairSession.outcome == AdaptiveRepairOutcome.PENDING,
            )
            .order_by(
                AdaptiveRepairSession.created_at.desc(),
                AdaptiveRepairSession.repair_cycle_index.desc(),
                AdaptiveRepairSession.id.asc(),
            )
        )
        if active_repair is not None:
            return active_repair.subject_id

        # 2. ACTIVE RootCauseVerification diagnosis subject
        active_ver = self.session.execute(
            select(RootCauseDiagnosis.subject_id)
            .join(
                RootCauseVerification,
                RootCauseVerification.diagnosis_id == RootCauseDiagnosis.id,
            )
            .where(
                RootCauseDiagnosis.student_id == student_id,
                RootCauseVerification.status == RootCauseVerificationStatus.ACTIVE,
            )
            .order_by(
                RootCauseVerification.created_at.desc(),
                RootCauseVerification.id.asc(),
            )
        ).first()
        if active_ver is not None:
            return active_ver[0]

        # 3. IN_PROGRESS assignment subject
        in_prog_assign = self.session.execute(
            select(Assignment.subject_id)
            .join(
                StudentAssignment,
                StudentAssignment.assignment_id == Assignment.id,
            )
            .where(
                StudentAssignment.student_id == student_id,
                StudentAssignment.status == StudentAssignmentStatus.IN_PROGRESS,
                Assignment.status == AssignmentStatus.PUBLISHED,
            )
            .order_by(
                (Assignment.due_at.is_not(None) & (Assignment.due_at < now)).desc(),
                Assignment.due_at.asc().nullslast(),
                StudentAssignment.assigned_at.asc(),
                Assignment.id.asc(),
            )
        ).first()
        if in_prog_assign is not None:
            return in_prog_assign[0]

        # 4. Latest LearningEvidenceEvent subject
        latest_evidence = self.session.scalar(
            select(LearningEvidenceEvent.subject_id)
            .where(LearningEvidenceEvent.student_id == student_id)
            .order_by(
                LearningEvidenceEvent.occurred_at.desc(),
                LearningEvidenceEvent.id.asc(),
            )
        )
        if latest_evidence is not None:
            return latest_evidence

        # 5. Active TeachingPlan subject from enrolled classroom
        active_tp = self.session.scalar(
            select(TeachingPlan.subject_id)
            .join(
                StudentEnrollment,
                StudentEnrollment.classroom_id == TeachingPlan.classroom_id,
            )
            .where(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                TeachingPlan.status == TeachingPlanStatus.ACTIVE,
            )
            .order_by(TeachingPlan.created_at.desc(), TeachingPlan.id.asc())
        )
        if active_tp is not None:
            return active_tp

        # 6. Active AcademicGoal subject
        active_goal_subject = self.session.scalar(
            select(SubjectGoal.subject_id)
            .join(AcademicGoal, AcademicGoal.id == SubjectGoal.academic_goal_id)
            .where(
                AcademicGoal.student_id == student_id,
                AcademicGoal.status == AcademicGoalStatus.ACTIVE,
            )
            .order_by(
                AcademicGoal.created_at.desc(),
                SubjectGoal.priority.asc().nullslast(),
                SubjectGoal.id.asc(),
            )
        )
        if active_goal_subject is not None:
            return active_goal_subject

        # 7. First available subject deterministically
        return available_subjects[0].id

    def _resolve_class_contexts(
        self, student_id: UUID, focus_subject_id: UUID | None
    ) -> list[StudentClassContextRead]:
        if focus_subject_id is None:
            return []

        rows = self.session.execute(
            select(Classroom.id, Classroom.name, TeachingPlan.id)
            .join(
                StudentEnrollment,
                StudentEnrollment.classroom_id == Classroom.id,
            )
            .outerjoin(
                TeachingPlan,
                (TeachingPlan.classroom_id == Classroom.id)
                & (TeachingPlan.subject_id == focus_subject_id)
                & (TeachingPlan.status == TeachingPlanStatus.ACTIVE),
            )
            .where(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            )
            .order_by(Classroom.name.asc(), Classroom.id.asc())
        ).all()

        return [
            StudentClassContextRead(
                classroom_id=row[0],
                classroom_name=row[1],
                teaching_plan_id=row[2],
            )
            for row in rows
        ]

    def _get_active_repair(
        self, student_id: UUID, focus_subject_id: UUID | None
    ) -> AdaptiveRepairSession | None:
        if focus_subject_id is None:
            return None

        stmt = select(AdaptiveRepairSession).where(
            AdaptiveRepairSession.student_id == student_id,
            AdaptiveRepairSession.status == AdaptiveRepairStatus.ACTIVE,
            AdaptiveRepairSession.outcome == AdaptiveRepairOutcome.PENDING,
            AdaptiveRepairSession.subject_id == focus_subject_id,
        ).order_by(
            AdaptiveRepairSession.created_at.desc(),
            AdaptiveRepairSession.repair_cycle_index.desc(),
            AdaptiveRepairSession.id.asc(),
        )
        return self.session.scalar(stmt)

    def _get_active_verification(
        self, student_id: UUID, focus_subject_id: UUID | None
    ) -> tuple[RootCauseVerification | None, RootCauseDiagnosis | None]:
        if focus_subject_id is None:
            return None, None

        stmt = (
            select(RootCauseVerification, RootCauseDiagnosis)
            .join(
                RootCauseDiagnosis,
                RootCauseDiagnosis.id == RootCauseVerification.diagnosis_id,
            )
            .where(
                RootCauseDiagnosis.student_id == student_id,
                RootCauseDiagnosis.subject_id == focus_subject_id,
                RootCauseVerification.status == RootCauseVerificationStatus.ACTIVE,
            )
            .order_by(
                RootCauseVerification.created_at.desc(),
                RootCauseVerification.id.asc(),
            )
        )
        row = self.session.execute(stmt).first()
        if row is None:
            return None, None
        return row[0], row[1]

    def _get_in_progress_assignment(
        self, student_id: UUID, focus_subject_id: UUID | None, *, now: datetime
    ) -> tuple[StudentAssignment | None, Assignment | None]:
        if focus_subject_id is None:
            return None, None

        stmt = (
            select(StudentAssignment, Assignment)
            .join(Assignment, Assignment.id == StudentAssignment.assignment_id)
            .where(
                StudentAssignment.student_id == student_id,
                Assignment.subject_id == focus_subject_id,
                StudentAssignment.status == StudentAssignmentStatus.IN_PROGRESS,
                Assignment.status == AssignmentStatus.PUBLISHED,
            )
            .order_by(
                (Assignment.due_at.is_not(None) & (Assignment.due_at < now)).desc(),
                Assignment.due_at.asc().nullslast(),
                StudentAssignment.assigned_at.asc(),
                Assignment.id.asc(),
            )
        )
        row = self.session.execute(stmt).first()
        if row is None:
            return None, None
        return row[0], row[1]

    def _get_overdue_assignment(
        self, student_id: UUID, focus_subject_id: UUID | None, *, now: datetime
    ) -> tuple[StudentAssignment | None, Assignment | None]:
        if focus_subject_id is None:
            return None, None

        stmt = (
            select(StudentAssignment, Assignment)
            .join(Assignment, Assignment.id == StudentAssignment.assignment_id)
            .where(
                StudentAssignment.student_id == student_id,
                Assignment.subject_id == focus_subject_id,
                StudentAssignment.status == StudentAssignmentStatus.NOT_STARTED,
                Assignment.status == AssignmentStatus.PUBLISHED,
                Assignment.due_at.is_not(None),
                Assignment.due_at < now,
            )
            .order_by(
                Assignment.due_at.asc(),
                StudentAssignment.assigned_at.asc(),
                Assignment.id.asc(),
            )
        )
        row = self.session.execute(stmt).first()
        if row is None:
            return None, None
        return row[0], row[1]

    def _get_active_practice(
        self, student_id: UUID, focus_subject_id: UUID | None
    ) -> PracticeSession | None:
        if focus_subject_id is None:
            return None

        stmt = (
            select(PracticeSession)
            .where(
                PracticeSession.student_id == student_id,
                PracticeSession.subject_id == focus_subject_id,
                PracticeSession.status == PracticeSessionStatus.ACTIVE,
                PracticeSession.session_type.notin_(
                    [
                        PracticeSessionType.ROOT_CAUSE_VERIFICATION,
                        PracticeSessionType.REPAIR,
                    ]
                ),
            )
            .order_by(PracticeSession.created_at.desc(), PracticeSession.id.asc())
        )
        return self.session.scalar(stmt)

    def _resolve_review_state(
        self, student_id: UUID, focus_subject_id: UUID | None, *, now: datetime
    ) -> StudentReviewStateRead:
        if focus_subject_id is None:
            return StudentReviewStateRead(due_now_count=0, upcoming_count=0, due_targets=[])

        review_svc = ReviewScheduleService(self.session)
        due_schedules = review_svc.get_due_schedules(
            student_id, subject_id=focus_subject_id, as_of=now
        )

        upcoming_stmt = select(func.count(ReviewSchedule.id)).where(
            ReviewSchedule.student_id == student_id,
            ReviewSchedule.next_review_at > now,
            ReviewSchedule.next_review_at <= now + timedelta(days=3),
            or_(
                ReviewSchedule.problem_type_id.in_(
                    select(ProblemType.id)
                    .join(Topic, Topic.id == ProblemType.topic_id)
                    .join(Chapter, Chapter.id == Topic.chapter_id)
                    .where(Chapter.subject_id == focus_subject_id)
                ),
                ReviewSchedule.concept_id.in_(
                    select(Concept.id).where(Concept.subject_id == focus_subject_id)
                ),
            ),
        )
        upcoming_count = self.session.scalar(upcoming_stmt) or 0

        # Batch resolve target names/codes for due schedules
        pt_ids = {s.problem_type_id for s in due_schedules if s.problem_type_id is not None}
        c_ids = {s.concept_id for s in due_schedules if s.concept_id is not None}
        pt_map = self._batch_get_problem_types(pt_ids)
        c_map = self._batch_get_concepts(c_ids)

        due_targets: list[StudentReviewTargetRead] = []
        for s in due_schedules:
            if s.problem_type_id is not None:
                pt = pt_map.get(s.problem_type_id)
                target_name = pt.name if pt else "Unknown Problem Type"
                target_code = pt.code if pt else ""
                target_type = "PROBLEM_TYPE"
            else:
                c = c_map.get(s.concept_id) if s.concept_id else None
                target_name = c.name if c else "Unknown Concept"
                target_code = c.code if c else ""
                target_type = "CONCEPT"

            due_targets.append(
                StudentReviewTargetRead(
                    schedule_id=s.id,
                    target_type=target_type,
                    problem_type_id=s.problem_type_id,
                    concept_id=s.concept_id,
                    target_name=target_name,
                    target_code=target_code,
                    next_review_at=s.next_review_at,
                    review_interval_days=s.review_interval_days,
                    review_count=s.review_count,
                    last_review_result=s.last_review_result,
                )
            )

        return StudentReviewStateRead(
            due_now_count=len(due_schedules),
            upcoming_count=upcoming_count,
            due_targets=due_targets,
        )

    def _filter_today_tasks_for_subject(
        self, tasks: list[StudyTaskRead], focus_subject_id: UUID
    ) -> list[StudyTaskRead]:
        """Filter today's tasks strictly for focus_subject_id, resolving subjects for null-subject tasks without N+1.
        
        Priority:
        1. task.subject_id if present (stored explicit subject wins)
        2. if subject_id is None:
           - problem_type_id -> ProblemType -> Topic -> Chapter -> Chapter.subject_id
           - concept_id -> Concept.subject_id
           - if both present and resolve to different subjects: exclude task (no guessing)
           - if neither resolves or both targets null: UNKNOWN -> exclude task
        3. Include task only if resolved_subject_id == focus_subject_id
        """
        # 1. Collect targets for batch querying to avoid N+1
        null_sub_pt_ids: set[UUID] = set()
        null_sub_concept_ids: set[UUID] = set()
        for t in tasks:
            if t.subject_id is None:
                if t.problem_type_id is not None:
                    null_sub_pt_ids.add(t.problem_type_id)
                if t.concept_id is not None:
                    null_sub_concept_ids.add(t.concept_id)

        pt_subject_map: dict[UUID, UUID] = {}
        if null_sub_pt_ids:
            pt_rows = self.session.execute(
                select(ProblemType.id, Chapter.subject_id)
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .where(ProblemType.id.in_(null_sub_pt_ids))
            ).all()
            pt_subject_map = {row[0]: row[1] for row in pt_rows}

        concept_subject_map: dict[UUID, UUID] = {}
        if null_sub_concept_ids:
            c_rows = self.session.execute(
                select(Concept.id, Concept.subject_id)
                .where(Concept.id.in_(null_sub_concept_ids))
            ).all()
            concept_subject_map = {row[0]: row[1] for row in c_rows}

        filtered: list[StudyTaskRead] = []
        for t in tasks:
            if t.subject_id is not None:
                resolved_subject_id = t.subject_id
            else:
                pt_sub = pt_subject_map.get(t.problem_type_id) if t.problem_type_id else None
                c_sub = concept_subject_map.get(t.concept_id) if t.concept_id else None

                if pt_sub is not None and c_sub is not None:
                    if pt_sub != c_sub:
                        logger.warning(
                            "StudyTask %s has conflicting target subjects (pt=%s, concept=%s); excluding",
                            t.id,
                            pt_sub,
                            c_sub,
                        )
                        resolved_subject_id = None
                    else:
                        resolved_subject_id = pt_sub
                elif pt_sub is not None:
                    resolved_subject_id = pt_sub
                elif c_sub is not None:
                    resolved_subject_id = c_sub
                else:
                    resolved_subject_id = None

            if resolved_subject_id == focus_subject_id:
                filtered.append(t)

        return filtered

    def _resolve_today_plan_snapshot(
        self, student_id: UUID, focus_subject_id: UUID | None, *, now: datetime
    ) -> StudyDayRead | None:
        plan_svc = StudyPlanService(self.session)
        snapshot = plan_svc.get_today_plan_snapshot(student_id, as_of=now.date())
        if snapshot is None:
            return None

        if focus_subject_id is not None:
            filtered_tasks = self._filter_today_tasks_for_subject(
                snapshot.tasks, focus_subject_id
            )
            total_estimated = sum(t.estimated_duration_minutes for t in filtered_tasks)
            completed_count = sum(
                1 for t in filtered_tasks if t.status == StudyTaskStatus.COMPLETED
            )
            return StudyDayRead(
                date=snapshot.date,
                available_daily_minutes=snapshot.available_daily_minutes,
                total_estimated_minutes=total_estimated,
                tasks=filtered_tasks,
                completed_count=completed_count,
                total_count=len(filtered_tasks),
                days_to_exam=snapshot.days_to_exam,
                notice=snapshot.notice,
                explanation=None,
            )
        return snapshot

    def _resolve_priority_targets(
        self, student_id: UUID, focus_subject_id: UUID | None
    ) -> list[StudentPriorityTargetRead]:
        if focus_subject_id is None:
            return []

        priority_svc = LearningPriorityService(self.session)
        priorities = priority_svc.get_priorities(
            student_id, focus_subject_id, limit=5
        )
        if not priorities:
            return []

        pt_ids = {p.problem_type_id for p in priorities if p.problem_type_id is not None}
        c_ids = {p.concept_id for p in priorities if p.concept_id is not None}
        pt_map = self._batch_get_problem_types(pt_ids)
        c_map = self._batch_get_concepts(c_ids)

        targets: list[StudentPriorityTargetRead] = []
        for p in priorities:
            if p.problem_type_id is not None:
                pt = pt_map.get(p.problem_type_id)
                target_name = pt.name if pt else "Unknown Problem Type"
                target_code = pt.code if pt else ""
            else:
                c = c_map.get(p.concept_id) if p.concept_id else None
                target_name = c.name if c else "Unknown Concept"
                target_code = c.code if c else ""

            targets.append(
                StudentPriorityTargetRead(
                    target_type=p.target_type,
                    problem_type_id=p.problem_type_id,
                    concept_id=p.concept_id,
                    target_name=target_name,
                    target_code=target_code,
                    reason_code=p.reason_code,
                    priority_score=p.priority_score,
                    mastery_score=p.mastery_score,
                    confidence=p.confidence,
                    desired_difficulty=p.desired_difficulty,
                )
            )
        return targets

    def _determine_current_action(
        self,
        *,
        focus_subject_id: UUID | None,
        active_repair: AdaptiveRepairSession | None,
        active_verification: RootCauseVerification | None,
        active_verification_diag: RootCauseDiagnosis | None,
        in_progress_assignment: StudentAssignment | None,
        in_prog_assign_model: Assignment | None,
        overdue_assignment: StudentAssignment | None,
        overdue_assign_model: Assignment | None,
        active_practice: PracticeSession | None,
        review_state: StudentReviewStateRead,
        today_plan: StudyDayRead | None,
        priority_targets: list[StudentPriorityTargetRead],
    ) -> StudentCurrentActionRead:
        """Evaluate deterministic precedence state machine."""
        # 1. CONTINUE_REPAIR
        if active_repair is not None:
            return StudentCurrentActionRead(
                action_type=StudentCurrentActionType.CONTINUE_REPAIR,
                subject_id=active_repair.subject_id,
                resource_id=active_repair.id,
                adaptive_repair_session_id=active_repair.id,
                practice_session_id=active_repair.practice_session_id,
                verification_id=active_repair.verification_id,
                target_type=active_repair.target_type.value,
                problem_type_id=active_repair.target_problem_type_id,
                concept_id=active_repair.target_concept_id,
                target_name=active_repair.target_name,
                target_code=active_repair.target_code,
                reason_code="ACTIVE_REPAIR",
                repair_cycle_index=active_repair.repair_cycle_index,
                phase=active_repair.phase.value,
            )

        # 2. CONTINUE_VERIFICATION
        if active_verification is not None and active_verification_diag is not None:
            first_target = None
            if active_verification.targets:
                first_target = active_verification.targets[0]

            t_type = first_target.target_type.value if first_target else None
            t_pt_id = first_target.target_problem_type_id if first_target else None
            t_c_id = first_target.target_concept_id if first_target else None

            target_name = None
            target_code = None
            if t_pt_id:
                pt = self.session.get(ProblemType, t_pt_id)
                if pt:
                    target_name, target_code = pt.name, pt.code
            elif t_c_id:
                c = self.session.get(Concept, t_c_id)
                if c:
                    target_name, target_code = c.name, c.code

            return StudentCurrentActionRead(
                action_type=StudentCurrentActionType.CONTINUE_VERIFICATION,
                subject_id=active_verification_diag.subject_id,
                resource_id=active_verification.id,
                verification_id=active_verification.id,
                practice_session_id=active_verification.practice_session_id,
                target_type=t_type,
                problem_type_id=t_pt_id,
                concept_id=t_c_id,
                target_name=target_name,
                target_code=target_code,
                reason_code="ACTIVE_VERIFICATION",
            )

        # 3. CONTINUE_ASSIGNMENT
        if in_progress_assignment is not None and in_prog_assign_model is not None:
            return StudentCurrentActionRead(
                action_type=StudentCurrentActionType.CONTINUE_ASSIGNMENT,
                subject_id=in_prog_assign_model.subject_id,
                resource_id=in_progress_assignment.id,
                assignment_id=in_prog_assign_model.id,
                reason_code="ASSIGNMENT_IN_PROGRESS",
            )

        # 4. COMPLETE_OVERDUE_ASSIGNMENT
        if overdue_assignment is not None and overdue_assign_model is not None:
            return StudentCurrentActionRead(
                action_type=StudentCurrentActionType.COMPLETE_OVERDUE_ASSIGNMENT,
                subject_id=overdue_assign_model.subject_id,
                resource_id=overdue_assignment.id,
                assignment_id=overdue_assign_model.id,
                reason_code="ASSIGNMENT_OVERDUE",
            )

        # 5. CONTINUE_PRACTICE
        if active_practice is not None:
            return StudentCurrentActionRead(
                action_type=StudentCurrentActionType.CONTINUE_PRACTICE,
                subject_id=active_practice.subject_id,
                resource_id=active_practice.id,
                practice_session_id=active_practice.id,
                target_type=active_practice.session_type.value,
                reason_code="ACTIVE_PRACTICE",
            )

        # 6. REVIEW_DUE
        if review_state.due_targets:
            top_review = review_state.due_targets[0]
            return StudentCurrentActionRead(
                action_type=StudentCurrentActionType.REVIEW_DUE,
                subject_id=focus_subject_id,
                resource_id=top_review.schedule_id,
                target_type=top_review.target_type,
                problem_type_id=top_review.problem_type_id,
                concept_id=top_review.concept_id,
                target_name=top_review.target_name,
                target_code=top_review.target_code,
                reason_code="REVIEW_DUE",
            )

        # 7. TODAY_TASK
        if today_plan and today_plan.tasks:
            pending_tasks = [
                t for t in today_plan.tasks if t.status == StudyTaskStatus.PENDING
            ]
            if pending_tasks:
                top_task = pending_tasks[0]
                t_type = (
                    "PROBLEM_TYPE"
                    if top_task.problem_type_id
                    else ("CONCEPT" if top_task.concept_id else None)
                )
                t_name = top_task.problem_type_name or top_task.concept_name
                r_code = top_task.reason_code or "TODAY_STUDY_TASK"
                return StudentCurrentActionRead(
                    action_type=StudentCurrentActionType.TODAY_TASK,
                    subject_id=top_task.subject_id or focus_subject_id,
                    resource_id=top_task.id,
                    study_task_id=top_task.id,
                    target_type=t_type,
                    problem_type_id=top_task.problem_type_id,
                    concept_id=top_task.concept_id,
                    target_name=t_name,
                    reason_code=r_code,
                )

        # 8. LEARNING_PRIORITY
        if priority_targets:
            top_priority = priority_targets[0]
            return StudentCurrentActionRead(
                action_type=StudentCurrentActionType.LEARNING_PRIORITY,
                subject_id=focus_subject_id,
                target_type=top_priority.target_type,
                problem_type_id=top_priority.problem_type_id,
                concept_id=top_priority.concept_id,
                target_name=top_priority.target_name,
                target_code=top_priority.target_code,
                reason_code=top_priority.reason_code,
            )

        # 9. IDLE
        return StudentCurrentActionRead(
            action_type=StudentCurrentActionType.IDLE,
            reason_code="IDLE",
        )

    def _build_active_learning(
        self,
        *,
        active_repair: AdaptiveRepairSession | None,
        active_verification: RootCauseVerification | None,
        in_prog_assign_model: Assignment | None,
        active_practice: PracticeSession | None,
    ) -> StudentActiveLearningRead:
        practice_id = None
        practice_type = None

        if active_repair is not None:
            practice_id = active_repair.practice_session_id
            practice_type = PracticeSessionType.REPAIR.value
        elif active_verification is not None:
            practice_id = active_verification.practice_session_id
            practice_type = PracticeSessionType.ROOT_CAUSE_VERIFICATION.value
        elif active_practice is not None:
            practice_id = active_practice.id
            practice_type = active_practice.session_type.value

        return StudentActiveLearningRead(
            practice_session_id=practice_id,
            practice_session_type=practice_type,
            verification_id=active_verification.id if active_verification else None,
            adaptive_repair_session_id=active_repair.id if active_repair else None,
            assignment_id=in_prog_assign_model.id if in_prog_assign_model else None,
        )

    def _build_repair_state(
        self, active_repair: AdaptiveRepairSession | None
    ) -> StudentRepairStateRead | None:
        if active_repair is None:
            return None

        return StudentRepairStateRead(
            adaptive_repair_session_id=active_repair.id,
            practice_session_id=active_repair.practice_session_id,
            subject_id=active_repair.subject_id,
            verification_target_id=active_repair.verification_target_id,
            diagnosis_id=active_repair.diagnosis_id,
            status=active_repair.status.value,
            phase=active_repair.phase.value,
            target_type=active_repair.target_type.value,
            target_concept_id=active_repair.target_concept_id,
            target_problem_type_id=active_repair.target_problem_type_id,
            misconception_definition_id=active_repair.misconception_definition_id,
            target_name=active_repair.target_name,
            target_code=active_repair.target_code,
            repair_cycle_index=active_repair.repair_cycle_index,
            current_difficulty=active_repair.current_difficulty,
            target_exit_difficulty=active_repair.target_exit_difficulty,
            attempted_count=active_repair.attempted_count,
            correct_count=active_repair.correct_count,
            max_questions=active_repair.max_questions,
        )

    def _resolve_assignment_state(
        self, student_id: UUID, focus_subject_id: UUID | None, *, now: datetime
    ) -> StudentAssignmentStateRead:
        if focus_subject_id is None:
            return StudentAssignmentStateRead(
                overdue_count=0, in_progress_count=0, pending_count=0, upcoming=[]
            )

        stmt = (
            select(StudentAssignment, Assignment)
            .join(Assignment, Assignment.id == StudentAssignment.assignment_id)
            .where(
                StudentAssignment.student_id == student_id,
                Assignment.subject_id == focus_subject_id,
                Assignment.status == AssignmentStatus.PUBLISHED,
            )
        )
        rows = self.session.execute(stmt).all()

        overdue_count = 0
        in_progress_count = 0
        pending_count = 0
        actionable_items: list[tuple[StudentAssignment, Assignment, bool]] = []

        for sa, a in rows:
            due_at_utc = _ensure_utc(a.due_at)
            is_overdue = due_at_utc is not None and due_at_utc < now
            if sa.status == StudentAssignmentStatus.IN_PROGRESS:
                in_progress_count += 1
                if is_overdue:
                    overdue_count += 1
                actionable_items.append((sa, a, is_overdue))
            elif sa.status == StudentAssignmentStatus.NOT_STARTED:
                pending_count += 1
                if is_overdue:
                    overdue_count += 1
                actionable_items.append((sa, a, is_overdue))

        # Sort actionable items:
        # 1. overdue first
        # 2. IN_PROGRESS before NOT_STARTED
        # 3. due_at ASC NULLS LAST
        # 4. assignment.created_at ASC
        # 5. assignment.id ASC
        def sort_key(item: tuple[StudentAssignment, Assignment, bool]):
            sa, a, is_overdue = item
            is_in_progress = sa.status == StudentAssignmentStatus.IN_PROGRESS
            due_at_val = _ensure_utc(a.due_at) or datetime.max.replace(tzinfo=timezone.utc)
            created_at_val = _ensure_utc(a.created_at)
            return (
                0 if is_overdue else 1,
                0 if is_in_progress else 1,
                due_at_val,
                created_at_val,
                a.id,
            )

        actionable_items.sort(key=sort_key)
        top_upcoming = actionable_items[:5]

        upcoming_reads = [
            StudentAssignmentStateItemRead(
                assignment_id=a.id,
                student_assignment_id=sa.id,
                classroom_id=a.classroom_id,
                subject_id=a.subject_id,
                title=a.title,
                status=sa.status.value,
                start_at=a.start_at,
                due_at=a.due_at,
                score=sa.score,
                is_overdue=is_overdue,
            )
            for sa, a, is_overdue in top_upcoming
        ]

        return StudentAssignmentStateRead(
            overdue_count=overdue_count,
            in_progress_count=in_progress_count,
            pending_count=pending_count,
            upcoming=upcoming_reads,
        )

    def _resolve_mastery_summary(
        self, student_id: UUID, focus_subject_id: UUID | None, *, now: datetime
    ) -> StudentMasterySummaryRead:
        if focus_subject_id is None:
            return StudentMasterySummaryRead()

        # Problem Type masteries for focus subject
        pt_stmt = (
            select(StudentProblemTypeMastery, ProblemType)
            .join(ProblemType, ProblemType.id == StudentProblemTypeMastery.problem_type_id)
            .join(Topic, Topic.id == ProblemType.topic_id)
            .join(Chapter, Chapter.id == Topic.chapter_id)
            .where(
                StudentProblemTypeMastery.student_id == student_id,
                Chapter.subject_id == focus_subject_id,
            )
        )
        pt_rows = self.session.execute(pt_stmt).all()

        pt_started_count = len(pt_rows)
        mastered_pt_count = 0
        weak_pt_count = 0
        total_pt_score = 0.0
        weak_pt_candidates: list[StudentWeakTargetRead] = []

        for mastery, pt in pt_rows:
            total_pt_score += mastery.mastery_score
            state = derive_mastery_state(
                mastery_score=mastery.mastery_score,
                confidence=mastery.confidence,
                attempt_count=mastery.attempt_count,
                last_practiced_at=_ensure_utc(mastery.last_practiced_at),
                as_of=now,
            )
            if state == DerivedMasteryState.MASTERED:
                mastered_pt_count += 1
            elif state == DerivedMasteryState.WEAK:
                weak_pt_count += 1
                weak_pt_candidates.append(
                    StudentWeakTargetRead(
                        problem_type_id=pt.id,
                        target_name=pt.name,
                        target_code=pt.code,
                        name=pt.name,
                        code=pt.code,
                        mastery_score=mastery.mastery_score,
                        confidence=mastery.confidence,
                        last_practiced_at=_ensure_utc(mastery.last_practiced_at),
                    )
                )

        avg_pt_mastery = (
            round(total_pt_score / pt_started_count, 4) if pt_started_count > 0 else None
        )

        # Concept masteries for focus subject
        c_stmt = (
            select(StudentConceptMastery, Concept)
            .join(Concept, Concept.id == StudentConceptMastery.concept_id)
            .where(
                StudentConceptMastery.student_id == student_id,
                Concept.subject_id == focus_subject_id,
            )
        )
        c_rows = self.session.execute(c_stmt).all()

        c_started_count = len(c_rows)
        mastered_c_count = 0
        weak_c_count = 0
        total_c_score = 0.0
        weak_c_candidates: list[StudentWeakTargetRead] = []

        for mastery, c in c_rows:
            total_c_score += mastery.mastery_score
            state = derive_mastery_state(
                mastery_score=mastery.mastery_score,
                confidence=mastery.confidence,
                attempt_count=mastery.attempt_count,
                last_practiced_at=_ensure_utc(mastery.last_practiced_at),
                as_of=now,
            )
            if state == DerivedMasteryState.MASTERED:
                mastered_c_count += 1
            elif state == DerivedMasteryState.WEAK:
                weak_c_count += 1
                weak_c_candidates.append(
                    StudentWeakTargetRead(
                        concept_id=c.id,
                        target_name=c.name,
                        target_code=c.code,
                        name=c.name,
                        code=c.code,
                        mastery_score=mastery.mastery_score,
                        confidence=mastery.confidence,
                        last_practiced_at=_ensure_utc(mastery.last_practiced_at),
                    )
                )

        avg_c_mastery = (
            round(total_c_score / c_started_count, 4) if c_started_count > 0 else None
        )

        # Sort weak candidates:
        # mastery_score ASC, confidence DESC, last_practiced_at ASC NULLS FIRST, code ASC, id ASC
        def weak_sort_key(t: StudentWeakTargetRead):
            # None last_practiced_at should sort first (NULLS FIRST)
            lp_ts = (
                datetime.min.replace(tzinfo=timezone.utc)
                if t.last_practiced_at is None
                else _ensure_utc(t.last_practiced_at)
            )
            return (
                t.mastery_score,
                -t.confidence,
                lp_ts,
                t.target_code or "",
                str(t.problem_type_id or t.concept_id),
            )

        weak_pt_candidates.sort(key=weak_sort_key)
        weak_c_candidates.sort(key=weak_sort_key)

        return StudentMasterySummaryRead(
            problem_type_started_count=pt_started_count,
            concept_started_count=c_started_count,
            mastered_problem_type_count=mastered_pt_count,
            weak_problem_type_count=weak_pt_count,
            mastered_concept_count=mastered_c_count,
            weak_concept_count=weak_c_count,
            average_problem_type_mastery=avg_pt_mastery,
            average_concept_mastery=avg_c_mastery,
            weak_problem_types=weak_pt_candidates[:5],
            weak_concepts=weak_c_candidates[:5],
        )

    def _resolve_verified_root_causes(
        self, student_id: UUID, focus_subject_id: UUID | None
    ) -> list[StudentVerifiedRootCauseRead]:
        if focus_subject_id is None:
            return []

        stmt = (
            select(RootCauseVerificationTarget, RootCauseVerification, RootCauseDiagnosis)
            .join(
                RootCauseVerification,
                RootCauseVerification.id == RootCauseVerificationTarget.verification_id,
            )
            .join(
                RootCauseDiagnosis,
                RootCauseDiagnosis.id == RootCauseVerification.diagnosis_id,
            )
            .where(
                RootCauseDiagnosis.student_id == student_id,
                RootCauseDiagnosis.subject_id == focus_subject_id,
                RootCauseVerification.status == RootCauseVerificationStatus.COMPLETED,
                RootCauseVerificationTarget.outcome == RootCauseVerificationOutcome.SUPPORTED,
            )
            .order_by(
                RootCauseDiagnosis.created_at.desc(),
                RootCauseDiagnosis.id.desc(),
            )
            .limit(5)
        )
        rows = self.session.execute(stmt).all()
        if not rows:
            return []

        pt_ids = {r[0].target_problem_type_id for r in rows if r[0].target_problem_type_id}
        c_ids = {r[0].target_concept_id for r in rows if r[0].target_concept_id}
        m_ids = {r[0].misconception_definition_id for r in rows if r[0].misconception_definition_id}

        pt_map = self._batch_get_problem_types(pt_ids)
        c_map = self._batch_get_concepts(c_ids)
        m_map = self._batch_get_misconceptions(m_ids)

        reads: list[StudentVerifiedRootCauseRead] = []
        for target, ver, diag in rows:
            target_name = None
            target_code = None

            if target.target_problem_type_id and target.target_problem_type_id in pt_map:
                pt = pt_map[target.target_problem_type_id]
                target_name = pt.name
                target_code = pt.code
            elif target.target_concept_id and target.target_concept_id in c_map:
                c = c_map[target.target_concept_id]
                target_name = c.name
                target_code = c.code
            elif target.misconception_definition_id and target.misconception_definition_id in m_map:
                m = m_map[target.misconception_definition_id]
                target_name = m.name
                target_code = m.code

            reads.append(
                StudentVerifiedRootCauseRead(
                    diagnosis_id=diag.id,
                    verification_id=ver.id,
                    verification_target_id=target.id,
                    target_type=target.target_type.value,
                    concept_id=target.target_concept_id,
                    problem_type_id=target.target_problem_type_id,
                    misconception_definition_id=target.misconception_definition_id,
                    target_name=target_name,
                    target_code=target_code,
                    diagnosis_type=diag.diagnosis_type.value,
                    diagnosis_confidence=diag.confidence,
                    verified_at=ver.completed_at,
                )
            )

        return reads

    def _batch_get_problem_types(self, ids: set[UUID]) -> dict[UUID, ProblemType]:
        if not ids:
            return {}
        pts = self.session.scalars(select(ProblemType).where(ProblemType.id.in_(ids)))
        return {p.id: p for p in pts}

    def _batch_get_concepts(self, ids: set[UUID]) -> dict[UUID, Concept]:
        if not ids:
            return {}
        cs = self.session.scalars(select(Concept).where(Concept.id.in_(ids)))
        return {c.id: c for c in cs}

    def _batch_get_misconceptions(
        self, ids: set[UUID]
    ) -> dict[UUID, MisconceptionDefinition]:
        if not ids:
            return {}
        ms = self.session.scalars(
            select(MisconceptionDefinition).where(MisconceptionDefinition.id.in_(ids))
        )
        return {m.id: m for m in ms}
