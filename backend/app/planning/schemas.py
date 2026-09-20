from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.planning.models import TeachingPlanStatus


class TeachingPlanItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_type_id: UUID
    learning_outcome_id: UUID | None = None
    priority: int = Field(default=1, gt=0)
    order_index: int | None = Field(default=None, ge=0)


class TeachingPlanItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    teaching_plan_id: UUID
    problem_type_id: UUID
    learning_outcome_id: UUID | None = None
    priority: int
    order_index: int | None = None
    derived_concept_ids: list[UUID] = Field(default_factory=list)


class TeachingPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: UUID
    start_date: date
    target_end_date: date | None = None
    status: TeachingPlanStatus = TeachingPlanStatus.PLANNED
    items: list[TeachingPlanItemCreate] = Field(default_factory=list)


class TeachingPlanPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date | None = None
    target_end_date: date | None = None
    status: TeachingPlanStatus | None = None
    items: list[TeachingPlanItemCreate] | None = None


class TeachingPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    classroom_id: UUID
    subject_id: UUID
    start_date: date
    target_end_date: date | None = None
    status: TeachingPlanStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: list[TeachingPlanItemRead] = Field(default_factory=list)
