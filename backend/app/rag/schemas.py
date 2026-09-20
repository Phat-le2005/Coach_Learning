from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.rag.models import DocumentSourceType, DocumentStatus


class AcademicMetadata(BaseModel):
    chapter_ids: list[UUID] = Field(default_factory=list)
    topic_ids: list[UUID] = Field(default_factory=list)
    problem_type_ids: list[UUID] = Field(default_factory=list)
    concept_ids: list[UUID] = Field(default_factory=list)
    learning_outcome_ids: list[UUID] = Field(default_factory=list)
    grade_level: int | None = None


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    subject_id: UUID | None = None
    source_type: DocumentSourceType | str = DocumentSourceType.TEXTBOOK
    source_reference: str | None = None
    status: DocumentStatus | str = DocumentStatus.PUBLISHED
    academic_metadata: AcademicMetadata | None = None


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    subject_id: UUID | None = None
    source_type: str
    source_reference: str | None = None
    status: str
    created_by: UUID | None = None
    created_at: datetime
    chunk_count: int = 0


class AcademicMetadataFilter(BaseModel):
    subject_id: UUID | None = None
    chapter_ids: list[UUID] | None = None
    topic_ids: list[UUID] | None = None
    problem_type_ids: list[UUID] | None = None
    concept_ids: list[UUID] | None = None
    learning_outcome_ids: list[UUID] | None = None


class SearchResultItem(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    content: str
    similarity_score: float
    chunk_index: int
    metadata: dict[str, Any] = Field(default_factory=dict)
