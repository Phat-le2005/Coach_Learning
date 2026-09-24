from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.questions.models import (
    CognitiveLevel,
    QuestionGroupScoringPolicy,
    QuestionGroupType,
    QuestionStatus,
    QuestionType,
)


class QuestionGroupItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_id: UUID
    label: Literal["a", "b", "c", "d"]
    order_index: int = Field(ge=0, le=3, strict=True)


class QuestionGroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject_id: UUID
    content: str = Field(min_length=1, max_length=20000)
    group_type: QuestionGroupType = QuestionGroupType.TRUE_FALSE_FOUR
    scoring_policy: QuestionGroupScoringPolicy = (
        QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE
    )
    difficulty: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    source_type: str = Field(min_length=1, max_length=50)
    source_reference: str | None = Field(default=None, min_length=1, max_length=500)
    source_year: int | None = Field(default=None, ge=1900, le=2100, strict=True)
    cognitive_level: CognitiveLevel | None = None
    exam_weight: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    items: list[QuestionGroupItemInput] = Field(min_length=4, max_length=4)

    @field_validator("source_type")
    @classmethod
    def normalize_source_type(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_items(self) -> "QuestionGroupCreate":
        if {item.label for item in self.items} != {"a", "b", "c", "d"}:
            raise ValueError("Question group labels must be exactly a, b, c, d")
        if {item.order_index for item in self.items} != {0, 1, 2, 3}:
            raise ValueError("Question group order indexes must be exactly 0, 1, 2, 3")
        if len({item.question_id for item in self.items}) != 4:
            raise ValueError("Question group child question IDs must be unique")
        return self


class QuestionGroupChildInternalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_id: UUID
    content: str
    question_type: QuestionType
    correct_answer: str | None
    status: QuestionStatus


class QuestionGroupItemInternalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    group_id: UUID
    question_id: UUID
    label: str
    order_index: int
    question: QuestionGroupChildInternalRead


class QuestionGroupInternalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_id: UUID
    content: str
    group_type: QuestionGroupType
    scoring_policy: QuestionGroupScoringPolicy
    difficulty: float
    source_type: str
    source_reference: str | None
    source_year: int | None
    cognitive_level: CognitiveLevel | None
    exam_weight: float
    status: QuestionStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    items: list[QuestionGroupItemInternalRead]
