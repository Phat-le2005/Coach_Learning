"""Persistence models for reviewed acquisition question candidates."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
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
    UniqueConstraint,
    Uuid,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.questions.models import CognitiveLevel, QuestionType


class QuestionValidationBatchStatus(StrEnum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    READY_FOR_PROMOTION = "READY_FOR_PROMOTION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class QuestionValidationCandidateStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    PROMOTED = "PROMOTED"


class QuestionValidationRightsDecision(StrEnum):
    PENDING = "PENDING"
    ALLOW_DRAFT = "ALLOW_DRAFT"
    BLOCKED = "BLOCKED"


class QuestionValidationCheckType(StrEnum):
    STRUCTURE = "STRUCTURE"
    ANSWER_INTEGRITY = "ANSWER_INTEGRITY"
    TAXONOMY_INTEGRITY = "TAXONOMY_INTEGRITY"
    DUPLICATE = "DUPLICATE"
    VISUAL_INTEGRITY = "VISUAL_INTEGRITY"
    ACADEMIC_REVIEW = "ACADEMIC_REVIEW"
    ANSWER_REVIEW = "ANSWER_REVIEW"
    TAXONOMY_REVIEW = "TAXONOMY_REVIEW"
    RIGHTS_REVIEW = "RIGHTS_REVIEW"


class QuestionValidationCheckResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"


SYSTEM_CHECK_TYPES = frozenset(
    {
        QuestionValidationCheckType.STRUCTURE,
        QuestionValidationCheckType.ANSWER_INTEGRITY,
        QuestionValidationCheckType.TAXONOMY_INTEGRITY,
        QuestionValidationCheckType.DUPLICATE,
        QuestionValidationCheckType.VISUAL_INTEGRITY,
    }
)
MANUAL_CHECK_TYPES = frozenset(set(QuestionValidationCheckType) - SYSTEM_CHECK_TYPES)
REQUIRED_CHECK_TYPES = frozenset(QuestionValidationCheckType)


class QuestionValidationBatch(Base):
    __tablename__ = "question_validation_batches"
    __table_args__ = (
        UniqueConstraint(
            "acquisition_request_id",
            "attempt_index",
            name="uq_question_validation_batches_request_attempt",
        ),
        CheckConstraint("attempt_index >= 1", name="ck_question_validation_batches_attempt"),
        CheckConstraint(
            "target_candidate_count_snapshot > 0",
            name="ck_question_validation_batches_target_positive",
        ),
        Index(
            "ix_question_validation_batches_request_status",
            "acquisition_request_id",
            "status",
        ),
        Index("ix_question_validation_batches_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    acquisition_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_acquisition_requests.id", ondelete="CASCADE"), nullable=False
    )
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[QuestionValidationBatchStatus] = mapped_column(
        Enum(
            QuestionValidationBatchStatus,
            native_enum=False,
            name="question_validation_batch_status",
        ),
        nullable=False,
        default=QuestionValidationBatchStatus.OPEN,
        server_default="OPEN",
    )
    target_candidate_count_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    acquisition_request = relationship("QuestionAcquisitionRequest")
    candidates: Mapped[list[QuestionValidationCandidate]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionValidationCandidate.created_at",
    )


class QuestionValidationCandidate(Base):
    __tablename__ = "question_validation_candidates"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_question_validation_candidates_revision"),
        CheckConstraint("length(trim(content)) > 0", name="ck_question_validation_candidates_content"),
        CheckConstraint("length(content_hash) = 64", name="ck_question_validation_candidates_hash"),
        CheckConstraint(
            "difficulty IS NULL OR difficulty BETWEEN 0.0 AND 1.0",
            name="ck_question_validation_candidates_difficulty",
        ),
        CheckConstraint(
            "exam_weight IS NULL OR exam_weight BETWEEN 0.0 AND 1.0",
            name="ck_question_validation_candidates_exam_weight",
        ),
        CheckConstraint(
            "source_year IS NULL OR source_year BETWEEN 1900 AND 2100",
            name="ck_question_validation_candidates_source_year",
        ),
        Index("ix_question_validation_candidates_batch_status", "batch_id", "status"),
        Index("ix_question_validation_candidates_source_status", "source_id", "status"),
        Index("ix_question_validation_candidates_content_hash", "content_hash"),
        Index("ix_question_validation_candidates_promoted_question", "promoted_question_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_validation_batches.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_acquisition_sources.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[QuestionValidationCandidateStatus] = mapped_column(
        Enum(
            QuestionValidationCandidateStatus,
            native_enum=False,
            name="question_validation_candidate_status",
        ),
        nullable=False,
        default=QuestionValidationCandidateStatus.DRAFT,
        server_default="DRAFT",
    )
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, native_enum=False, name="question_validation_question_type"),
        nullable=False,
    )
    difficulty: Mapped[float | None] = mapped_column(Float)
    correct_answer: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    cognitive_level: Mapped[CognitiveLevel | None] = mapped_column(
        Enum(
            CognitiveLevel,
            native_enum=False,
            name="question_validation_cognitive_level",
        )
    )
    exam_weight: Mapped[float | None] = mapped_column(Float)
    source_year: Mapped[int | None] = mapped_column(Integer)
    visual_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    rights_decision: Mapped[QuestionValidationRightsDecision] = mapped_column(
        Enum(
            QuestionValidationRightsDecision,
            native_enum=False,
            name="question_validation_rights_decision",
        ),
        nullable=False,
        default=QuestionValidationRightsDecision.PENDING,
        server_default="PENDING",
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    promoted_question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    promoted_revision: Mapped[int | None] = mapped_column(Integer)
    promoted_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    batch: Mapped[QuestionValidationBatch] = relationship(back_populates="candidates")
    spans: Mapped[list[QuestionValidationCandidateSpan]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True,
        order_by="QuestionValidationCandidateSpan.order_index"
    )
    options: Mapped[list[QuestionValidationCandidateOption]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True,
        order_by="QuestionValidationCandidateOption.order_index"
    )
    concept_links: Mapped[list[QuestionValidationCandidateConcept]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )
    problem_type_links: Mapped[list[QuestionValidationCandidateProblemType]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )
    learning_outcome_links: Mapped[list[QuestionValidationCandidateLearningOutcome]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )
    checks: Mapped[list[QuestionValidationCheck]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True,
        order_by="QuestionValidationCheck.checked_at"
    )


class QuestionValidationCandidateSpan(Base):
    __tablename__ = "question_validation_candidate_spans"
    __table_args__ = (
        UniqueConstraint("candidate_id", "order_index", name="uq_validation_spans_candidate_order"),
        CheckConstraint("order_index >= 0", name="ck_validation_spans_order"),
        CheckConstraint("start_char >= 0", name="ck_validation_spans_start"),
        CheckConstraint("end_char > start_char", name="ck_validation_spans_range"),
        CheckConstraint("length(trim(excerpt)) > 0", name="ck_validation_spans_excerpt"),
        CheckConstraint("length(excerpt_sha256) = 64", name="ck_validation_spans_hash"),
        Index("ix_validation_spans_page", "page_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_acquisition_pages.id", ondelete="RESTRICT"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    candidate: Mapped[QuestionValidationCandidate] = relationship(back_populates="spans")


class QuestionValidationCandidateOption(Base):
    __tablename__ = "question_validation_candidate_options"
    __table_args__ = (
        UniqueConstraint("candidate_id", "label", name="uq_validation_options_candidate_label"),
        UniqueConstraint("candidate_id", "order_index", name="uq_validation_options_candidate_order"),
        CheckConstraint("length(trim(label)) > 0", name="ck_validation_options_label"),
        CheckConstraint("length(trim(content)) > 0", name="ck_validation_options_content"),
        CheckConstraint("order_index >= 0", name="ck_validation_options_order"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate: Mapped[QuestionValidationCandidate] = relationship(back_populates="options")


class QuestionValidationCandidateConcept(Base):
    __tablename__ = "question_validation_candidate_concepts"
    __table_args__ = (CheckConstraint("weight > 0.0 AND weight <= 1.0", name="ck_validation_concepts_weight"),)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT"), primary_key=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    candidate: Mapped[QuestionValidationCandidate] = relationship(back_populates="concept_links")


class QuestionValidationCandidateProblemType(Base):
    __tablename__ = "question_validation_candidate_problem_types"
    __table_args__ = (
        CheckConstraint(
            "weight IS NULL OR (weight > 0.0 AND weight <= 1.0)",
            name="ck_validation_problem_types_weight",
        ),
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), primary_key=True
    )
    problem_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("problem_types.id", ondelete="RESTRICT"), primary_key=True
    )
    weight: Mapped[float | None] = mapped_column(Float)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    candidate: Mapped[QuestionValidationCandidate] = relationship(back_populates="problem_type_links")


class QuestionValidationCandidateLearningOutcome(Base):
    __tablename__ = "question_validation_candidate_learning_outcomes"
    __table_args__ = (
        CheckConstraint(
            "weight IS NULL OR (weight > 0.0 AND weight <= 1.0)",
            name="ck_validation_learning_outcomes_weight",
        ),
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), primary_key=True
    )
    learning_outcome_id: Mapped[UUID] = mapped_column(
        ForeignKey("learning_outcomes.id", ondelete="RESTRICT"), primary_key=True
    )
    weight: Mapped[float | None] = mapped_column(Float)
    candidate: Mapped[QuestionValidationCandidate] = relationship(back_populates="learning_outcome_links")


class QuestionValidationCheck(Base):
    __tablename__ = "question_validation_checks"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "candidate_revision", "check_type",
            name="uq_validation_checks_candidate_revision_type",
        ),
        CheckConstraint("candidate_revision >= 1", name="ck_validation_checks_revision"),
        Index("ix_validation_checks_candidate_revision", "candidate_id", "candidate_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_validation_candidates.id", ondelete="CASCADE"), nullable=False
    )
    candidate_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    check_type: Mapped[QuestionValidationCheckType] = mapped_column(
        Enum(QuestionValidationCheckType, native_enum=False, name="question_validation_check_type"),
        nullable=False,
    )
    result: Mapped[QuestionValidationCheckResult] = mapped_column(
        Enum(QuestionValidationCheckResult, native_enum=False, name="question_validation_check_result"),
        nullable=False,
    )
    checked_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    candidate: Mapped[QuestionValidationCandidate] = relationship(back_populates="checks")
