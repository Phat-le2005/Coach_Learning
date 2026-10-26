"""Internal teacher grading of assigned canonical open-response questions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.assignments.models import StudentAssignmentStatus


class CanonicalQuestionGradeRequest(BaseModel):
    score: float = Field(ge=0, le=1)
    is_correct: bool
    feedback: str | None = Field(default=None, max_length=4000)


class CanonicalQuestionGradeRead(BaseModel):
    item_id: UUID
    question_id: UUID
    score: float
    is_correct: bool
    feedback: str | None
    graded_by: UUID
    graded_at: datetime
    assignment_score: float | None
    assignment_status: StudentAssignmentStatus