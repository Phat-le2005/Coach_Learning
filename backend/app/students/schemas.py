from datetime import UTC, date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.students.models import SyntheticProfile


class StudentProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    grade_level: int
    school_name: str | None
    date_of_birth: date | None
    is_synthetic: bool
    synthetic_profile: SyntheticProfile | None
    created_at: datetime
    updated_at: datetime


class StudentProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    grade_level: int | None = Field(default=None, ge=1, le=12, strict=True)
    school_name: str | None = Field(default=None, max_length=200)
    date_of_birth: date | None = None

    @field_validator("grade_level")
    @classmethod
    def grade_cannot_be_null(cls, value: int | None) -> int:
        if value is None:
            raise ValueError("grade_level cannot be null")
        return value

    @field_validator("school_name")
    @classmethod
    def normalize_school_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("school_name must be nonblank or null")
        return normalized

    @field_validator("date_of_birth")
    @classmethod
    def birth_date_cannot_be_future(cls, value: date | None) -> date | None:
        if value is not None and value > datetime.now(UTC).date():
            raise ValueError("date_of_birth cannot be in the future")
        return value
