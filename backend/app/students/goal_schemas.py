from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.students.goal_models import AcademicGoalStatus


class SubjectGoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    subject_id: UUID
    current_score: float | None = None
    target_score: float
    priority: int | None = Field(default=None, ge=1)


class SubjectGoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    academic_goal_id: UUID
    subject_id: UUID
    current_score: float | None
    target_score: float
    priority: int | None
    created_at: datetime
    updated_at: datetime


class AcademicGoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    target_exam: str = Field(min_length=1, max_length=100)
    exam_date: date
    available_daily_minutes: int = Field(gt=0, le=1440)
    status: AcademicGoalStatus = AcademicGoalStatus.ACTIVE
    target_university: str | None = Field(default=None, max_length=200)
    target_major: str | None = Field(default=None, max_length=200)
    subject_goals: list[SubjectGoalCreate] = Field(default_factory=list)

    @field_validator("target_exam")
    @classmethod
    def normalize_target_exam(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("target_exam must be nonblank")
        return normalized

    @field_validator("target_university")
    @classmethod
    def normalize_target_university(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None

    @field_validator("target_major")
    @classmethod
    def normalize_target_major(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


class AcademicGoalPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    target_exam: str | None = Field(default=None, min_length=1, max_length=100)
    exam_date: date | None = None
    available_daily_minutes: int | None = Field(default=None, gt=0, le=1440)
    status: AcademicGoalStatus | None = None
    target_university: str | None = Field(default=None, max_length=200)
    target_major: str | None = Field(default=None, max_length=200)
    subject_goals: list[SubjectGoalCreate] | None = None

    @field_validator("target_exam")
    @classmethod
    def normalize_target_exam(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("target_exam must be nonblank")
        return normalized

    @field_validator("target_university")
    @classmethod
    def normalize_target_university(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None

    @field_validator("target_major")
    @classmethod
    def normalize_target_major(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized else None


class AcademicGoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    target_exam: str
    exam_date: date
    available_daily_minutes: int
    status: AcademicGoalStatus
    target_university: str | None
    target_major: str | None
    subject_goals: list[SubjectGoalRead]
    created_at: datetime
    updated_at: datetime
