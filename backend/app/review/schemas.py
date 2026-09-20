from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.review.models import ReviewResult


class ReviewScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    problem_type_id: UUID | None = None
    concept_id: UUID | None = None
    next_review_at: datetime
    review_interval_days: float
    review_count: int
    last_review_result: str | None = None
    created_at: datetime
    updated_at: datetime


class ReviewScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: UUID
    problem_type_id: UUID | None = None
    concept_id: UUID | None = None
    initial_interval_days: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def check_exactly_one_target(self) -> "ReviewScheduleCreate":
        has_pt = self.problem_type_id is not None
        has_concept = self.concept_id is not None
        if has_pt == has_concept:
            raise ValueError("Exactly one of problem_type_id or concept_id must be provided.")
        return self


class ReviewPerformanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_problem_type_id: UUID | None = None
    target_concept_id: UUID | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    is_correct: bool | None = None

    @model_validator(mode="after")
    def check_target_and_outcome(self) -> "ReviewPerformanceRecord":
        has_pt = self.target_problem_type_id is not None
        has_concept = self.target_concept_id is not None
        if has_pt == has_concept:
            raise ValueError(
                "Exactly one of target_problem_type_id or target_concept_id must be provided."
            )
        if self.score is None and self.is_correct is None:
            raise ValueError("At least one of score or is_correct must be provided.")
        return self


class ReviewDueItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schedule_id: UUID
    student_id: UUID
    problem_type_id: UUID | None = None
    concept_id: UUID | None = None
    next_review_at: datetime
    review_interval_days: float
    review_count: int
    last_review_result: str | None = None
    is_overdue: bool = True
