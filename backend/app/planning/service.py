import logging
from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.classes.models import Classroom, TeacherClassroom
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, ProblemTypeConcept, Topic
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.planning.schemas import (
    TeachingPlanCreate,
    TeachingPlanItemCreate,
    TeachingPlanItemRead,
    TeachingPlanPatch,
    TeachingPlanRead,
)
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile

logger = logging.getLogger(__name__)


class TeachingPlanService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_plan(
        self, teacher_user_id: UUID, classroom_id: UUID, data: TeachingPlanCreate
    ) -> TeachingPlanRead:
        teacher, classroom = self._verify_teacher_classroom(teacher_user_id, classroom_id)
        self._validate_subject(data.subject_id)
        self._validate_dates(data.start_date, data.target_end_date)
        self._validate_items(data.subject_id, data.items)

        if data.status == TeachingPlanStatus.ACTIVE:
            if not data.items:
                raise ApplicationError(
                    422,
                    "EMPTY_TEACHING_PLAN",
                    "Cannot activate a teaching plan with no items.",
                )
            self._assert_no_active_conflict(classroom_id, data.subject_id)

        plan = TeachingPlan(
            classroom_id=classroom_id,
            subject_id=data.subject_id,
            start_date=data.start_date,
            target_end_date=data.target_end_date,
            status=data.status,
            created_by=teacher_user_id,
        )
        for item in data.items:
            plan.items.append(
                TeachingPlanItem(
                    problem_type_id=item.problem_type_id,
                    learning_outcome_id=item.learning_outcome_id,
                    priority=item.priority,
                    order_index=item.order_index,
                )
            )

        self.session.add(plan)
        self.session.commit()
        self.session.refresh(plan)
        logger.info(
            "Teaching plan created (plan_id=%s, classroom_id=%s, teacher_id=%s, status=%s)",
            plan.id,
            classroom_id,
            teacher.id,
            plan.status.value,
        )
        return self._build_read_model(plan)

    def list_plans(
        self,
        teacher_user_id: UUID,
        classroom_id: UUID,
        *,
        subject_id: UUID | None = None,
        status: TeachingPlanStatus | None = None,
    ) -> list[TeachingPlanRead]:
        self._verify_teacher_classroom(teacher_user_id, classroom_id)
        statement = (
            select(TeachingPlan)
            .options(
                selectinload(TeachingPlan.items).selectinload(TeachingPlanItem.problem_type),
                selectinload(TeachingPlan.items).selectinload(TeachingPlanItem.learning_outcome),
            )
            .where(TeachingPlan.classroom_id == classroom_id)
        )
        if subject_id is not None:
            statement = statement.where(TeachingPlan.subject_id == subject_id)
        if status is not None:
            statement = statement.where(TeachingPlan.status == status)

        statement = statement.order_by(TeachingPlan.created_at.desc(), TeachingPlan.id.desc())
        plans = list(self.session.scalars(statement))
        return [self._build_read_model(plan) for plan in plans]

    def get_plan(self, teacher_user_id: UUID, plan_id: UUID) -> TeachingPlanRead:
        plan = self._get_plan_or_404(plan_id)
        self._verify_teacher_classroom(teacher_user_id, plan.classroom_id)
        return self._build_read_model(plan)

    def patch_plan(
        self, teacher_user_id: UUID, plan_id: UUID, data: TeachingPlanPatch
    ) -> TeachingPlanRead:
        plan = self._get_plan_or_404(plan_id)
        self._verify_teacher_classroom(teacher_user_id, plan.classroom_id)

        if plan.status in {TeachingPlanStatus.COMPLETED, TeachingPlanStatus.CANCELLED}:
            raise ApplicationError(
                422,
                "TEACHING_PLAN_IMMUTABLE",
                "Cannot modify a completed or cancelled teaching plan.",
            )

        new_start = data.start_date if data.start_date is not None else plan.start_date
        new_end = (
            data.target_end_date if data.target_end_date is not None else plan.target_end_date
        )
        self._validate_dates(new_start, new_end)

        if data.start_date is not None:
            plan.start_date = data.start_date
        if data.target_end_date is not None:
            plan.target_end_date = data.target_end_date

        if data.items is not None:
            self._validate_items(plan.subject_id, data.items)
            plan.items.clear()
            for item in data.items:
                plan.items.append(
                    TeachingPlanItem(
                        problem_type_id=item.problem_type_id,
                        learning_outcome_id=item.learning_outcome_id,
                        priority=item.priority,
                        order_index=item.order_index,
                    )
                )

        if data.status is not None and data.status != plan.status:
            if data.status == TeachingPlanStatus.ACTIVE:
                if not plan.items:
                    raise ApplicationError(
                        422,
                        "EMPTY_TEACHING_PLAN",
                        "Cannot activate a teaching plan with no items.",
                    )
                self._assert_no_active_conflict(
                    plan.classroom_id, plan.subject_id, exclude_plan_id=plan.id
                )
            plan.status = data.status

        self.session.commit()
        self.session.refresh(plan)
        logger.info("Teaching plan patched (plan_id=%s, status=%s)", plan.id, plan.status.value)
        return self._build_read_model(plan)

    def activate_plan(self, teacher_user_id: UUID, plan_id: UUID) -> TeachingPlanRead:
        plan = self._get_plan_or_404(plan_id)
        self._verify_teacher_classroom(teacher_user_id, plan.classroom_id)

        if plan.status == TeachingPlanStatus.ACTIVE:
            return self._build_read_model(plan)

        if plan.status in {TeachingPlanStatus.COMPLETED, TeachingPlanStatus.CANCELLED}:
            raise ApplicationError(
                422,
                "INVALID_STATUS_TRANSITION",
                f"Cannot activate a {plan.status.value.lower()} teaching plan.",
            )

        if not plan.items:
            raise ApplicationError(
                422,
                "EMPTY_TEACHING_PLAN",
                "Cannot activate a teaching plan with no items.",
            )

        self._assert_no_active_conflict(
            plan.classroom_id, plan.subject_id, exclude_plan_id=plan.id
        )
        plan.status = TeachingPlanStatus.ACTIVE
        self.session.commit()
        self.session.refresh(plan)
        logger.info("Teaching plan activated (plan_id=%s)", plan.id)
        return self._build_read_model(plan)

    def complete_plan(self, teacher_user_id: UUID, plan_id: UUID) -> TeachingPlanRead:
        plan = self._get_plan_or_404(plan_id)
        self._verify_teacher_classroom(teacher_user_id, plan.classroom_id)

        if plan.status == TeachingPlanStatus.COMPLETED:
            return self._build_read_model(plan)

        if plan.status == TeachingPlanStatus.CANCELLED:
            raise ApplicationError(
                422,
                "INVALID_STATUS_TRANSITION",
                "Cannot complete a cancelled teaching plan.",
            )

        plan.status = TeachingPlanStatus.COMPLETED
        self.session.commit()
        self.session.refresh(plan)
        logger.info("Teaching plan completed (plan_id=%s)", plan.id)
        return self._build_read_model(plan)

    def _verify_teacher_classroom(
        self, teacher_user_id: UUID, classroom_id: UUID
    ) -> tuple[TeacherProfile, Classroom]:
        teacher = self.session.scalar(
            select(TeacherProfile).where(TeacherProfile.user_id == teacher_user_id)
        )
        if teacher is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Teacher profile was not found.")

        classroom = self.session.get(Classroom, classroom_id)
        if classroom is None:
            raise ApplicationError(404, "CLASSROOM_NOT_FOUND", "Classroom was not found.")

        assignment = self.session.scalar(
            select(TeacherClassroom).where(
                TeacherClassroom.teacher_id == teacher.id,
                TeacherClassroom.classroom_id == classroom_id,
            )
        )
        if assignment is None:
            raise ApplicationError(
                403,
                "CLASSROOM_ACCESS_DENIED",
                "You are not assigned to this classroom.",
            )
        return teacher, classroom

    def _validate_subject(self, subject_id: UUID) -> Subject:
        subject = self.session.get(Subject, subject_id)
        if subject is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        return subject

    @staticmethod
    def _validate_dates(start_date: date, target_end_date: date | None) -> None:
        if target_end_date is not None and target_end_date < start_date:
            raise ApplicationError(
                422,
                "INVALID_DATE_RANGE",
                "Target end date must be on or after start date.",
            )

    def _validate_items(
        self, subject_id: UUID, items: list[TeachingPlanItemCreate]
    ) -> None:
        if not items:
            return

        pt_ids = [item.problem_type_id for item in items]
        if len(pt_ids) != len(set(pt_ids)):
            raise ApplicationError(
                422,
                "DUPLICATE_PROBLEM_TYPE",
                "Duplicate problem types are not allowed in a teaching plan.",
            )

        valid_pts = set(
            self.session.scalars(
                select(ProblemType.id)
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .where(
                    ProblemType.id.in_(pt_ids),
                    ProblemType.is_active.is_(True),
                    Chapter.subject_id == subject_id,
                )
            )
        )
        for pt_id in pt_ids:
            if pt_id not in valid_pts:
                pt_exists = self.session.get(ProblemType, pt_id)
                if pt_exists is None:
                    raise ApplicationError(
                        404, "PROBLEM_TYPE_NOT_FOUND", f"Problem type {pt_id} was not found."
                    )
                raise ApplicationError(
                    422,
                    "PROBLEM_TYPE_SUBJECT_MISMATCH",
                    f"Problem type {pt_id} does not belong to subject {subject_id} or is inactive.",
                )

        lo_ids = [
            item.learning_outcome_id
            for item in items
            if item.learning_outcome_id is not None
        ]
        if lo_ids:
            valid_los = set(
                self.session.scalars(
                    select(LearningOutcome.id).where(
                        LearningOutcome.id.in_(lo_ids),
                        LearningOutcome.subject_id == subject_id,
                    )
                )
            )
            for lo_id in lo_ids:
                if lo_id not in valid_los:
                    lo_exists = self.session.get(LearningOutcome, lo_id)
                    if lo_exists is None:
                        raise ApplicationError(
                            404,
                            "LEARNING_OUTCOME_NOT_FOUND",
                            f"Learning outcome {lo_id} was not found.",
                        )
                    raise ApplicationError(
                        422,
                        "LEARNING_OUTCOME_SUBJECT_MISMATCH",
                        f"Learning outcome {lo_id} does not belong to subject {subject_id}.",
                    )

    def _assert_no_active_conflict(
        self, classroom_id: UUID, subject_id: UUID, exclude_plan_id: UUID | None = None
    ) -> None:
        statement = select(TeachingPlan.id).where(
            TeachingPlan.classroom_id == classroom_id,
            TeachingPlan.subject_id == subject_id,
            TeachingPlan.status == TeachingPlanStatus.ACTIVE,
        )
        if exclude_plan_id is not None:
            statement = statement.where(TeachingPlan.id != exclude_plan_id)

        existing_active = self.session.scalar(statement)
        if existing_active is not None:
            raise ApplicationError(
                409,
                "ACTIVE_PLAN_CONFLICT",
                "An active teaching plan already exists for this classroom and subject.",
            )

    def _get_plan_or_404(self, plan_id: UUID) -> TeachingPlan:
        statement = (
            select(TeachingPlan)
            .options(
                selectinload(TeachingPlan.items).selectinload(TeachingPlanItem.problem_type),
                selectinload(TeachingPlan.items).selectinload(TeachingPlanItem.learning_outcome),
            )
            .where(TeachingPlan.id == plan_id)
        )
        plan = self.session.scalar(statement)
        if plan is None:
            raise ApplicationError(404, "TEACHING_PLAN_NOT_FOUND", "Teaching plan was not found.")
        return plan

    def _build_read_model(self, plan: TeachingPlan) -> TeachingPlanRead:
        pt_ids = [item.problem_type_id for item in plan.items]
        derived_map: dict[UUID, list[UUID]] = defaultdict(list)
        if pt_ids:
            concept_rows = self.session.execute(
                select(ProblemTypeConcept.problem_type_id, ProblemTypeConcept.concept_id)
                .where(ProblemTypeConcept.problem_type_id.in_(pt_ids))
                .order_by(
                    ProblemTypeConcept.problem_type_id,
                    ProblemTypeConcept.is_primary.desc(),
                    ProblemTypeConcept.weight.desc(),
                )
            ).all()
            for pt_id, c_id in concept_rows:
                derived_map[pt_id].append(c_id)

        items_read = [
            TeachingPlanItemRead(
                id=item.id,
                teaching_plan_id=item.teaching_plan_id,
                problem_type_id=item.problem_type_id,
                learning_outcome_id=item.learning_outcome_id,
                priority=item.priority,
                order_index=item.order_index,
                derived_concept_ids=derived_map[item.problem_type_id],
            )
            for item in plan.items
        ]

        return TeachingPlanRead(
            id=plan.id,
            classroom_id=plan.classroom_id,
            subject_id=plan.subject_id,
            start_date=plan.start_date,
            target_end_date=plan.target_end_date,
            status=plan.status,
            created_by=plan.created_by,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            items=items_read,
        )
