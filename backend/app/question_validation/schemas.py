"""API contracts for reviewed acquisition candidate validation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.question_validation.models import (
    QuestionValidationBatchStatus,
    QuestionValidationCandidateStatus,
    QuestionValidationCheckResult,
    QuestionValidationCheckType,
    QuestionValidationRightsDecision,
)
from app.questions.models import CognitiveLevel, QuestionType


class StrictInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True
    )


class CandidateSpanInput(StrictInput):
    page_id: UUID
    order_index: int = Field(ge=0)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "CandidateSpanInput":
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self


class CandidateOptionInput(StrictInput):
    label: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=1, max_length=10000)
    order_index: int = Field(ge=0)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        return value.upper()


class CandidateConceptInput(StrictInput):
    concept_id: UUID
    weight: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)


class CandidateProblemTypeInput(StrictInput):
    problem_type_id: UUID
    weight: float | None = Field(default=None, gt=0.0, le=1.0, allow_inf_nan=False)
    is_primary: bool = False


class CandidateLearningOutcomeInput(StrictInput):
    learning_outcome_id: UUID
    weight: float | None = Field(default=None, gt=0.0, le=1.0, allow_inf_nan=False)


class CandidateSemanticInput(StrictInput):
    content: str = Field(min_length=1, max_length=20000)
    question_type: QuestionType
    difficulty: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    correct_answer: str | None = Field(default=None, min_length=1, max_length=10000)
    explanation: str | None = Field(default=None, min_length=1, max_length=20000)
    cognitive_level: CognitiveLevel | None = None
    exam_weight: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    source_year: int | None = Field(default=None, ge=1900, le=2100)
    visual_required: bool = False
    rights_decision: QuestionValidationRightsDecision = QuestionValidationRightsDecision.PENDING
    spans: list[CandidateSpanInput] = Field(default_factory=list, max_length=100)
    options: list[CandidateOptionInput] = Field(default_factory=list, max_length=10)
    concepts: list[CandidateConceptInput] = Field(default_factory=list, max_length=30)
    problem_types: list[CandidateProblemTypeInput] = Field(default_factory=list, max_length=30)
    learning_outcomes: list[CandidateLearningOutcomeInput] = Field(default_factory=list, max_length=30)


class CandidateCreate(CandidateSemanticInput):
    source_id: UUID
    group_structure_required: bool = False


class CandidatePatch(StrictInput):
    expected_revision: int = Field(ge=1)
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    question_type: QuestionType | None = None
    difficulty: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    correct_answer: str | None = Field(default=None, min_length=1, max_length=10000)
    explanation: str | None = Field(default=None, min_length=1, max_length=20000)
    cognitive_level: CognitiveLevel | None = None
    exam_weight: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    source_year: int | None = Field(default=None, ge=1900, le=2100)
    visual_required: bool | None = None
    rights_decision: QuestionValidationRightsDecision | None = None
    spans: list[CandidateSpanInput] | None = Field(default=None, max_length=100)
    options: list[CandidateOptionInput] | None = Field(default=None, max_length=10)
    concepts: list[CandidateConceptInput] | None = Field(default=None, max_length=30)
    problem_types: list[CandidateProblemTypeInput] | None = Field(default=None, max_length=30)
    learning_outcomes: list[CandidateLearningOutcomeInput] | None = Field(default=None, max_length=30)
    group_structure_required: bool | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self) -> "CandidatePatch":
        required = {"content", "question_type", "visual_required", "rights_decision"}
        if any(field in self.model_fields_set and getattr(self, field) is None for field in required):
            raise ValueError("Required candidate fields cannot be null")
        return self


class ManualReviewInput(StrictInput):
    check_type: QuestionValidationCheckType
    result: QuestionValidationCheckResult
    note: str = Field(min_length=1, max_length=10000)


class CandidateRejectInput(StrictInput):
    reason: str = Field(min_length=1, max_length=10000)


class CandidateSpanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    page_id: UUID
    order_index: int
    start_char: int
    end_char: int
    excerpt: str
    excerpt_sha256: str


class CandidateOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    label: str
    content: str
    order_index: int


class CandidateConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    concept_id: UUID
    weight: float


class CandidateProblemTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    problem_type_id: UUID
    weight: float | None
    is_primary: bool


class CandidateLearningOutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    learning_outcome_id: UUID
    weight: float | None


class ValidationCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    candidate_revision: int
    check_type: QuestionValidationCheckType
    result: QuestionValidationCheckResult
    checked_by: UUID | None
    note: str | None
    details_json: dict[str, object]
    checked_at: datetime


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    batch_id: UUID
    source_id: UUID
    revision: int
    status: QuestionValidationCandidateStatus
    subject_id: UUID
    content: str
    question_type: QuestionType
    difficulty: float | None
    correct_answer: str | None
    explanation: str | None
    cognitive_level: CognitiveLevel | None
    exam_weight: float | None
    source_year: int | None
    visual_required: bool
    rights_decision: QuestionValidationRightsDecision
    content_hash: str
    promoted_question_id: UUID | None
    promoted_revision: int | None
    promoted_by: UUID | None
    promoted_at: datetime | None
    rejection_reason: str | None
    created_by: UUID | None
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime
    spans: list[CandidateSpanRead]
    options: list[CandidateOptionRead]
    concepts: list[CandidateConceptRead] = Field(validation_alias="concept_links")
    problem_types: list[CandidateProblemTypeRead] = Field(validation_alias="problem_type_links")
    learning_outcomes: list[CandidateLearningOutcomeRead] = Field(
        validation_alias="learning_outcome_links"
    )
    checks: list[ValidationCheckRead]


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    acquisition_request_id: UUID
    attempt_index: int
    status: QuestionValidationBatchStatus
    target_candidate_count_snapshot: int
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None


class BatchDetailRead(BatchRead):
    candidates: list[CandidateRead]


class PromotionRead(BaseModel):
    candidate: CandidateRead
    question_id: UUID
    question_status: str
