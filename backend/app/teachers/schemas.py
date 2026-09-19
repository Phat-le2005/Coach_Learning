from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TeacherProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    specialization: str | None
    created_at: datetime
    updated_at: datetime


class TeacherProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    specialization: str | None = Field(default=None, max_length=200)

    @field_validator("specialization")
    @classmethod
    def normalize_specialization(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("specialization must be nonblank or null")
        return normalized
