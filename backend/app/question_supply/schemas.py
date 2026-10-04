"""Pydantic schemas for question bank sufficiency and supply gaps."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.question_supply.models import (
    QuestionSupplyHealth,
    QuestionSupplyObservationSourceKind,
    QuestionSupplyReasonCode,
    QuestionSupplySeverity,
    QuestionSupplyStatus,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)


class QuestionBankSufficiencyReport(BaseModel):
    """Evaluation report on question availability for a specific learning requirement."""

    model_config = ConfigDict(from_attributes=True)

    subject_id: UUID
    use_case: QuestionSupplyUseCase
    target_type: QuestionSupplyTargetType
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    misconception_definition_id: UUID | None = None

    desired_difficulty: float | None = None
    difficulty_min: float
    difficulty_max: float

    minimum_required_count: int
    preferred_count: int

    approved_eligible_count: int
    approved_in_band_count: int
    approved_target_count: int | None = None
    approved_type_eligible_count: int | None = None

    fresh_eligible_count: int | None = None
    fresh_in_band_count: int | None = None
    excluded_exposure_count: int = 0

    pipeline_candidate_count: int = 0
    pipeline_runtime_eligible_count: int = 0

    health: QuestionSupplyHealth
    severity: QuestionSupplySeverity
    reason_code: QuestionSupplyReasonCode | None = None

    is_startable: bool


class QuestionSupplyGapObservationRead(BaseModel):
    """Read representation of an observation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gap_id: UUID
    student_id: UUID | None = None
    source_kind: QuestionSupplyObservationSourceKind
    source_entity_id: UUID | None = None
    reason_code: QuestionSupplyReasonCode

    observed_approved_eligible_count: int
    observed_approved_in_band_count: int
    observed_fresh_eligible_count: int | None = None
    observed_fresh_in_band_count: int | None = None
    observed_excluded_exposure_count: int | None = None

    created_at: datetime


class QuestionSupplyGapRead(BaseModel):
    """Read representation of an aggregate question supply gap."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    signature: str

    subject_id: UUID
    use_case: QuestionSupplyUseCase
    target_type: QuestionSupplyTargetType
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    misconception_definition_id: UUID | None = None

    desired_difficulty: float | None = None
    difficulty_min: float
    difficulty_max: float

    minimum_required_count: int
    preferred_count: int

    approved_eligible_count: int
    approved_in_band_count: int
    pipeline_candidate_count: int
    pipeline_runtime_eligible_count: int = 0

    severity: QuestionSupplySeverity
    status: QuestionSupplyStatus
    reason_code: QuestionSupplyReasonCode

    demand_count: int

    first_observed_at: datetime
    last_observed_at: datetime
    last_assessed_at: datetime
    created_at: datetime
    updated_at: datetime


class QuestionSupplyGapDetailRead(QuestionSupplyGapRead):
    """Detailed read representation including observation history."""

    observations: list[QuestionSupplyGapObservationRead] = Field(default_factory=list)


class ManualAssessmentRequest(BaseModel):
    """Request payload for manual/read-only sufficiency assessment."""

    model_config = ConfigDict(extra="forbid")

    subject_id: UUID
    use_case: QuestionSupplyUseCase
    target_type: QuestionSupplyTargetType
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    misconception_definition_id: UUID | None = None
    desired_difficulty: float | None = Field(default=None, ge=0.0, le=1.0)
    student_id: UUID | None = None
    minimum_required_count: int | None = Field(default=None, gt=0)
    preferred_count: int | None = Field(default=None, gt=0)
