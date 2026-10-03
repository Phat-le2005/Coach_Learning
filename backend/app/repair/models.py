from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.knowledge_gap.models import RootCauseVerificationTargetType


class AdaptiveRepairStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


class AdaptiveRepairPhase(StrEnum):
    FOUNDATION = "FOUNDATION"
    GUIDED = "GUIDED"
    TARGET_PRACTICE = "TARGET_PRACTICE"
    FINAL_RECHECK = "FINAL_RECHECK"


class AdaptiveRepairOutcome(StrEnum):
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    NEEDS_MORE_PRACTICE = "NEEDS_MORE_PRACTICE"
    BANK_EXHAUSTED = "BANK_EXHAUSTED"


class AdaptiveRepairItemRole(StrEnum):
    FOUNDATION = "FOUNDATION"
    GUIDED = "GUIDED"
    PRACTICE = "PRACTICE"
    FINAL_RECHECK = "FINAL_RECHECK"


class AdaptiveRepairDecisionReason(StrEnum):
    CORRECT_ADVANCE_DIFFICULTY = "CORRECT_ADVANCE_DIFFICULTY"
    CORRECT_WITH_HINT_SMALL_ADVANCE = "CORRECT_WITH_HINT_SMALL_ADVANCE"
    WRONG_REDUCE_DIFFICULTY = "WRONG_REDUCE_DIFFICULTY"
    REPEATED_WRONG_ENTER_GUIDED = "REPEATED_WRONG_ENTER_GUIDED"
    RECOVERED_EXIT_GUIDED = "RECOVERED_EXIT_GUIDED"
    READY_FOR_FINAL_RECHECK = "READY_FOR_FINAL_RECHECK"
    FINAL_RECHECK_PASSED = "FINAL_RECHECK_PASSED"
    FINAL_RECHECK_FAILED = "FINAL_RECHECK_FAILED"
    MAX_QUESTIONS_REACHED = "MAX_QUESTIONS_REACHED"
    QUESTION_BANK_EXHAUSTED = "QUESTION_BANK_EXHAUSTED"


