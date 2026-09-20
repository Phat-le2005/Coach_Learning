from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.practice.models import EvaluationStatus, PracticeSessionStatus, PracticeSessionType
from app.questions.models import CognitiveLevel, QuestionType
from app.questions.schemas import QuestionOptionRead


class PracticeSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    subject_id: UUID
    session_type: PracticeSessionType
    problem_type_ids: list[UUID] = Field(default_factory=list, max_length=100)
    concept_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("problem_type_ids", "concept_ids")
    @classmethod
    def require_unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Scope identifiers must be unique")
        return value


class PracticeAnswerCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True
    )

    question_id: UUID
    student_answer: str = Field(min_length=1, max_length=20000)
    response_time_seconds: float | None = Field(
        default=None, gt=0.0, le=86400.0, allow_inf_nan=False
    )
    hint_count: int = Field(default=0, ge=0, le=100, strict=True)


class PracticeQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_id: UUID
    content: str
    question_type: QuestionType
    difficulty: float
    exam_weight: float
    cognitive_level: CognitiveLevel | None
    options: list[QuestionOptionRead]


class QuestionAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    practice_session_id: UUID
    student_id: UUID
    question_id: UUID
    student_answer: str
    is_correct: bool | None
    score: float | None
    response_time_seconds: float | None
    hint_count: int
    attempt_number: int
    evaluation_status: EvaluationStatus
    evaluation_details: dict[str, Any] | None = None
    created_at: datetime


class PracticeSessionRead(BaseModel):
    id: UUID
    student_id: UUID
    subject_id: UUID
    session_type: PracticeSessionType
    started_at: datetime
    completed_at: datetime | None
    status: PracticeSessionStatus
    created_at: datetime
    problem_type_ids: list[UUID]
    concept_ids: list[UUID]
    attempts: list[QuestionAttemptRead]

