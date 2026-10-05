"""Persisted, evidence-driven root-cause diagnostic models."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class RootCauseDiagnosisType(StrEnum):
    PREREQUISITE_CONCEPT_GAP = "PREREQUISITE_CONCEPT_GAP"
    DIRECT_CONCEPT_GAP = "DIRECT_CONCEPT_GAP"
    PROBLEM_TYPE_PROCEDURE_GAP = "PROBLEM_TYPE_PROCEDURE_GAP"
    MISCONCEPTION_HYPOTHESIS = "MISCONCEPTION_HYPOTHESIS"
    MULTI_FACTOR_GAP = "MULTI_FACTOR_GAP"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RootCauseDiagnosisStatus(StrEnum):
    HYPOTHESIS = "HYPOTHESIS"
    STRONG_HYPOTHESIS = "STRONG_HYPOTHESIS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RootCauseDiagnosis(Base):
    __tablename__ = "root_cause_diagnoses"
    __table_args__ = (
        UniqueConstraint(
            "learning_evidence_event_id", name="uq_root_cause_diagnosis_evidence"
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint(
            "supporting_evidence_count >= 0", name="supporting_count_nonnegative"
        ),
        Index("ix_root_cause_student_created", "student_id", "created_at"),
        Index("ix_root_cause_subject_type", "subject_id", "diagnosis_type"),
        Index("ix_root_cause_classroom_created", "classroom_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    learning_evidence_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("learning_evidence_events.id", ondelete="RESTRICT"), nullable=False
    )
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    classroom_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("classrooms.id", ondelete="SET NULL")
    )
    assignment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assignments.id", ondelete="SET NULL")
    )
    target_problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT")
    )
    diagnosis_type: Mapped[RootCauseDiagnosisType] = mapped_column(
        Enum(
            RootCauseDiagnosisType,
            native_enum=False,
            name="root_cause_diagnosis_type",
        ),
        nullable=False,
    )
    status: Mapped[RootCauseDiagnosisStatus] = mapped_column(
        Enum(
            RootCauseDiagnosisStatus,
            native_enum=False,
            name="root_cause_diagnosis_status",
        ),
        nullable=False,
    )
    root_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT")
    )
    misconception_definition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("misconception_definitions.id", ondelete="RESTRICT")
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    supporting_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    diagnosis_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    candidates: Mapped[list["RootCauseCandidate"]] = relationship(
        back_populates="diagnosis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RootCauseCandidate.rank",
    )
    verifications: Mapped[list["RootCauseVerification"]] = relationship(
        back_populates="diagnosis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RootCauseVerification.created_at",
    )


class RootCauseCandidate(Base):
    __tablename__ = "root_cause_candidates"
    __table_args__ = (
        UniqueConstraint("diagnosis_id", "rank", name="uq_root_cause_candidate_rank"),
        CheckConstraint("rank > 0", name="rank_positive"),
        CheckConstraint("score BETWEEN 0 AND 1", name="score_range"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint(
            "graph_distance IS NULL OR graph_distance >= 0",
            name="graph_distance_nonnegative",
        ),
        CheckConstraint(
            "supporting_event_count >= 0 AND conflicting_event_count >= 0",
            name="event_counts_nonnegative",
        ),
        Index("ix_root_cause_candidates_concept", "concept_id"),
        Index("ix_root_cause_candidates_problem_type", "problem_type_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    diagnosis_id: Mapped[UUID] = mapped_column(
        ForeignKey("root_cause_diagnoses.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_type: Mapped[RootCauseDiagnosisType] = mapped_column(
        Enum(
            RootCauseDiagnosisType,
            native_enum=False,
            name="root_cause_candidate_type",
        ),
        nullable=False,
    )
    concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT")
    )
    problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT")
    )
    misconception_definition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("misconception_definitions.id", ondelete="RESTRICT")
    )
    graph_distance: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    mastery_deficit_signal: Mapped[float] = mapped_column(Float, nullable=False)
    recent_error_signal: Mapped[float] = mapped_column(Float, nullable=False)
    structural_signal: Mapped[float] = mapped_column(Float, nullable=False)
    misconception_signal: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_volume_signal: Mapped[float] = mapped_column(Float, nullable=False)
    supporting_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    conflicting_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    diagnosis: Mapped[RootCauseDiagnosis] = relationship(back_populates="candidates")


class RootCauseVerificationStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    UNAVAILABLE = "UNAVAILABLE"


class RootCauseVerificationTargetType(StrEnum):
    CONCEPT = "CONCEPT"
    PROBLEM_TYPE = "PROBLEM_TYPE"
    MISCONCEPTION = "MISCONCEPTION"


class RootCauseVerificationOutcome(StrEnum):
    PENDING = "PENDING"
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNAVAILABLE = "UNAVAILABLE"


class RootCauseVerification(Base):
    __tablename__ = "root_cause_verifications"
    __table_args__ = (
        CheckConstraint(
            "required_probe_count >= 0", name="required_probes_nonnegative"
        ),
        CheckConstraint(
            "completed_probe_count >= 0", name="completed_probes_nonnegative"
        ),
        CheckConstraint(
            "completed_probe_count <= required_probe_count",
            name="completed_probes_not_exceed_required",
        ),
        UniqueConstraint(
            "diagnosis_id", name="uq_root_cause_verification_diagnosis"
        ),
        Index("ix_root_cause_verification_diagnosis", "diagnosis_id"),
        Index("ix_root_cause_verification_practice_session", "practice_session_id"),
        Index("ix_root_cause_verification_diag_status", "diagnosis_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    diagnosis_id: Mapped[UUID] = mapped_column(
        ForeignKey("root_cause_diagnoses.id", ondelete="CASCADE"), nullable=False
    )
    practice_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[RootCauseVerificationStatus] = mapped_column(
        Enum(
            RootCauseVerificationStatus,
            native_enum=False,
            name="root_cause_verification_status",
        ),
        nullable=False,
        default=RootCauseVerificationStatus.PENDING,
    )
    required_probe_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_probe_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    diagnosis: Mapped[RootCauseDiagnosis] = relationship(back_populates="verifications")
    targets: Mapped[list["RootCauseVerificationTarget"]] = relationship(
        back_populates="verification",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RootCauseVerificationTarget.priority_order",
    )


class RootCauseVerificationTarget(Base):
    __tablename__ = "root_cause_verification_targets"
    __table_args__ = (
        CheckConstraint("priority_order >= 0", name="priority_order_nonnegative"),
        CheckConstraint("probe_count >= 0", name="probe_count_nonnegative"),
        CheckConstraint("correct_count >= 0", name="correct_count_nonnegative"),
        CheckConstraint(
            "correct_count <= probe_count",
            name="correct_count_not_exceed_probe_count",
        ),
        CheckConstraint(
            "average_score IS NULL OR (average_score >= 0 AND average_score <= 1)",
            name="target_average_score_range",
        ),
        Index("ix_root_cause_verification_target_verification", "verification_id"),
        Index("ix_root_cause_verification_target_concept", "target_concept_id"),
        Index("ix_root_cause_verification_target_problem_type", "target_problem_type_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    verification_id: Mapped[UUID] = mapped_column(
        ForeignKey("root_cause_verifications.id", ondelete="CASCADE"), nullable=False
    )
    root_cause_candidate_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("root_cause_candidates.id", ondelete="SET NULL"), nullable=True
    )
    target_type: Mapped[RootCauseVerificationTargetType] = mapped_column(
        Enum(
            RootCauseVerificationTargetType,
            native_enum=False,
            name="root_cause_verification_target_type",
        ),
        nullable=False,
    )
    target_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=True
    )
    target_problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"), nullable=True
    )
    misconception_definition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("misconception_definitions.id", ondelete="RESTRICT"), nullable=True
    )
    priority_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    outcome: Mapped[RootCauseVerificationOutcome] = mapped_column(
        Enum(
            RootCauseVerificationOutcome,
            native_enum=False,
            name="root_cause_verification_outcome",
        ),
        nullable=False,
        default=RootCauseVerificationOutcome.PENDING,
    )
    probe_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    verification: Mapped[RootCauseVerification] = relationship(back_populates="targets")
    items: Mapped[list["RootCauseVerificationItem"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RootCauseVerificationItem.order_index",
    )
    candidate: Mapped[RootCauseCandidate | None] = relationship()


class RootCauseVerificationItem(Base):
    __tablename__ = "root_cause_verification_items"
    __table_args__ = (
        CheckConstraint("order_index >= 0", name="item_order_index_nonnegative"),
        CheckConstraint(
            "desired_difficulty BETWEEN 0 AND 1", name="desired_difficulty_range"
        ),
        UniqueConstraint(
            "verification_target_id",
            "question_id",
            name="uq_root_cause_verification_target_question",
        ),
        Index("ix_root_cause_verification_item_target", "verification_target_id"),
        Index("ix_root_cause_verification_item_question", "question_id"),
        Index("ix_root_cause_verification_item_attempt", "attempt_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    verification_target_id: Mapped[UUID] = mapped_column(
        ForeignKey("root_cause_verification_targets.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    desired_difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    selection_score: Mapped[float] = mapped_column(Float, nullable=False)
    attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("question_attempts.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    target: Mapped[RootCauseVerificationTarget] = relationship(back_populates="items")

