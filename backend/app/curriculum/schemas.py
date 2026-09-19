from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CurriculumInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)

    @field_validator("code", mode="before", check_fields=False)
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class CurriculumCreate(CurriculumInput):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)


class CurriculumRead(CurriculumCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class CurriculumVersionCreate(CurriculumInput):
    curriculum_id: UUID
    code: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    effective_from: date | None = None
    effective_to: date | None = None
    source_reference: str | None = Field(default=None, min_length=1, max_length=1000)
    verified_at: datetime | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_effective_range(self) -> "CurriculumVersionCreate":
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to cannot be before effective_from")
        return self


class CurriculumVersionRead(CurriculumVersionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class ChapterCreate(CurriculumInput):
    subject_id: UUID
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    order_index: int = Field(ge=0, le=2147483647, strict=True)


class ChapterRead(ChapterCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class TopicCreate(CurriculumInput):
    chapter_id: UUID
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    order_index: int = Field(ge=0, le=2147483647, strict=True)


class TopicRead(TopicCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class ProblemTypeCreate(CurriculumInput):
    topic_id: UUID
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    order_index: int = Field(ge=0, le=2147483647, strict=True)
    default_difficulty: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    is_active: bool = True


class ProblemTypeRead(ProblemTypeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class LearningOutcomeCreate(CurriculumInput):
    subject_id: UUID
    code: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=10000)
    grade_level: int = Field(ge=1, le=12, strict=True)
    order_index: int | None = Field(default=None, ge=0, le=2147483647, strict=True)
    source_reference: str | None = Field(default=None, min_length=1, max_length=1000)


class LearningOutcomeRead(LearningOutcomeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class ProblemTypeConceptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    problem_type_id: UUID
    concept_id: UUID
    weight: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    is_primary: bool = False


class ProblemTypeConceptRead(ProblemTypeConceptCreate):
    model_config = ConfigDict(from_attributes=True)


class ProblemTypeLearningOutcomeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    problem_type_id: UUID
    learning_outcome_id: UUID
    weight: float | None = Field(default=None, gt=0.0, le=1.0, allow_inf_nan=False)


class ProblemTypeLearningOutcomeRead(ProblemTypeLearningOutcomeCreate):
    model_config = ConfigDict(from_attributes=True)


class ProblemTypeTreeNode(BaseModel):
    id: UUID
    code: str
    name: str
    order_index: int
    is_active: bool
    concept_count: int
    learning_outcome_count: int


class TopicTreeNode(BaseModel):
    id: UUID
    code: str
    name: str
    order_index: int
    problem_types: list[ProblemTypeTreeNode]


class ChapterTreeNode(BaseModel):
    id: UUID
    code: str
    name: str
    order_index: int
    topics: list[TopicTreeNode]


class SubjectTree(BaseModel):
    id: UUID
    curriculum_version_id: UUID
    code: str
    name: str
    grade_level: int | None
    chapters: list[ChapterTreeNode]


class ProblemTypeDetail(ProblemTypeRead):
    concepts: list[ProblemTypeConceptRead]
    learning_outcomes: list[ProblemTypeLearningOutcomeRead]
