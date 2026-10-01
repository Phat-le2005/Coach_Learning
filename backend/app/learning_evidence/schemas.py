from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.learning_evidence.models import LearningEvidenceSourceKind
from app.practice.models import EvaluationStatus

class LearningEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    student_id: UUID
    subject_id: UUID
    classroom_id: UUID | None
    teaching_plan_id: UUID | None
    assignment_id: UUID | None
    source_kind: LearningEvidenceSourceKind
    source_entity_id: UUID
    is_correct: bool | None
    score: float | None
    difficulty: float | None
    response_time_seconds: float | None
    hint_count: int
    evaluation_status: EvaluationStatus
    occurred_at: datetime
