from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.curriculum.constants import LEGACY_CURRICULUM_VERSION_ID


class AcademicInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)

    @field_validator("code", mode="before", check_fields=False)
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class SubjectCreate(AcademicInput):
    curriculum_version_id: UUID = LEGACY_CURRICULUM_VERSION_ID
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    grade_level: int | None = Field(default=None, ge=1, le=12, strict=True)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    order_index: int | None = Field(default=None, ge=0, le=2147483647, strict=True)


class SubjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    curriculum_version_id: UUID
    code: str
    name: str
    grade_level: int | None
    description: str | None
    order_index: int | None
