"""Domain models for question acquisition planning, sources, and staging artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import uuid

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
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.question_supply.models import (
    QuestionSupplyReasonCode,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.questions.models import Question


class QuestionAcquisitionStrategy(StrEnum):
    REVIEW_EXISTING_PIPELINE = "REVIEW_EXISTING_PIPELINE"
    MIXED = "MIXED"
    EXTERNAL_SOURCE_REQUIRED = "EXTERNAL_SOURCE_REQUIRED"


class QuestionAcquisitionRequestStatus(StrEnum):
    PLANNED = "PLANNED"
    AWAITING_SOURCE = "AWAITING_SOURCE"
    ACQUIRING = "ACQUIRING"
    STAGED = "STAGED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class QuestionAcquisitionSourceKind(StrEnum):
    PDF_URL = "PDF_URL"
    MANUAL_PDF_UPLOAD = "MANUAL_PDF_UPLOAD"
    GOOGLE_DRIVE_REFERENCE = "GOOGLE_DRIVE_REFERENCE"
    OTHER_REFERENCE = "OTHER_REFERENCE"


class QuestionAcquisitionDiscoveryMethod(StrEnum):
    ADMIN_URL = "ADMIN_URL"
    ADMIN_UPLOAD = "ADMIN_UPLOAD"
    KNOWN_SOURCE_REGISTRY = "KNOWN_SOURCE_REGISTRY"
    EXTERNAL_DISCOVERY_PROVIDER = "EXTERNAL_DISCOVERY_PROVIDER"


class QuestionAcquisitionRightsStatus(StrEnum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class QuestionAcquisitionSourceStatus(StrEnum):
    REGISTERED = "REGISTERED"
    FETCHING = "FETCHING"
    FETCHED = "FETCHED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class QuestionAcquisitionExtractionStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class QuestionAcquisitionRequest(Base):
    """Aggregate acquisition request plan generated from a QuestionSupplyGap."""

    __tablename__ = "question_acquisition_requests"
    __table_args__ = (
        UniqueConstraint("gap_id", "attempt_index", name="uq_acquisition_requests_gap_attempt"),
        CheckConstraint("attempt_index >= 1", name="ck_acquisition_requests_attempt_positive"),
        CheckConstraint(
            "minimum_required_count > 0 AND preferred_count >= minimum_required_count",
            name="ck_acquisition_requests_counts",
        ),
        CheckConstraint(
            "required_new_candidate_count >= 0 AND existing_candidate_count >= 0 AND external_candidate_target_count >= 0",
            name="ck_acquisition_requests_candidate_counts",
        ),
        CheckConstraint(
            "difficulty_min >= 0.0 AND difficulty_min <= difficulty_max AND difficulty_max <= 1.0",
            name="ck_acquisition_requests_difficulty_range",
        ),
        Index("ix_acquisition_requests_gap_status", "gap_id", "status"),
        Index("ix_acquisition_requests_status_created", "status", "created_at"),
        Index("ix_acquisition_requests_subject_status", "subject_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gap_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("question_supply_gaps.id", ondelete="CASCADE"), nullable=False
    )
    attempt_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    strategy: Mapped[QuestionAcquisitionStrategy] = mapped_column(
        Enum(QuestionAcquisitionStrategy, native_enum=False, name="question_acquisition_strategy"),
        nullable=False,
    )
    status: Mapped[QuestionAcquisitionRequestStatus] = mapped_column(
        Enum(
            QuestionAcquisitionRequestStatus,
            native_enum=False,
            name="question_acquisition_request_status",
        ),
        nullable=False,
        default=QuestionAcquisitionRequestStatus.PLANNED,
        server_default="PLANNED",
    )

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

    difficulty_min: Mapped[float] = mapped_column(Float, nullable=False)
    difficulty_max: Mapped[float] = mapped_column(Float, nullable=False)
    desired_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)

    minimum_required_count: Mapped[int] = mapped_column(Integer, nullable=False)
    preferred_count: Mapped[int] = mapped_column(Integer, nullable=False)

    shortage_reason_code: Mapped[QuestionSupplyReasonCode | None] = mapped_column(
        Enum(
            QuestionSupplyReasonCode,
            native_enum=False,
            name="question_supply_gap_reason_code",
        ),
        nullable=True,
    )

    approved_eligible_count_snapshot: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    approved_in_band_count_snapshot: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    pipeline_candidate_count_snapshot: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    pipeline_runtime_eligible_count_snapshot: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    required_new_candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    existing_candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    external_candidate_target_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    existing_candidates: Mapped[list[QuestionAcquisitionExistingCandidate]] = relationship(
        "QuestionAcquisitionExistingCandidate",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="QuestionAcquisitionExistingCandidate.selection_rank",
    )
    sources: Mapped[list[QuestionAcquisitionSource]] = relationship(
        "QuestionAcquisitionSource",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="QuestionAcquisitionSource.created_at",
    )


class QuestionAcquisitionExistingCandidate(Base):
    """Frozen links to existing DRAFT or REVIEW questions identified during planning."""

    __tablename__ = "question_acquisition_existing_candidates"
    __table_args__ = (
        UniqueConstraint("request_id", "question_id", name="uq_acquisition_existing_candidates_req_q"),
        CheckConstraint("selection_rank >= 1", name="ck_acquisition_existing_candidates_rank_positive"),
        Index("ix_acquisition_existing_candidates_req_rank", "request_id", "selection_rank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("question_acquisition_requests.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )

    difficulty_in_band: Mapped[bool] = mapped_column(Boolean, nullable=False)
    runtime_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    selection_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    selection_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    request: Mapped[QuestionAcquisitionRequest] = relationship(
        "QuestionAcquisitionRequest", back_populates="existing_candidates"
    )
    question: Mapped[Question] = relationship("Question")

    @property
    def question_status(self):
        return self.question.status if self.question else None

    @property
    def question_type(self):
        return self.question.question_type if self.question else None

    @property
    def difficulty(self):
        return self.question.difficulty if self.question else None


class QuestionAcquisitionSource(Base):
    """External source entry registered against an acquisition request."""

    __tablename__ = "question_acquisition_sources"
    __table_args__ = (
        UniqueConstraint("request_id", "url_hash", name="uq_acquisition_sources_req_url_hash"),
        Index("ix_acquisition_sources_request_status", "request_id", "status"),
        Index("ix_acquisition_sources_url_hash", "url_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("question_acquisition_requests.id", ondelete="CASCADE"), nullable=False
    )

    source_kind: Mapped[QuestionAcquisitionSourceKind] = mapped_column(
        Enum(
            QuestionAcquisitionSourceKind,
            native_enum=False,
            name="question_acquisition_source_kind",
        ),
        nullable=False,
    )
    discovery_method: Mapped[QuestionAcquisitionDiscoveryMethod] = mapped_column(
        Enum(
            QuestionAcquisitionDiscoveryMethod,
            native_enum=False,
            name="question_acquisition_discovery_method",
        ),
        nullable=False,
    )

    original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    rights_status: Mapped[QuestionAcquisitionRightsStatus] = mapped_column(
        Enum(
            QuestionAcquisitionRightsStatus,
            native_enum=False,
            name="question_acquisition_rights_status",
        ),
        nullable=False,
        default=QuestionAcquisitionRightsStatus.REVIEW_REQUIRED,
        server_default="REVIEW_REQUIRED",
    )
    status: Mapped[QuestionAcquisitionSourceStatus] = mapped_column(
        Enum(
            QuestionAcquisitionSourceStatus,
            native_enum=False,
            name="question_acquisition_source_status",
        ),
        nullable=False,
        default=QuestionAcquisitionSourceStatus.REGISTERED,
        server_default="REGISTERED",
    )

    provenance_note: Mapped[str] = mapped_column(Text, nullable=False)
    registered_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped[QuestionAcquisitionRequest] = relationship(
        "QuestionAcquisitionRequest", back_populates="sources"
    )
    source_artifacts: Mapped[list[QuestionAcquisitionSourceArtifact]] = relationship(
        "QuestionAcquisitionSourceArtifact",
        back_populates="source",
        cascade="all, delete-orphan",
    )


class QuestionAcquisitionArtifact(Base):
    """Globally deduplicated binary artifact (e.g. PDF) stored immutably on disk."""

    __tablename__ = "question_acquisition_artifacts"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_acquisition_artifacts_sha256"),
        CheckConstraint("file_size_bytes > 0", name="ck_acquisition_artifacts_file_size_positive"),
        CheckConstraint("length(sha256) = 64", name="ck_acquisition_artifacts_sha256_length"),
        CheckConstraint(
            "page_count IS NULL OR page_count > 0",
            name="ck_acquisition_artifacts_page_count_positive",
        ),
        Index("ix_acquisition_artifacts_sha256", "sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="application/pdf", server_default="application/pdf"
    )
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)

    extraction_status: Mapped[QuestionAcquisitionExtractionStatus] = mapped_column(
        Enum(
            QuestionAcquisitionExtractionStatus,
            native_enum=False,
            name="question_acquisition_extraction_status",
        ),
        nullable=False,
        default=QuestionAcquisitionExtractionStatus.PENDING,
        server_default="PENDING",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    pages: Mapped[list[QuestionAcquisitionPage]] = relationship(
        "QuestionAcquisitionPage",
        back_populates="artifact",
        cascade="all, delete-orphan",
        order_by="QuestionAcquisitionPage.page_number",
    )
    source_links: Mapped[list[QuestionAcquisitionSourceArtifact]] = relationship(
        "QuestionAcquisitionSourceArtifact",
        back_populates="artifact",
        cascade="all, delete-orphan",
    )


class QuestionAcquisitionSourceArtifact(Base):
    """M:N link between an acquisition source record and a physical deduplicated artifact."""

    __tablename__ = "question_acquisition_source_artifacts"
    __table_args__ = (
        UniqueConstraint("source_id", "artifact_id", name="uq_acquisition_source_artifacts"),
        Index("ix_acquisition_source_artifacts_source", "source_id"),
        Index("ix_acquisition_source_artifacts_artifact", "artifact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("question_acquisition_sources.id", ondelete="CASCADE"), nullable=False
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("question_acquisition_artifacts.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    source: Mapped[QuestionAcquisitionSource] = relationship(
        "QuestionAcquisitionSource", back_populates="source_artifacts"
    )
    artifact: Mapped[QuestionAcquisitionArtifact] = relationship(
        "QuestionAcquisitionArtifact", back_populates="source_links"
    )


class QuestionAcquisitionPage(Base):
    """Page-by-page extracted text evidence from an acquisition artifact."""

    __tablename__ = "question_acquisition_pages"
    __table_args__ = (
        UniqueConstraint("artifact_id", "page_number", name="uq_acquisition_pages_artifact_page"),
        CheckConstraint("page_number >= 1", name="ck_acquisition_pages_page_positive"),
        CheckConstraint("char_count >= 0", name="ck_acquisition_pages_char_count_nonnegative"),
        CheckConstraint(
            "length(text_sha256) = 64", name="ck_acquisition_pages_text_sha256_length"
        ),
        Index("ix_acquisition_pages_artifact_page", "artifact_id", "page_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("question_acquisition_artifacts.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    artifact: Mapped[QuestionAcquisitionArtifact] = relationship(
        "QuestionAcquisitionArtifact", back_populates="pages"
    )
