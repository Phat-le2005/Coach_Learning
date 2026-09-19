from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, SmallInteger, String, Uuid, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.parents.models import ParentStudentRelationship

from app.students.goal_models import AcademicGoal, AcademicGoalStatus, SubjectGoal


class SyntheticProfile(StrEnum):
    STRONG = "STRONG"
    AVERAGE = "AVERAGE"
    WEAK = "WEAK"
    SPECIFIC_GAP = "SPECIFIC_GAP"
    INCONSISTENT = "INCONSISTENT"


class StudentProfile(Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        CheckConstraint("grade_level BETWEEN 1 AND 12", name="grade_level_range"),
        CheckConstraint(
            "(is_synthetic AND synthetic_profile IS NOT NULL) OR "
            "(NOT is_synthetic AND synthetic_profile IS NULL)",
            name="synthetic_profile_consistency",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    grade_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=12, server_default="12")
    school_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    synthetic_profile: Mapped[SyntheticProfile | None] = mapped_column(
        Enum(
            SyntheticProfile,
            native_enum=False,
            create_constraint=True,
            name="synthetic_student_profile",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    parent_relationships: Mapped[list["ParentStudentRelationship"]] = relationship(
        back_populates="student", cascade="all, delete-orphan", passive_deletes=True
    )
    academic_goals: Mapped[list["AcademicGoal"]] = relationship(
        "AcademicGoal", back_populates="student", cascade="all, delete-orphan", passive_deletes=True
    )


__all__ = [
    "AcademicGoal",
    "AcademicGoalStatus",
    "StudentProfile",
    "SubjectGoal",
    "SyntheticProfile",
]
