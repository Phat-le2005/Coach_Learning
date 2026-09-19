from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.students.models import StudentProfile
    from app.subjects.models import Subject


class AcademicGoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"
    ARCHIVED = "ARCHIVED"


class AcademicGoal(Base):
    __tablename__ = "academic_goals"
    __table_args__ = (
        CheckConstraint(
            "available_daily_minutes > 0 AND available_daily_minutes <= 1440",
            name="ck_academic_goals_daily_minutes",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_exam: Mapped[str] = mapped_column(String(100), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    available_daily_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AcademicGoalStatus] = mapped_column(
        Enum(
            AcademicGoalStatus,
            native_enum=False,
            create_constraint=True,
            name="academic_goal_status",
        ),
        nullable=False,
        default=AcademicGoalStatus.ACTIVE,
        server_default="ACTIVE",
        index=True,
    )
    target_university: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_major: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["StudentProfile"] = relationship(
        "StudentProfile", back_populates="academic_goals"
    )
    subject_goals: Mapped[list["SubjectGoal"]] = relationship(
        "SubjectGoal",
        back_populates="academic_goal",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SubjectGoal.priority",
    )


class SubjectGoal(Base):
    __tablename__ = "subject_goals"
    __table_args__ = (
        UniqueConstraint(
            "academic_goal_id",
            "subject_id",
            name="uq_subject_goals_academic_goal_subject",
        ),
        CheckConstraint(
            "current_score IS NULL OR current_score >= 0.0",
            name="ck_subject_goals_current_score_non_negative",
        ),
        CheckConstraint(
            "target_score >= 0.0",
            name="ck_subject_goals_target_score_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    academic_goal_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("academic_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("subjects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    current_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_score: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    academic_goal: Mapped["AcademicGoal"] = relationship(
        "AcademicGoal", back_populates="subject_goals"
    )
    subject: Mapped["Subject"] = relationship("Subject")
