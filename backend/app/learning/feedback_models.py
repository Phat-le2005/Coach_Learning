from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.knowledge_gap.models import RootCauseVerificationTargetType
from app.recommendations.schemas import PriorityReasonCode, PriorityTargetType


class LearningFeedbackAction(StrEnum):
    RETURN_TO_CURRENT_LEARNING = "RETURN_TO_CURRENT_LEARNING"
    REVIEW_LATER = "REVIEW_LATER"
    RETRY_REPAIR = "RETRY_REPAIR"
    COLLECT_MORE_EVIDENCE = "COLLECT_MORE_EVIDENCE"
    QUESTION_SUPPLY_GAP = "QUESTION_SUPPLY_GAP"
    NO_ACTIVE_LEARNING = "NO_ACTIVE_LEARNING"


class LearningFeedbackReasonCode(StrEnum):
    REPAIR_RESOLVED_REVIEW_SCHEDULED = "REPAIR_RESOLVED_REVIEW_SCHEDULED"
    REPAIR_RESOLVED_TARGET_STABLE = "REPAIR_RESOLVED_TARGET_STABLE"
    REPAIR_NEEDS_MORE_RETRY_AVAILABLE = "REPAIR_NEEDS_MORE_RETRY_AVAILABLE"
    REPAIR_RETRY_LIMIT_REACHED = "REPAIR_RETRY_LIMIT_REACHED"
    REPAIR_BANK_EXHAUSTED = "REPAIR_BANK_EXHAUSTED"
    REPAIR_NEEDS_MORE_NO_QUESTIONS = "REPAIR_NEEDS_MORE_NO_QUESTIONS"
    CURRENT_LESSON_AVAILABLE = "CURRENT_LESSON_AVAILABLE"
    NO_ACTIVE_TEACHING_PLAN = "NO_ACTIVE_TEACHING_PLAN"
    NO_ACTIVE_LEARNING_PRIORITY = "NO_ACTIVE_LEARNING_PRIORITY"


class LearningFeedbackDecision(Base):
    __tablename__ = "learning_feedback_decisions"
    __table_args__ = (
        UniqueConstraint("adaptive_repair_session_id", name="uq_learning_feedback_adaptive_repair_session"),
        CheckConstraint("repair_cycle_index >= 1", name="ck_learning_feedback_decisions_repair_cycle_index_positive"),
        Index("ix_learning_feedback_student_subject", "student_id", "subject_id"),
        Index("ix_learning_feedback_session", "adaptive_repair_session_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    adaptive_repair_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("adaptive_repair_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    action: Mapped[LearningFeedbackAction] = mapped_column(
        Enum(LearningFeedbackAction, native_enum=False, name="learning_feedback_action"),
        nullable=False,
    )
    reason_code: Mapped[LearningFeedbackReasonCode] = mapped_column(
        Enum(LearningFeedbackReasonCode, native_enum=False, name="learning_feedback_reason_code"),
        nullable=False,
    )

    target_type: Mapped[RootCauseVerificationTargetType | None] = mapped_column(
        Enum(RootCauseVerificationTargetType, native_enum=False, name="learning_feedback_target_type"),
        nullable=True,
    )
    target_concept_id: Mapped[UUID | None] = mapped_column(ForeignKey("concepts.id", ondelete="RESTRICT"))
    target_problem_type_id: Mapped[UUID | None] = mapped_column(ForeignKey("problem_types.id", ondelete="RESTRICT"))

    next_target_type: Mapped[PriorityTargetType | None] = mapped_column(
        Enum(PriorityTargetType, native_enum=False, name="learning_feedback_next_target_type"),
        nullable=True,
    )
    next_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT", name="fk_learning_feedback_next_concept"),
        nullable=True,
    )
    next_problem_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT", name="fk_learning_feedback_next_problem_type"),
        nullable=True,
    )
    next_reason_code: Mapped[PriorityReasonCode | None] = mapped_column(
        Enum(PriorityReasonCode, native_enum=False, name="learning_feedback_next_reason_code"),
        nullable=True,
    )

    recommended_question_id: Mapped[UUID | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"))
    review_schedule_id: Mapped[UUID | None] = mapped_column(ForeignKey("review_schedules.id", ondelete="SET NULL"))

    repair_cycle_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    adaptive_session: Mapped["AdaptiveRepairSession"] = relationship(back_populates="feedback_decision")
    review_schedule: Mapped["ReviewSchedule | None"] = relationship()
    recommended_question: Mapped["Question | None"] = relationship()
