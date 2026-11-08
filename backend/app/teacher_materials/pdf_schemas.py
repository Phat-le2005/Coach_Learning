from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from app.teacher_materials.difficulty import MaterialDifficultyLevel
from app.teacher_materials.visual_schemas import QuestionVisualRead


class PdfReviewDecision(BaseModel):
    question_id: str = Field(min_length=1, max_length=200)
    accepted: bool = False
    source_checked: bool = False
    content: str = Field(max_length=200_000)
    answer: str = Field(default="", max_length=100_000)
    explanation: str = Field(default="", max_length=200_000)
    difficulty_level: MaterialDifficultyLevel | None = None


class PdfReviewSubmit(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    decisions: list[PdfReviewDecision] = Field(max_length=10_000)


class PdfImportQuestion(BaseModel):
    question_id: str
    number: int
    source_number: int | None = None
    content: str
    answer: str
    explanation: str
    difficulty_level: MaterialDifficultyLevel | None = None
    pages: list[int]
    warnings: list[str]
    suggested: bool
    source_assets: list[int]
    visual_assets: list[int]
    visuals: list[QuestionVisualRead] = Field(default_factory=list)


class PdfImportRead(BaseModel):
    id: UUID
    classroom_id: UUID
    subject_id: UUID
    title: str
    original_file_name: str
    source_kind: Literal["PDF", "IMAGE"] = "PDF"
    source_mime_type: Literal["application/pdf", "image/png", "image/jpeg"] = "application/pdf"
    status: Literal["QUEUED", "PROCESSING", "NEEDS_REVIEW", "FAILED", "SUBMITTED"]
    created_at: datetime
    error: str | None = None
    material_id: UUID | None = None
    revision_of: UUID | None = None
    progress: dict = Field(default_factory=dict)
    questions: list[PdfImportQuestion] = Field(default_factory=list)
    review: PdfReviewSubmit | None = None
