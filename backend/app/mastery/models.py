from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class StudentConceptMastery(Base):
    __tablename__ = "student_concept_mastery"
    __table_args__ = (
        CheckConstraint("mastery_score BETWEEN 0.0 AND 1.0", name="mastery_score_range"),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="confidence_range"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("correct_count >= 0", name="correct_count_nonnegative"),
        CheckConstraint("correct_count <= attempt_count", name="correct_not_above_attempts"),
        Index("ix_student_concept_mastery_concept_student", "concept_id", "student_id"),
    )

    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT"), primary_key=True
    )
    mastery_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_practiced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StudentProblemTypeMastery(Base):
    __tablename__ = "student_problem_type_mastery"
    __table_args__ = (
        CheckConstraint("mastery_score BETWEEN 0.0 AND 1.0", name="mastery_score_range"),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="confidence_range"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("correct_count >= 0", name="correct_count_nonnegative"),
        CheckConstraint("correct_count <= attempt_count", name="correct_not_above_attempts"),
        Index(
            "ix_student_problem_type_mastery_problem_student",
            "problem_type_id",
            "student_id",
        ),
    )

    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    problem_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"), primary_key=True
    )
    mastery_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_practiced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

