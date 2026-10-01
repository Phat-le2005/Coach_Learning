from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.questions.models import QuestionType
from app.teacher_materials.models import MaterialEvaluationMode, MaterialItemExtractionStatus, MaterialMappingSource, MaterialMappingStatus, TeacherMaterialStatus

class MaterialOptionInput(BaseModel):
    label: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=1)
    order_index: int = Field(ge=0)

class MaterialOptionRead(MaterialOptionInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID

class TeacherMaterialItemUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    question_type: QuestionType | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    difficulty: float | None = Field(default=None, ge=0, le=1)
    evaluation_mode: MaterialEvaluationMode | None = None
    options: list[MaterialOptionInput] | None = None
    content_reviewed: bool | None = None
    archive: bool = False

class MappingCreate(BaseModel):
    target_id: UUID
    weight: float = Field(default=1, gt=0, le=1)
    confidence: float = Field(default=1, ge=0, le=1)
    is_primary: bool = False
    rationale: str | None = None

class MappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    weight: float
    confidence: float
    is_primary: bool
    source: MaterialMappingSource
    status: MaterialMappingStatus
    rationale: str | None

class TeacherMaterialItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    teacher_material_id: UUID
    order_index: int
    page_start: int | None
    page_end: int | None
    content: str
    content_hash: str
    question_type: QuestionType | None
    correct_answer: str | None
    explanation: str | None
    difficulty: float | None
    extraction_status: MaterialItemExtractionStatus
    evaluation_mode: MaterialEvaluationMode
    raw_metadata: dict
    options: list[MaterialOptionRead] = Field(default_factory=list)

class TeacherMaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    classroom_id: UUID
    subject_id: UUID
    teaching_plan_id: UUID | None
    uploaded_by: UUID
    title: str
    original_file_name: str
    mime_type: str
    sha256: str
    file_size_bytes: int
    page_count: int | None
    status: TeacherMaterialStatus
    parse_error: str | None
    created_at: datetime
    updated_at: datetime
