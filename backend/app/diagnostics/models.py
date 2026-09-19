from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Index,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DiagnosticSelectionReason(StrEnum):
    BLUEPRINT_COVERAGE = "BLUEPRINT_COVERAGE"
    CONFIDENCE_REFINEMENT = "CONFIDENCE_REFINEMENT"
    PREREQUISITE_CHECK = "PREREQUISITE_CHECK"


class DiagnosticCompletionReason(StrEnum):
    CONFIDENCE_REACHED = "CONFIDENCE_REACHED"
    MAX_QUESTIONS = "MAX_QUESTIONS"
    NO_AVAILABLE_QUESTION = "NO_AVAILABLE_QUESTION"


class DiagnosticAssessment(Base):
    __tablename__ = "diagnostic_assessments"
    __table_args__ = (
        CheckConstraint(
            "max_questions BETWEEN 1 AND 100",
            name="max_questions_range",
        ),
        CheckConstraint(
            "minimum_problem_type_coverage > 0.0 "
            "AND minimum_problem_type_coverage <= 1.0",
            name="minimum_coverage_range",
        ),
        CheckConstraint(
            "confidence_threshold BETWEEN 0.0 AND 1.0",
            name="confidence_threshold_range",
        ),
        CheckConstraint(
            "current_difficulty IS NULL OR current_difficulty BETWEEN 0.0 AND 1.0",
            name="current_difficulty_range",
        ),
        CheckConstraint(
            "(current_question_id IS NULL "
            "AND current_target_problem_type_id IS NULL "
            "AND current_target_concept_id IS NULL "
            "AND current_difficulty IS NULL "
            "AND current_selection_reason IS NULL) OR "
            "(current_question_id IS NOT NULL "
            "AND current_difficulty IS NOT NULL "
            "AND current_selection_reason IS NOT NULL "
            "AND ((current_target_problem_type_id IS NOT NULL "
            "AND current_target_concept_id IS NULL) "
            "OR (current_target_problem_type_id IS NULL "
            "AND current_target_concept_id IS NOT NULL)))",
            name="pending_selection_consistency",
        ),
        Index("ix_diagnostic_assessments_current_question_id", "current_question_id"),
    )

    id: Mapped[UUID] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    max_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_problem_type_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    current_question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=True
    )
    current_target_problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"), nullable=True
    )
    current_target_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=True
    )
    current_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_selection_reason: Mapped[DiagnosticSelectionReason | None] = mapped_column(
        Enum(
            DiagnosticSelectionReason,
            native_enum=False,
            create_constraint=True,
            name="diagnostic_selection_reason",
        ),
        nullable=True,
    )
    completion_reason: Mapped[DiagnosticCompletionReason | None] = mapped_column(
        Enum(
            DiagnosticCompletionReason,
            native_enum=False,
            create_constraint=True,
            name="diagnostic_completion_reason",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    blueprint_items: Mapped[list["DiagnosticBlueprintItem"]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DiagnosticBlueprintItem.order_index",
    )


class DiagnosticBlueprintItem(Base):
    __tablename__ = "diagnostic_blueprint_items"
    __table_args__ = (
        UniqueConstraint(
            "diagnostic_assessment_id",
            "order_index",
            name="uq_diagnostic_blueprint_items_assessment_order",
        ),
        CheckConstraint("order_index >= 0", name="order_index_nonnegative"),
        Index("ix_diagnostic_blueprint_items_problem_type_id", "problem_type_id"),
    )

    diagnostic_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("diagnostic_assessments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    problem_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    assessment: Mapped[DiagnosticAssessment] = relationship(
        back_populates="blueprint_items"
    )


class DiagnosticAttemptContext(Base):
    __tablename__ = "diagnostic_attempt_contexts"
    __table_args__ = (
        CheckConstraint(
            "(target_problem_type_id IS NOT NULL AND target_concept_id IS NULL) OR "
            "(target_problem_type_id IS NULL AND target_concept_id IS NOT NULL)",
            name="ck_diagnostic_attempt_target_exclusive",
        ),
        CheckConstraint(
            "desired_difficulty BETWEEN 0.0 AND 1.0",
            name="ck_diagnostic_attempt_difficulty_range",
        ),
        Index("ix_diagnostic_attempt_contexts_target_pt", "target_problem_type_id"),
        Index("ix_diagnostic_attempt_contexts_target_concept", "target_concept_id"),
    )

    attempt_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("question_attempts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    target_problem_type_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("problem_types.id", ondelete="RESTRICT"),
        nullable=True,
    )
    target_concept_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("concepts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    selection_reason: Mapped[DiagnosticSelectionReason] = mapped_column(
        Enum(
            DiagnosticSelectionReason,
            native_enum=False,
            create_constraint=True,
            name="diagnostic_selection_reason",
        ),
        nullable=False,
    )
    desired_difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
