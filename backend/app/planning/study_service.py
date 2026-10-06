from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from app.classes.models import EnrollmentStatus, StudentEnrollment
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.planning.study_models import (
    StudyPlan,
    StudyPlanStatus,
    StudyTask,
    StudyTaskReasonCode,
    StudyTaskStatus,
    StudyTaskType,
)
from app.planning.study_policy import CandidateTask, PlanningContext, StudyPlanningPolicy
from app.planning.study_schemas import (
    StudyDayRead,
    StudyPlanRead,
    StudyTaskRead,
)
from app.review.service import ReviewScheduleService
from app.students.goal_models import AcademicGoal, AcademicGoalStatus
from app.students.models import StudentProfile
from app.subjects.models import Subject


class StudyPlanService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.policy = StudyPlanningPolicy()

    def get_or_create_active_plan(
        self,
        student_id: UUID,
        *,
        as_of: date | None = None,
    ) -> StudyPlan:
        current_date = as_of or date.today()
        student = self.session.get(StudentProfile, student_id)
        if student is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile was not found.")

        plan = self.session.scalar(
            select(StudyPlan)
            .where(
                StudyPlan.student_id == student_id,
                StudyPlan.status == StudyPlanStatus.ACTIVE,
            )
            .order_by(StudyPlan.created_at.desc())
        )
        if plan:
            return plan

        # Look up active academic goal
        active_goal = self.session.scalar(
            select(AcademicGoal)
            .where(
                AcademicGoal.student_id == student_id,
                AcademicGoal.status == AcademicGoalStatus.ACTIVE,
            )
            .order_by(AcademicGoal.created_at.desc())
        )

        plan = StudyPlan(
            student_id=student_id,
            academic_goal_id=active_goal.id if active_goal else None,
            start_date=current_date,
            target_date=active_goal.exam_date if active_goal else None,
            status=StudyPlanStatus.ACTIVE,
        )
        self.session.add(plan)
        self.session.flush()
        return plan

    def get_today_plan(
        self,
        student_id: UUID,
        *,
        as_of: date | None = None,
        include_explanation: bool = False,
    ) -> StudyDayRead:
        current_date = as_of or date.today()
        plan = self.get_or_create_active_plan(student_id, as_of=current_date)

        # Check for missed days: mark uncompleted tasks from past days as SKIPPED
        self._skip_past_pending_tasks(plan.id, current_date)

        # Query tasks for current_date
        tasks = self._query_tasks(plan.id, planned_date=current_date)
        if not tasks:
            # If no tasks for today, recalculate
            self.recalculate_study_plan(student_id, as_of=current_date)
            tasks = self._query_tasks(plan.id, planned_date=current_date)

        # Get daily budget
        daily_minutes = self._get_daily_budget(plan)
        total_estimated = sum(t.estimated_duration_minutes for t in tasks)
        completed_count = sum(1 for t in tasks if t.status == StudyTaskStatus.COMPLETED)

        days_to_exam: int | None = None
        if plan.target_date:
            days_to_exam = (plan.target_date - current_date).days

        notice = None
        if days_to_exam is not None and days_to_exam <= 14:
            notice = f"Kỳ thi đến gần (còn {days_to_exam} ngày). Tăng cường luyện đề và mini-test!"

        pt_ids = {t.problem_type_id for t in tasks if t.problem_type_id is not None}
        hierarchy_map = self._get_hierarchy_map(pt_ids)

        explanation = None
        if include_explanation:
            from app.planning.study_explanation_service import StudyPlanExplanationService

            explainer = StudyPlanExplanationService(self.session)
            input_ctx = explainer.build_context(student_id, current_date)
            explanation = explainer.explain_study_plan(input_ctx)

        return StudyDayRead(
            date=current_date,
            available_daily_minutes=daily_minutes,
            total_estimated_minutes=total_estimated,
            tasks=[self._to_task_read(t, hierarchy_map) for t in tasks],
            completed_count=completed_count,
            total_count=len(tasks),
            days_to_exam=days_to_exam,
            notice=notice,
            explanation=explanation,
        )

    def get_today_plan_snapshot(
        self,
        student_id: UUID,
        *,
        as_of: date | None = None,
    ) -> StudyDayRead | None:
        """Strictly read-only query helper for today's study plan snapshot.
        
        Zero DB mutations: does not create plan, does not skip past tasks,
        does not recalculate missing tasks, and does not invoke explanation AI.
        """
        current_date = as_of or date.today()
        plan = self.session.scalar(
            select(StudyPlan)
            .where(
                StudyPlan.student_id == student_id,
                StudyPlan.status == StudyPlanStatus.ACTIVE,
            )
            .order_by(StudyPlan.created_at.desc())
        )
        if plan is None:
            return None

        tasks = self._query_tasks(plan.id, planned_date=current_date)
        daily_minutes = self._get_daily_budget(plan)
        total_estimated = sum(t.estimated_duration_minutes for t in tasks)
        completed_count = sum(1 for t in tasks if t.status == StudyTaskStatus.COMPLETED)

        days_to_exam: int | None = None
        if plan.target_date:
            days_to_exam = (plan.target_date - current_date).days

        notice = None
        if days_to_exam is not None and days_to_exam <= 14:
            notice = f"Kỳ thi đến gần (còn {days_to_exam} ngày). Tăng cường luyện đề và mini-test!"

        pt_ids = {t.problem_type_id for t in tasks if t.problem_type_id is not None}
        hierarchy_map = self._get_hierarchy_map(pt_ids)

        return StudyDayRead(
            date=current_date,
            available_daily_minutes=daily_minutes,
            total_estimated_minutes=total_estimated,
            tasks=[self._to_task_read(t, hierarchy_map) for t in tasks],
            completed_count=completed_count,
            total_count=len(tasks),
            days_to_exam=days_to_exam,
            notice=notice,
            explanation=None,
        )

    def get_today_explanation(
        self,
        student_id: UUID,
        *,
        as_of: date | None = None,
    ):
        from app.planning.study_explanation_service import StudyPlanExplanationService

        current_date = as_of or date.today()
        explainer = StudyPlanExplanationService(self.session)
        input_ctx = explainer.build_context(student_id, current_date)
        return explainer.explain_study_plan(input_ctx)

    def get_study_plan(
        self,
        student_id: UUID,
        *,
        as_of: date | None = None,
    ) -> StudyPlanRead:
        current_date = as_of or date.today()
        plan = self.get_or_create_active_plan(student_id, as_of=current_date)
        self._skip_past_pending_tasks(plan.id, current_date)

        tasks = self._query_tasks(plan.id)
        if not tasks:
            self.recalculate_study_plan(student_id, as_of=current_date)
            tasks = self._query_tasks(plan.id)

        daily_minutes = self._get_daily_budget(plan)
        days_to_exam: int | None = None
        if plan.target_date:
            days_to_exam = (plan.target_date - current_date).days

        completed_tasks = sum(1 for t in tasks if t.status == StudyTaskStatus.COMPLETED)
        pt_ids = {t.problem_type_id for t in tasks if t.problem_type_id is not None}
        hierarchy_map = self._get_hierarchy_map(pt_ids)

        return StudyPlanRead(
            id=plan.id,
            student_id=student_id,
            academic_goal_id=plan.academic_goal_id,
            start_date=plan.start_date,
            target_date=plan.target_date,
            status=plan.status,
            days_to_exam=days_to_exam,
            available_daily_minutes=daily_minutes,
            total_tasks=len(tasks),
            completed_tasks=completed_tasks,
            tasks=[self._to_task_read(t, hierarchy_map) for t in tasks],
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    def recalculate_study_plan(
        self,
        student_id: UUID,
        *,
        as_of: date | None = None,
        horizon_days: int = 7,
    ) -> StudyPlanRead:
        current_date = as_of or date.today()
        plan = self.get_or_create_active_plan(student_id, as_of=current_date)

        # 1. Skip past pending tasks (No giant backlog rule)
        self._skip_past_pending_tasks(plan.id, current_date)

        # 2. Delete future pending tasks (so we can freshly regenerate)
        self.session.execute(
            delete(StudyTask).where(
                StudyTask.study_plan_id == plan.id,
                StudyTask.planned_date >= current_date,
                StudyTask.status == StudyTaskStatus.PENDING,
            )
        )

        # 3. Gather planning inputs
        ctx = self._gather_context(student_id, current_date)

        # 4. Generate candidates & schedule horizon
        candidates = self.policy.generate_candidate_tasks(ctx)
        schedule = self.policy.schedule_horizon(ctx, candidates, horizon_days=horizon_days)

        # 5. Insert newly planned tasks
        for plan_date, daily_candidates in schedule.items():
            for order_idx, candidate in enumerate(daily_candidates):
                task = StudyTask(
                    study_plan_id=plan.id,
                    task_type=candidate.task_type,
                    status=StudyTaskStatus.PENDING,
                    planned_date=plan_date,
                    problem_type_id=candidate.problem_type_id,
                    concept_id=candidate.concept_id,
                    subject_id=candidate.subject_id,
                    estimated_duration_minutes=candidate.estimated_duration_minutes,
                    priority=int(candidate.priority_score),
                    order_index=order_idx,
                    reason_code=candidate.reason_code,
                )
                self.session.add(task)

        # Update target_date if goal changed
        if ctx.exam_date and plan.target_date != ctx.exam_date:
            plan.target_date = ctx.exam_date
        plan.updated_at = datetime.now(timezone.utc)
        self.session.commit()

        return self.get_study_plan(student_id, as_of=current_date)

    def _skip_past_pending_tasks(self, plan_id: UUID, current_date: date) -> None:
        """Enforce No Giant Backlog: past pending tasks are marked SKIPPED."""
        self.session.execute(
            update(StudyTask)
            .where(
                StudyTask.study_plan_id == plan_id,
                StudyTask.planned_date < current_date,
                StudyTask.status == StudyTaskStatus.PENDING,
            )
            .values(status=StudyTaskStatus.SKIPPED)
        )
        self.session.flush()

    def _get_daily_budget(self, plan: StudyPlan) -> int:
        if plan.academic_goal_id:
            goal = self.session.get(AcademicGoal, plan.academic_goal_id)
            if goal and goal.available_daily_minutes > 0:
                return goal.available_daily_minutes
        return 60

    def _gather_context(self, student_id: UUID, current_date: date) -> PlanningContext:
        # Academic goal
        active_goal = self.session.scalar(
            select(AcademicGoal)
            .where(
                AcademicGoal.student_id == student_id,
                AcademicGoal.status == AcademicGoalStatus.ACTIVE,
            )
            .order_by(AcademicGoal.created_at.desc())
        )
        daily_minutes = active_goal.available_daily_minutes if active_goal else 60
        exam_date = active_goal.exam_date if active_goal else None

        target_subjects: list[UUID] = []
        if active_goal and active_goal.subject_goals:
            target_subjects = [sg.subject_id for sg in active_goal.subject_goals]
        if not target_subjects:
            target_subjects = list(self.session.scalars(select(Subject.id).limit(3)))

        # Active teaching plan items for enrolled classrooms
        enrolled_classroom_ids = list(
            self.session.scalars(
                select(StudentEnrollment.classroom_id).where(
                    StudentEnrollment.student_id == student_id,
                    StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                )
            )
        )
        active_pt_ids: list[UUID] = []
        if enrolled_classroom_ids:
            active_pt_ids = list(
                self.session.scalars(
                    select(TeachingPlanItem.problem_type_id)
                    .join(TeachingPlan, TeachingPlan.id == TeachingPlanItem.teaching_plan_id)
                    .where(
                        TeachingPlan.classroom_id.in_(enrolled_classroom_ids),
                        TeachingPlan.status == TeachingPlanStatus.ACTIVE,
                    )
                    .order_by(TeachingPlanItem.priority.desc())
                )
            )

        # Student Problem Type Mastery: weak problem types (mastery < 0.50)
        weak_pt_ids = list(
            self.session.scalars(
                select(StudentProblemTypeMastery.problem_type_id).where(
                    StudentProblemTypeMastery.student_id == student_id,
                    StudentProblemTypeMastery.mastery_score < 0.50,
                )
            )
        )

        # Student Concept Mastery: weak concepts (mastery < 0.60)
        weak_concept_ids = list(
            self.session.scalars(
                select(StudentConceptMastery.concept_id).where(
                    StudentConceptMastery.student_id == student_id,
                    StudentConceptMastery.mastery_score < 0.60,
                )
            )
        )

        # Prerequisite gaps: concepts that are prerequisite to active or weak problem types
        # and have low concept mastery (< 0.60)
        prerequisite_gap_ids: list[UUID] = []
        if weak_concept_ids:
            # Find which of these weak concepts serve as PREREQUISITE in ConceptRelation
            prerequisite_relations = list(
                self.session.scalars(
                    select(ConceptRelation.source_concept_id).where(
                        ConceptRelation.source_concept_id.in_(weak_concept_ids),
                        ConceptRelation.relation_type == RelationType.PREREQUISITE,
                    )
                )
            )
            prerequisite_gap_ids = list(set(prerequisite_relations))

        # Review due
        review_service = ReviewScheduleService(self.session)
        due_schedules = review_service.get_due_schedules(
            student_id,
            as_of=datetime.combine(current_date, datetime.min.time(), tzinfo=timezone.utc),
        )
        due_pt_ids = [s.problem_type_id for s in due_schedules if s.problem_type_id is not None]
        due_c_ids = [s.concept_id for s in due_schedules if s.concept_id is not None]

        return PlanningContext(
            student_id=student_id,
            as_of=current_date,
            available_daily_minutes=daily_minutes,
            exam_date=exam_date,
            target_subjects=target_subjects,
            active_teaching_plan_problem_type_ids=active_pt_ids,
            prerequisite_gap_concept_ids=prerequisite_gap_ids,
            weak_problem_type_ids=weak_pt_ids,
            weak_concept_ids=weak_concept_ids,
            due_review_problem_type_ids=due_pt_ids,
            due_review_concept_ids=due_c_ids,
        )

    def _query_tasks(
        self,
        plan_id: UUID,
        *,
        planned_date: date | None = None,
    ) -> list[StudyTask]:
        stmt = (
            select(StudyTask)
            .options(
                selectinload(StudyTask.problem_type),
                selectinload(StudyTask.concept),
                selectinload(StudyTask.subject),
            )
            .where(StudyTask.study_plan_id == plan_id)
        )
        if planned_date is not None:
            stmt = stmt.where(StudyTask.planned_date == planned_date)
        stmt = stmt.order_by(
            StudyTask.planned_date,
            StudyTask.priority.desc(),
            StudyTask.order_index,
            StudyTask.id,
        )
        return list(self.session.scalars(stmt))

    def _get_hierarchy_map(
        self, problem_type_ids: set[UUID]
    ) -> dict[UUID, tuple[UUID, str, UUID, str]]:
        if not problem_type_ids:
            return {}
        rows = self.session.execute(
            select(ProblemType.id, Topic.id, Topic.name, Chapter.id, Chapter.name)
            .join(Topic, Topic.id == ProblemType.topic_id)
            .join(Chapter, Chapter.id == Topic.chapter_id)
            .where(ProblemType.id.in_(problem_type_ids))
        ).all()
        return {
            row[0]: (row[1], row[2], row[3], row[4])
            for row in rows
        }

    def _to_task_read(
        self,
        task: StudyTask,
        hierarchy_map: dict[UUID, tuple[UUID, str, UUID, str]] | None = None,
    ) -> StudyTaskRead:
        pt_name = task.problem_type.name if task.problem_type else None
        c_name = task.concept.name if task.concept else None
        s_name = task.subject.name if task.subject else None

        topic_id = None
        topic_name = None
        chapter_id = None
        chapter_name = None

        if hierarchy_map and task.problem_type_id in hierarchy_map:
            topic_id, topic_name, chapter_id, chapter_name = hierarchy_map[task.problem_type_id]

        return StudyTaskRead(
            id=task.id,
            study_plan_id=task.study_plan_id,
            task_type=task.task_type,
            status=task.status,
            planned_date=task.planned_date,
            problem_type_id=task.problem_type_id,
            problem_type_name=pt_name,
            concept_id=task.concept_id,
            concept_name=c_name,
            topic_id=topic_id,
            topic_name=topic_name,
            chapter_id=chapter_id,
            chapter_name=chapter_name,
            subject_id=task.subject_id,
            subject_name=s_name,
            estimated_duration_minutes=task.estimated_duration_minutes,
            priority=task.priority,
            order_index=task.order_index,
            reason_code=task.reason_code,
            completed_at=task.completed_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

