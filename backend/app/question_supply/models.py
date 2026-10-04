"""Question bank sufficiency and supply gap models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class QuestionSupplyUseCase(StrEnum):
    ROOT_CAUSE_VERIFICATION = "ROOT_CAUSE_VERIFICATION"
    ADAPTIVE_REPAIR = "ADAPTIVE_REPAIR"
    REVIEW = "REVIEW"
    CURRENT_LEARNING = "CURRENT_LEARNING"


class QuestionSupplyTargetType(StrEnum):
    CONCEPT = "CONCEPT"
    PROBLEM_TYPE = "PROBLEM_TYPE"
    MISCONCEPTION = "MISCONCEPTION"


class QuestionSupplyStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class QuestionSupplySeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class QuestionSupplyHealth(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    THIN = "THIN"
    INSUFFICIENT = "INSUFFICIENT"


class QuestionSupplyReasonCode(StrEnum):
    NO_APPROVED_TARGET_QUESTIONS = "NO_APPROVED_TARGET_QUESTIONS"
    INSUFFICIENT_APPROVED_TARGET_COUNT = "INSUFFICIENT_APPROVED_TARGET_COUNT"
    INSUFFICIENT_DIFFICULTY_COVERAGE = "INSUFFICIENT_DIFFICULTY_COVERAGE"
    NO_AUTO_EVALUABLE_TARGET_QUESTIONS = "NO_AUTO_EVALUABLE_TARGET_QUESTIONS"
    STUDENT_EXPOSURE_EXHAUSTED = "STUDENT_EXPOSURE_EXHAUSTED"
    THIN_APPROVED_TARGET_COUNT = "THIN_APPROVED_TARGET_COUNT"
    THIN_DIFFICULTY_COVERAGE = "THIN_DIFFICULTY_COVERAGE"


class QuestionSupplyObservationSourceKind(StrEnum):
    LEARNING_FEEDBACK = "LEARNING_FEEDBACK"
    ROOT_CAUSE_VERIFICATION = "ROOT_CAUSE_VERIFICATION"
    ADAPTIVE_REPAIR_START = "ADAPTIVE_REPAIR_START"
    ADAPTIVE_REPAIR_RUNTIME = "ADAPTIVE_REPAIR_RUNTIME"
    MANUAL_ASSESSMENT = "MANUAL_ASSESSMENT"


class QuestionSupplyGap(Base):
    """Aggregate demand shortage for canonical questions."""

    __tablename__ = "question_supply_gaps"
    __table_args__ = (
        UniqueConstraint("signature", name="uq_question_supply_gap_signature"),
        CheckConstraint(
            "desired_difficulty IS NULL OR (desired_difficulty >= 0.0 AND desired_difficulty <= 1.0)",
            name="ck_supply_gaps_desired_difficulty",
        ),
        CheckConstraint(
            "difficulty_min >= 0.0 AND difficulty_min <= difficulty_max AND difficulty_max <= 1.0",
            name="ck_supply_gaps_difficulty_range",
        ),
        CheckConstraint(
            "minimum_required_count > 0 AND preferred_count >= minimum_required_count",
            name="ck_supply_gaps_counts_logic",
        ),
        CheckConstraint(
            "approved_eligible_count >= 0 AND approved_in_band_count >= 0 AND approved_in_band_count <= approved_eligible_count",
            name="ck_supply_gaps_approved_counts",
        ),
        CheckConstraint(
            "pipeline_candidate_count >= 0 AND demand_count >= 0",
            name="ck_supply_gaps_pipeline_demand",
        ),
        CheckConstraint(
            "pipeline_runtime_eligible_count >= 0 AND pipeline_runtime_eligible_count <= pipeline_candidate_count",
            name="ck_supply_gaps_pipeline_runtime_eligible",
        ),
        Index("ix_supply_gaps_status_severity", "status", "severity"),
        Index("ix_supply_gaps_subject_status", "subject_id", "status"),
        Index("ix_supply_gaps_use_case_status", "use_case", "status"),
        Index("ix_supply_gaps_concept_id", "concept_id"),
        Index("ix_supply_gaps_problem_type_id", "problem_type_id"),
        Index("ix_supply_gaps_misconception_id", "misconception_definition_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    signature: Mapped[str] = mapped_column(String(64), nullable=False)

    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    use_case: Mapped[QuestionSupplyUseCase] = mapped_column(
        Enum(QuestionSupplyUseCase, native_enum=False, name="question_supply_use_case"),
        nullable=False,
    )
    target_type: Mapped[QuestionSupplyTargetType] = mapped_column(
        Enum(QuestionSupplyTargetType, native_enum=False, name="question_supply_target_type"),
        nullable=False,
    )

    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=True
    )
    problem_type_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("problem_types.id", ondelete="RESTRICT"), nullable=True
    )
    misconception_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("misconception_definitions.id", ondelete="RESTRICT"), nullable=True
    )

    desired_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty_min: Mapped[float] = mapped_column(Float, nullable=False)
    difficulty_max: Mapped[float] = mapped_column(Float, nullable=False)

    minimum_required_count: Mapped[int] = mapped_column(Integer, nullable=False)
    preferred_count: Mapped[int] = mapped_column(Integer, nullable=False)

    approved_eligible_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_in_band_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pipeline_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    pipeline_runtime_eligible_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    severity: Mapped[QuestionSupplySeverity] = mapped_column(
        Enum(QuestionSupplySeverity, native_enum=False, name="question_supply_severity"),
        nullable=False,
    )
    status: Mapped[QuestionSupplyStatus] = mapped_column(
        Enum(QuestionSupplyStatus, native_enum=False, name="question_supply_status"),
        nullable=False,
        default=QuestionSupplyStatus.OPEN,
        server_default=QuestionSupplyStatus.OPEN.value,
    )
    reason_code: Mapped[QuestionSupplyReasonCode] = mapped_column(
        Enum(
            QuestionSupplyReasonCode,
            native_enum=False,
            name="question_supply_gap_reason_code",
        ),
        nullable=False,
    )

    demand_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    first_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    last_assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    observations: Mapped[list[QuestionSupplyGapObservation]] = relationship(
        "QuestionSupplyGapObservation",
        back_populates="gap",
        cascade="all, delete-orphan",
        order_by="desc(QuestionSupplyGapObservation.created_at)",
    )


class QuestionSupplyGapObservation(Base):
    """Context and demand occurrence for a question supply gap."""

    __tablename__ = "question_supply_gap_observations"
    __table_args__ = (
        UniqueConstraint(
            "gap_id",
            "source_kind",
            "source_entity_id",
            name="uq_supply_gap_observation_source",
        ),
        Index("ix_supply_gap_obs_gap_created", "gap_id", "created_at"),
        Index("ix_supply_gap_obs_student_created", "student_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gap_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("question_supply_gaps.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("student_profiles.id", ondelete="SET NULL"), nullable=True
    )
    source_kind: Mapped[QuestionSupplyObservationSourceKind] = mapped_column(
        Enum(
            QuestionSupplyObservationSourceKind,
            native_enum=False,
            name="question_supply_obs_source_kind",
        ),
        nullable=False,
    )
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reason_code: Mapped[QuestionSupplyReasonCode] = mapped_column(
        Enum(
            QuestionSupplyReasonCode,
            native_enum=False,
            name="question_supply_obs_reason_code",
        ),
        nullable=False,
    )

    observed_approved_eligible_count: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_approved_in_band_count: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_fresh_eligible_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_fresh_in_band_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_excluded_exposure_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    gap: Mapped[QuestionSupplyGap] = relationship(
        "QuestionSupplyGap", back_populates="observations"
    )
