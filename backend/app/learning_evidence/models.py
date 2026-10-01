from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, UniqueConstraint, Uuid, event, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.practice.models import EvaluationStatus


class LearningEvidenceSourceKind(StrEnum):
    PRACTICE_QUESTION = "PRACTICE_QUESTION"
    ASSIGNMENT_CANONICAL_QUESTION = "ASSIGNMENT_CANONICAL_QUESTION"
    TEACHER_MATERIAL_ITEM = "TEACHER_MATERIAL_ITEM"


class LearningEvidenceEvent(Base):
    __tablename__ = "learning_evidence_events"
    __table_args__ = (
        UniqueConstraint("source_kind", "source_entity_id", name="uq_learning_evidence_source"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score_range"),
        CheckConstraint("difficulty IS NULL OR difficulty BETWEEN 0 AND 1", name="difficulty_range"),
        CheckConstraint("response_time_seconds IS NULL OR response_time_seconds > 0", name="response_time_positive"),
        CheckConstraint("hint_count >= 0", name="hint_count_nonnegative"),
        Index("ix_learning_evidence_student_occurred", "student_id", "occurred_at"),
        Index("ix_learning_evidence_assignment", "assignment_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    classroom_id: Mapped[UUID | None] = mapped_column(ForeignKey("classrooms.id", ondelete="SET NULL"))
    teaching_plan_id: Mapped[UUID | None] = mapped_column(ForeignKey("teaching_plans.id", ondelete="SET NULL"))
    assignment_id: Mapped[UUID | None] = mapped_column(ForeignKey("assignments.id", ondelete="SET NULL"))
    source_kind: Mapped[LearningEvidenceSourceKind] = mapped_column(Enum(LearningEvidenceSourceKind, native_enum=False, name="learning_evidence_source_kind"), nullable=False)
    source_entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    response_time_seconds: Mapped[float | None] = mapped_column(Float)
    hint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluation_status: Mapped[EvaluationStatus] = mapped_column(Enum(EvaluationStatus, native_enum=False, name="learning_evidence_evaluation_status"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    concepts: Mapped[list["LearningEvidenceConcept"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    problem_types: Mapped[list["LearningEvidenceProblemType"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


@event.listens_for(LearningEvidenceEvent, "before_update")
@event.listens_for(LearningEvidenceEvent, "before_delete")
def _immutable_evidence(*_: object) -> None:
    raise ValueError("LearningEvidenceEvent is append-only")


class LearningEvidenceConcept(Base):
    __tablename__ = "learning_evidence_concepts"
    __table_args__ = (UniqueConstraint("event_id", "concept_id", name="uq_learning_evidence_concept"), CheckConstraint("weight > 0 AND weight <= 1", name="weight_range"))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("learning_evidence_events.id", ondelete="CASCADE"), nullable=False)
    concept_id: Mapped[UUID] = mapped_column(ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)


class LearningEvidenceProblemType(Base):
    __tablename__ = "learning_evidence_problem_types"
    __table_args__ = (UniqueConstraint("event_id", "problem_type_id", name="uq_learning_evidence_problem_type"), CheckConstraint("weight > 0 AND weight <= 1", name="weight_range"))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("learning_evidence_events.id", ondelete="CASCADE"), nullable=False)
    problem_type_id: Mapped[UUID] = mapped_column(ForeignKey("problem_types.id", ondelete="RESTRICT"), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
