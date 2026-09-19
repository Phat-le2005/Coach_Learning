from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.concepts.models import RelationType


class ImportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)

    @field_validator("code", mode="before", check_fields=False)
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class DatasetManifest(ImportRecord):
    dataset_code: str = Field(min_length=1, max_length=150)
    dataset_version: str = Field(min_length=1, max_length=100)
    curriculum_code: str = Field(min_length=1, max_length=100)
    curriculum_name: str = Field(min_length=1, max_length=200)
    curriculum_description: str | None = None
    curriculum_version_code: str = Field(min_length=1, max_length=100)
    curriculum_version: str = Field(min_length=1, max_length=100)
    subject_code: str = Field(min_length=1, max_length=100)
    grade_level: int = Field(ge=1, le=12)
    source_name: str = Field(min_length=1, max_length=500)
    source_reference: str | None = None
    verified_at: datetime | None = None
    legacy_identity_compatible: bool = False

    @field_validator(
        "dataset_code",
        "curriculum_code",
        "curriculum_version_code",
        "subject_code",
        mode="before",
    )
    @classmethod
    def normalize_manifest_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class SubjectRecord(ImportRecord):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    grade_level: int = Field(ge=1, le=12)
    description: str | None = None
    order_index: int | None = Field(default=None, ge=0)


class ChapterRecord(ImportRecord):
    code: str
    name: str
    description: str | None = None
    order_index: int = Field(ge=0)


class TopicRecord(ImportRecord):
    chapter_code: str
    code: str
    name: str
    description: str | None = None
    order_index: int = Field(ge=0)

    @field_validator("chapter_code", mode="before")
    @classmethod
    def normalize_parent(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class ProblemTypeRecord(ImportRecord):
    topic_code: str
    code: str
    name: str
    description: str | None = None
    order_index: int = Field(ge=0)
    default_difficulty: float | None = Field(default=None, ge=0.0, le=1.0)
    is_active: bool = True

    @field_validator("topic_code", mode="before")
    @classmethod
    def normalize_parent(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class ConceptRecord(ImportRecord):
    code: str
    name: str
    description: str | None = None
    grade_level: int | None = Field(default=None, ge=1, le=12)
    order_index: int | None = Field(default=None, ge=0)


class LearningOutcomeRecord(ImportRecord):
    code: str
    description: str
    grade_level: int = Field(ge=1, le=12)
    order_index: int | None = Field(default=None, ge=0)
    source_reference: str | None = None


class ConceptRelationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_code: str
    target_code: str
    relation_type: RelationType

    @field_validator("source_code", "target_code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class ProblemTypeConceptRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    problem_type_code: str
    concept_code: str
    weight: float = Field(gt=0.0, le=1.0)
    is_primary: bool = False

    @field_validator("problem_type_code", "concept_code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class ProblemTypeOutcomeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    problem_type_code: str
    learning_outcome_code: str
    weight: float | None = Field(default=None, gt=0.0, le=1.0)

    @field_validator("problem_type_code", "learning_outcome_code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class CurriculumImportPreview(BaseModel):
    dataset_code: str
    dataset_version: str
    content_hash: str
    source_name: str
    source_reference: str | None
    verified_at: datetime | None
    counts: dict[str, int]
    already_imported: bool


class CurriculumImportResult(CurriculumImportPreview):
    created: dict[str, int]
    updated: dict[str, int]
    unchanged: dict[str, int]
