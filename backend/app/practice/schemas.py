from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.practice.evaluation import AnswerEvaluationService
from app.practice.models import EvaluationStatus, PracticeSessionStatus, PracticeSessionType
from app.questions.models import (
    CognitiveLevel,
    QuestionGroupScoringPolicy,
    QuestionGroupType,
    QuestionType,
)
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


class PracticeQuestionGroupItemRead(BaseModel):
    label: str
    order_index: int
    question_id: UUID
    content: str


class PracticeQuestionGroupRead(BaseModel):
    id: UUID
    subject_id: UUID
    content: str
    group_type: QuestionGroupType
    scoring_policy: QuestionGroupScoringPolicy
    difficulty: float
    exam_weight: float
    cognitive_level: CognitiveLevel | None
    items: list[PracticeQuestionGroupItemRead]


class PracticeItemRead(BaseModel):
    item_type: Literal["QUESTION", "QUESTION_GROUP"]
    question: PracticeQuestionRead | None = None
    question_group: PracticeQuestionGroupRead | None = None


class PracticeGroupAnswerItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True
    )

    label: str = Field(min_length=1, max_length=1)
    student_answer: str = Field(min_length=1, max_length=20)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        return value.strip().casefold()

    @field_validator("student_answer")
    @classmethod
    def normalize_true_false_answer(cls, value: str) -> str:
        normalized = AnswerEvaluationService.normalize(value)
        if normalized not in {"true", "false"}:
            raise ValueError("Student answer must be TRUE or FALSE")
        return normalized.upper()


class PracticeGroupAnswerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    question_group_id: UUID
    answers: list[PracticeGroupAnswerItem] = Field(min_length=4, max_length=4)
    response_time_seconds: float | None = Field(
        default=None, gt=0.0, le=86400.0, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def require_exact_group_shape(self) -> "PracticeGroupAnswerCreate":
        labels = [item.label for item in self.answers]
        if len(labels) != 4 or set(labels) != {"a", "b", "c", "d"}:
            raise ValueError("Answers must contain each label a, b, c and d exactly once")
        return self


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


class QuestionGroupAttemptItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_group_item_id: UUID
    question_attempt_id: UUID
    label: str
    order_index: int
    question_attempt: QuestionAttemptRead


class QuestionGroupAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    practice_session_id: UUID
    student_id: UUID
    question_group_id: UUID
    correct_count: int
    score: float
    response_time_seconds: float | None
    scoring_policy: QuestionGroupScoringPolicy
    created_at: datetime
    attempt_items: list[QuestionGroupAttemptItemRead]


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
