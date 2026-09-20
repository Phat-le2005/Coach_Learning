from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.concepts.models import Concept
    from app.curriculum.models import Chapter, ProblemType, Topic
    from app.students.goal_models import AcademicGoal
    from app.students.models import StudentProfile
    from app.subjects.models import Subject


class StudyPlanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class StudyTaskType(StrEnum):
    LEARN = "LEARN"
    PRACTICE = "PRACTICE"
    REPAIR = "REPAIR"
    REVIEW = "REVIEW"
    QUICK_CHECK = "QUICK_CHECK"
    MINI_TEST = "MINI_TEST"
    EXAM = "EXAM"


class StudyTaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


class StudyTaskReasonCode(StrEnum):
    CURRENT_TEACHING_PLAN = "CURRENT_TEACHING_PLAN"
    PREREQUISITE_REPAIR = "PREREQUISITE_REPAIR"
    WEAK_PROBLEM_TYPE = "WEAK_PROBLEM_TYPE"
    REVIEW_DUE = "REVIEW_DUE"
    EXAM_PREPARATION = "EXAM_PREPARATION"
    DIAGNOSTIC_FOLLOWUP = "DIAGNOSTIC_FOLLOWUP"
    GENERAL_PRACTICE = "GENERAL_PRACTICE"


class StudyPlan(Base):
    __tablename__ = "study_plans"
    __table_args__ = (
        CheckConstraint(
            "target_date IS NULL OR target_date >= start_date",
            name="ck_study_plans_target_date_after_start_date",
        ),
        Index("ix_study_plans_student_status", "student_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    academic_goal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("academic_goals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[StudyPlanStatus] = mapped_column(
        Enum(
            StudyPlanStatus,
            native_enum=False,
            create_constraint=True,
            name="study_plan_status",
        ),
        nullable=False,
        default=StudyPlanStatus.ACTIVE,
        server_default=StudyPlanStatus.ACTIVE.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    student: Mapped["StudentProfile"] = relationship()
    academic_goal: Mapped["AcademicGoal | None"] = relationship()
    tasks: Mapped[list["StudyTask"]] = relationship(
        back_populates="study_plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="StudyTask.planned_date, StudyTask.priority.desc(), StudyTask.order_index, StudyTask.id",
    )


class StudyTask(Base):
    __tablename__ = "study_tasks"
    __table_args__ = (
        CheckConstraint(
            "estimated_duration_minutes > 0",
            name="ck_study_tasks_positive_duration",
        ),
        CheckConstraint("priority > 0", name="ck_study_tasks_positive_priority"),
        CheckConstraint("order_index >= 0", name="ck_study_tasks_nonnegative_order"),
        Index("ix_study_tasks_plan_date", "study_plan_id", "planned_date"),
        Index("ix_study_tasks_plan_date_status", "study_plan_id", "planned_date", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    study_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("study_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_type: Mapped[StudyTaskType] = mapped_column(
        Enum(
            StudyTaskType,
            native_enum=False,
            create_constraint=True,
            name="study_task_type",
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[StudyTaskStatus] = mapped_column(
        Enum(
            StudyTaskStatus,
            native_enum=False,
            create_constraint=True,
            name="study_task_status",
        ),
        nullable=False,
        default=StudyTaskStatus.PENDING,
        server_default=StudyTaskStatus.PENDING.value,
        index=True,
    )
    planned_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Optional targeting: ProblemType and/or Concept
    problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subject_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    study_plan: Mapped["StudyPlan"] = relationship(back_populates="tasks")
    problem_type: Mapped["ProblemType | None"] = relationship()
    concept: Mapped["Concept | None"] = relationship()
    subject: Mapped["Subject | None"] = relationship()

