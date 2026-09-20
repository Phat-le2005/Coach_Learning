from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class TeachingPlanStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TeachingPlan(Base):
    __tablename__ = "teaching_plans"
    __table_args__ = (
        CheckConstraint(
            "target_end_date IS NULL OR target_end_date >= start_date",
            name="target_end_date_after_start_date",
        ),
        Index("ix_teaching_plans_classroom_subject_status", "classroom_id", "subject_id", "status"),
        Index("ix_teaching_plans_created_by", "created_by"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    classroom_id: Mapped[UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[TeachingPlanStatus] = mapped_column(
        Enum(
            TeachingPlanStatus,
            native_enum=False,
            create_constraint=True,
            name="teaching_plan_status",
        ),
        nullable=False,
        default=TeachingPlanStatus.PLANNED,
        server_default=TeachingPlanStatus.PLANNED.value,
        index=True,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
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

    classroom: Mapped["Classroom"] = relationship()
    subject: Mapped["Subject"] = relationship()
    items: Mapped[list["TeachingPlanItem"]] = relationship(
        back_populates="teaching_plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TeachingPlanItem.priority.desc(), TeachingPlanItem.order_index, TeachingPlanItem.id",
    )


class TeachingPlanItem(Base):
    __tablename__ = "teaching_plan_items"
    __table_args__ = (
        UniqueConstraint(
            "teaching_plan_id",
            "problem_type_id",
            name="uq_teaching_plan_items_plan_problem_type",
        ),
        CheckConstraint("priority > 0", name="priority_positive"),
        CheckConstraint("order_index IS NULL OR order_index >= 0", name="order_index_nonnegative"),
        Index("ix_teaching_plan_items_plan_priority", "teaching_plan_id", "priority"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    teaching_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("teaching_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    problem_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    learning_outcome_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("learning_outcomes.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    teaching_plan: Mapped[TeachingPlan] = relationship(back_populates="items")
    problem_type: Mapped["ProblemType"] = relationship()
    learning_outcome: Mapped["LearningOutcome | None"] = relationship()


from app.planning.study_models import (
    StudyPlan,
    StudyPlanStatus,
    StudyTask,
    StudyTaskReasonCode,
    StudyTaskStatus,
    StudyTaskType,
)

