from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.concepts.models import Concept
from app.curriculum.models import ProblemType
from app.database.base import Base
from app.students.models import StudentProfile


class ReviewResult(StrEnum):
    GOOD = "GOOD"
    POOR = "POOR"


class ReviewSchedule(Base):
    __tablename__ = "review_schedules"
    __table_args__ = (
        CheckConstraint(
            "((problem_type_id IS NOT NULL AND concept_id IS NULL) OR "
            "(problem_type_id IS NULL AND concept_id IS NOT NULL))",
            name="chk_review_schedule_single_target",
        ),
        CheckConstraint("review_interval_days > 0", name="chk_review_schedule_positive_interval"),
        CheckConstraint("review_count >= 0", name="chk_review_schedule_nonnegative_count"),
        Index("ix_review_schedules_student_next", "student_id", "next_review_at"),
        Index("ix_review_schedules_problem_type_id", "problem_type_id"),
        Index("ix_review_schedules_concept_id", "concept_id"),
        Index(
            "uq_review_schedules_student_pt",
            "student_id",
            "problem_type_id",
            unique=True,
            postgresql_where=text("problem_type_id IS NOT NULL"),
            sqlite_where=text("problem_type_id IS NOT NULL"),
        ),
        Index(
            "uq_review_schedules_student_concept",
            "student_id",
            "concept_id",
            unique=True,
            postgresql_where=text("concept_id IS NOT NULL"),
            sqlite_where=text("concept_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="CASCADE"),
        nullable=True,
    )
    concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=True,
    )
    next_review_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    review_interval_days: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )
    review_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_review_result: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    student: Mapped[StudentProfile] = relationship()
    problem_type: Mapped[ProblemType | None] = relationship()
    concept: Mapped[Concept | None] = relationship()
