from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.concepts.models import RelationType
from app.subjects.schemas import AcademicInput


class ConceptCreate(AcademicInput):
    subject_id: UUID
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    grade_level: int | None = Field(default=None, ge=1, le=12, strict=True)
    order_index: int | None = Field(default=None, ge=0, le=2147483647, strict=True)


class ConceptPatch(AcademicInput):
    subject_id: UUID | None = None
    code: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    grade_level: int | None = Field(default=None, ge=1, le=12, strict=True)
    order_index: int | None = Field(default=None, ge=0, le=2147483647, strict=True)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "ConceptPatch":
        if any(
            getattr(self, field) is None
            for field in self.model_fields_set - {"description", "grade_level", "order_index"}
        ):
            raise ValueError("Concept fields cannot be null")
        return self


class ConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_id: UUID
    code: str
    name: str
    description: str | None
    grade_level: int | None
    order_index: int | None


class ConceptRelationCreate(AcademicInput):
    source_concept_id: UUID
    target_concept_id: UUID
    relation_type: RelationType


class ConceptRelationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_concept_id: UUID
    target_concept_id: UUID
    relation_type: RelationType


class PrerequisiteTree(BaseModel):
    """Normalized tree/DAG: shared prerequisites appear once, all edges are retained."""

    root_concept_id: UUID
    concepts: list[ConceptRead]
    relations: list[ConceptRelationRead]
