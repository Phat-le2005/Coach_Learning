from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.planning.study_explanation_schemas import StudyPlanExplanationRead
from app.planning.study_models import (
    StudyPlanStatus,
    StudyTaskReasonCode,
    StudyTaskStatus,
    StudyTaskType,
)


class StudyTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_plan_id: UUID
    task_type: StudyTaskType
    status: StudyTaskStatus
    planned_date: date
    problem_type_id: UUID | None = None
    problem_type_name: str | None = None
    concept_id: UUID | None = None
    concept_name: str | None = None
    topic_id: UUID | None = None
    topic_name: str | None = None
    chapter_id: UUID | None = None
    chapter_name: str | None = None
    subject_id: UUID | None = None
    subject_name: str | None = None
    estimated_duration_minutes: int = Field(gt=0)
    priority: int = Field(gt=0)
    order_index: int = Field(ge=0)
    reason_code: str
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StudyDayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    available_daily_minutes: int
    total_estimated_minutes: int
    tasks: list[StudyTaskRead]
    completed_count: int
    total_count: int
    days_to_exam: int | None = None
    notice: str | None = None
    explanation: StudyPlanExplanationRead | None = None


class StudyPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    academic_goal_id: UUID | None = None
    start_date: date
    target_date: date | None = None
    status: StudyPlanStatus
    days_to_exam: int | None = None
    available_daily_minutes: int
    total_tasks: int
    completed_tasks: int
    tasks: list[StudyTaskRead]
    created_at: datetime
    updated_at: datetime


class StudyPlanRecalculateRequest(BaseModel):
    horizon_days: int = Field(default=7, ge=1, le=30)
    as_of: date | None = None
