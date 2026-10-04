"""Pydantic schemas for question acquisition planning and source management."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.question_acquisition.models import (
    QuestionAcquisitionDiscoveryMethod,
    QuestionAcquisitionExtractionStatus,
    QuestionAcquisitionRequestStatus,
    QuestionAcquisitionRightsStatus,
    QuestionAcquisitionSourceKind,
    QuestionAcquisitionSourceStatus,
    QuestionAcquisitionStrategy,
)
from app.question_supply.models import (
    QuestionSupplyReasonCode,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.questions.models import QuestionStatus, QuestionType


class QuestionAcquisitionExistingCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: UUID
    question_id: UUID
    difficulty_in_band: bool
    runtime_eligible: bool
    selection_rank: int
    selection_score: float | None = None
    created_at: datetime

    # Question metadata projection if loaded
    question_status: QuestionStatus | None = None
    question_type: QuestionType | None = None
    difficulty: float | None = None


class QuestionAcquisitionPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artifact_id: UUID
    page_number: int
    text: str
    text_sha256: str
    char_count: int
    created_at: datetime


class QuestionAcquisitionArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sha256: str
    mime_type: str
    file_size_bytes: int
    page_count: int | None = None
    extraction_status: QuestionAcquisitionExtractionStatus
    created_at: datetime


class QuestionAcquisitionSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: UUID
    source_kind: QuestionAcquisitionSourceKind
    discovery_method: QuestionAcquisitionDiscoveryMethod
    original_url: str | None = None
    normalized_url: str | None = None
    url_hash: str | None = None
    title: str | None = None
    publisher: str | None = None
    source_year: int | None = None
    rights_status: QuestionAcquisitionRightsStatus
    status: QuestionAcquisitionSourceStatus
    provenance_note: str
    registered_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    fetched_at: datetime | None = None
    failure_code: str | None = None
    failure_detail: str | None = None


class QuestionAcquisitionRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gap_id: UUID
    attempt_index: int
    strategy: QuestionAcquisitionStrategy
    status: QuestionAcquisitionRequestStatus
    subject_id: UUID
    use_case: QuestionSupplyUseCase
    target_type: QuestionSupplyTargetType
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    misconception_definition_id: UUID | None = None
    difficulty_min: float
    difficulty_max: float
    desired_difficulty: float | None = None
    minimum_required_count: int
    preferred_count: int
    shortage_reason_code: QuestionSupplyReasonCode | None = None

    approved_eligible_count_snapshot: int
    approved_in_band_count_snapshot: int
    pipeline_candidate_count_snapshot: int
    pipeline_runtime_eligible_count_snapshot: int

    required_new_candidate_count: int
    existing_candidate_count: int
    external_candidate_target_count: int

    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    failure_code: str | None = None


class QuestionAcquisitionRequestDetailRead(QuestionAcquisitionRequestRead):
    existing_candidates: list[QuestionAcquisitionExistingCandidateRead] = []
    sources: list[QuestionAcquisitionSourceRead] = []
    artifacts: list[QuestionAcquisitionArtifactRead] = []


class RegisterSourceRequest(BaseModel):
    source_kind: QuestionAcquisitionSourceKind = QuestionAcquisitionSourceKind.PDF_URL
    discovery_method: QuestionAcquisitionDiscoveryMethod = QuestionAcquisitionDiscoveryMethod.ADMIN_URL
    url: str | None = None
    title: str | None = None
    publisher: str | None = None
    source_year: int | None = Field(default=None, ge=1900, le=2100)
    provenance_note: str = Field(min_length=1)


class BlockSourceRequest(BaseModel):
    reason: str = Field(min_length=1)


class CancelRequestPayload(BaseModel):
    reason: str | None = None