class AdaptiveRepairSession(Base):
    __tablename__ = "adaptive_repair_sessions"
    __table_args__ = (
        UniqueConstraint("practice_session_id", name="uq_adaptive_repair_practice_session"),
        UniqueConstraint("verification_target_id", name="uq_adaptive_repair_verification_target"),
        CheckConstraint("initial_difficulty BETWEEN 0 AND 1", name="initial_difficulty_range"),
        CheckConstraint("current_difficulty BETWEEN 0 AND 1", name="current_difficulty_range"),
        CheckConstraint("target_exit_difficulty BETWEEN 0 AND 1", name="target_exit_difficulty_range"),
        CheckConstraint("verification_average_score IS NULL OR verification_average_score BETWEEN 0 AND 1", name="verification_average_score_range"),
        CheckConstraint("attempted_count >= 0", name="attempted_count_nonnegative"),
        CheckConstraint("correct_count >= 0", name="correct_count_nonnegative"),
        CheckConstraint("correct_count <= attempted_count", name="correct_count_not_exceed_attempted"),
        CheckConstraint("consecutive_correct >= 0", name="consecutive_correct_nonnegative"),
        CheckConstraint("consecutive_wrong >= 0", name="consecutive_wrong_nonnegative"),
        CheckConstraint("max_questions > 0", name="max_questions_positive"),
        CheckConstraint("(status = 'ACTIVE' AND outcome = 'PENDING' AND completed_at IS NULL) OR (status = 'COMPLETED' AND outcome <> 'PENDING' AND completed_at IS NOT NULL)", name="completion_consistency"),
        Index("ix_adaptive_repair_student_status", "student_id", "status"),
        Index("ix_adaptive_repair_diagnosis", "diagnosis_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    practice_session_id: Mapped[UUID] = mapped_column(ForeignKey("practice_sessions.id", ondelete="RESTRICT"), nullable=False)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    diagnosis_id: Mapped[UUID] = mapped_column(ForeignKey("root_cause_diagnoses.id", ondelete="RESTRICT"), nullable=False)
    verification_id: Mapped[UUID] = mapped_column(ForeignKey("root_cause_verifications.id", ondelete="RESTRICT"), nullable=False)
    verification_target_id: Mapped[UUID] = mapped_column(ForeignKey("root_cause_verification_targets.id", ondelete="RESTRICT"), nullable=False)
    target_type: Mapped[RootCauseVerificationTargetType] = mapped_column(Enum(RootCauseVerificationTargetType, native_enum=False, name="adaptive_repair_target_type"), nullable=False)
    target_concept_id: Mapped[UUID | None] = mapped_column(ForeignKey("concepts.id", ondelete="RESTRICT"))
    target_problem_type_id: Mapped[UUID | None] = mapped_column(ForeignKey("problem_types.id", ondelete="RESTRICT"))
    misconception_definition_id: Mapped[UUID | None] = mapped_column(ForeignKey("misconception_definitions.id", ondelete="RESTRICT"))
    target_name: Mapped[str | None] = mapped_column(String(255))
    target_code: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[AdaptiveRepairStatus] = mapped_column(Enum(AdaptiveRepairStatus, native_enum=False, name="adaptive_repair_status"), nullable=False, default=AdaptiveRepairStatus.ACTIVE)
    phase: Mapped[AdaptiveRepairPhase] = mapped_column(Enum(AdaptiveRepairPhase, native_enum=False, name="adaptive_repair_phase"), nullable=False)
    outcome: Mapped[AdaptiveRepairOutcome] = mapped_column(Enum(AdaptiveRepairOutcome, native_enum=False, name="adaptive_repair_outcome"), nullable=False, default=AdaptiveRepairOutcome.PENDING)
    initial_difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    current_difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    target_exit_difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    verification_average_score: Mapped[float | None] = mapped_column(Float)
    attempted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_wrong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    items: Mapped[list["AdaptiveRepairItem"]] = relationship(back_populates="adaptive_session", cascade="all, delete-orphan", passive_deletes=True, order_by="AdaptiveRepairItem.order_index")


class AdaptiveRepairItem(Base):
    __tablename__ = "adaptive_repair_items"
    __table_args__ = (
        UniqueConstraint("adaptive_repair_session_id", "order_index", name="uq_adaptive_repair_item_order"),
        UniqueConstraint("adaptive_repair_session_id", "question_id", name="uq_adaptive_repair_item_question"),
        UniqueConstraint("attempt_id", name="uq_adaptive_repair_item_attempt"),
        CheckConstraint("order_index > 0", name="order_index_positive"),
        CheckConstraint("desired_difficulty BETWEEN 0 AND 1", name="desired_difficulty_range"),
        CheckConstraint("difficulty_before BETWEEN 0 AND 1", name="difficulty_before_range"),
        CheckConstraint("difficulty_after IS NULL OR difficulty_after BETWEEN 0 AND 1", name="difficulty_after_range"),
        Index("ix_adaptive_repair_item_session", "adaptive_repair_session_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    adaptive_repair_session_id: Mapped[UUID] = mapped_column(ForeignKey("adaptive_repair_sessions.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[AdaptiveRepairItemRole] = mapped_column(Enum(AdaptiveRepairItemRole, native_enum=False, name="adaptive_repair_item_role"), nullable=False)
    desired_difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    selection_score: Mapped[float | None] = mapped_column(Float)
    selection_reason: Mapped[str] = mapped_column(String(100), nullable=False)
    attempt_id: Mapped[UUID | None] = mapped_column(ForeignKey("question_attempts.id", ondelete="SET NULL"))
    difficulty_before: Mapped[float] = mapped_column(Float, nullable=False)
    difficulty_after: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    adaptive_session: Mapped[AdaptiveRepairSession] = relationship(back_populates="items")
    decision: Mapped["AdaptiveRepairDecision | None"] = relationship(back_populates="item", uselist=False, cascade="all, delete-orphan")


class AdaptiveRepairDecision(Base):
    __tablename__ = "adaptive_repair_decisions"
    __table_args__ = (
        UniqueConstraint("adaptive_repair_item_id", name="uq_adaptive_repair_decision_item"),
        UniqueConstraint("adaptive_repair_session_id", "decision_index", name="uq_adaptive_repair_decision_index"),
        CheckConstraint("decision_index > 0", name="decision_index_positive"),
        CheckConstraint("difficulty_before BETWEEN 0 AND 1", name="difficulty_before_range"),
        CheckConstraint("difficulty_after BETWEEN 0 AND 1", name="difficulty_after_range"),
        Index("ix_adaptive_repair_decision_session", "adaptive_repair_session_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    adaptive_repair_session_id: Mapped[UUID] = mapped_column(ForeignKey("adaptive_repair_sessions.id", ondelete="CASCADE"), nullable=False)
    adaptive_repair_item_id: Mapped[UUID] = mapped_column(ForeignKey("adaptive_repair_items.id", ondelete="CASCADE"), nullable=False)
    decision_index: Mapped[int] = mapped_column(Integer, nullable=False)
    phase_before: Mapped[AdaptiveRepairPhase] = mapped_column(Enum(AdaptiveRepairPhase, native_enum=False, name="adaptive_repair_decision_phase_before"), nullable=False)
    phase_after: Mapped[AdaptiveRepairPhase] = mapped_column(Enum(AdaptiveRepairPhase, native_enum=False, name="adaptive_repair_decision_phase_after"), nullable=False)
    difficulty_before: Mapped[float] = mapped_column(Float, nullable=False)
    difficulty_after: Mapped[float] = mapped_column(Float, nullable=False)
    reason_code: Mapped[AdaptiveRepairDecisionReason] = mapped_column(Enum(AdaptiveRepairDecisionReason, native_enum=False, name="adaptive_repair_decision_reason"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    item: Mapped[AdaptiveRepairItem] = relationship(back_populates="decision")
