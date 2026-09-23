from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class MisconceptionCategory(StrEnum):
    CONCEPTUAL = "CONCEPTUAL"
    PROCEDURAL = "PROCEDURAL"
    CALCULATION = "CALCULATION"
    READING = "READING"
    CARELESS = "CARELESS"
    OTHER = "OTHER"


class StudentMisconceptionStatus(StrEnum):
    SUSPECTED = "SUSPECTED"
    CONFIRMED = "CONFIRMED"
    RESOLVED = "RESOLVED"


class MisconceptionDefinition(Base):
    __tablename__ = "misconception_definitions"
    __table_args__ = (
        CheckConstraint(
            "code = upper(trim(code)) AND length(code) > 0",
            name="code_normalized",
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint(
            "length(trim(description)) > 0", name="description_not_blank"
        ),
        Index(
            "ix_misconception_definitions_concept_active",
            "concept_id",
            "is_active",
        ),
        Index(
            "ix_misconception_definitions_problem_type_id",
            "problem_type_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    concept_id: Mapped[UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=False
    )
    problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[MisconceptionCategory] = mapped_column(
        Enum(
            MisconceptionCategory,
            native_enum=False,
            create_constraint=True,
            name="misconception_category",
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )


class StudentMisconception(Base):
    __tablename__ = "student_misconceptions"
    __table_args__ = (
        CheckConstraint(
            "confidence BETWEEN 0.0 AND 1.0", name="confidence_range"
        ),
        CheckConstraint("occurrence_count > 0", name="occurrence_count_positive"),
        CheckConstraint(
            "first_detected_at <= last_detected_at",
            name="detection_time_order",
        ),
        CheckConstraint(
            "(status = 'RESOLVED' AND resolved_at IS NOT NULL) OR "
            "(status IN ('SUSPECTED', 'CONFIRMED') AND resolved_at IS NULL)",
            name="status_resolved_at_consistency",
        ),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= last_detected_at",
            name="resolved_after_detection",
        ),
        Index(
            "ix_student_misconceptions_student_status_confidence",
            "student_id",
            "status",
            "confidence",
        ),
        Index(
            "ix_student_misconceptions_definition_status",
            "misconception_definition_id",
            "status",
        ),
    )

    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    misconception_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("misconception_definitions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[StudentMisconceptionStatus] = mapped_column(
        Enum(
            StudentMisconceptionStatus,
            native_enum=False,
            create_constraint=True,
            name="student_misconception_status",
        ),
        nullable=False,
        default=StudentMisconceptionStatus.SUSPECTED,
        server_default=StudentMisconceptionStatus.SUSPECTED.value,
    )
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
