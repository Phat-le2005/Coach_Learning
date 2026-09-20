from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.hints.models import HintLevel, HintSource


class HintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    practice_session_id: UUID
    current_hint_level: HintLevel


class HintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    practice_session_id: UUID
    question_id: UUID
    hint_level: HintLevel
    hint_count: int
    hint_source: HintSource
    content: str
    created_at: datetime


class AIHintOutput(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True
    )

    content: str = Field(min_length=1, max_length=4000)
    referenced_concept_codes: list[str] = Field(default_factory=list, max_length=20)
    referenced_problem_type_codes: list[str] = Field(
        default_factory=list, max_length=20
    )
    referenced_learning_outcome_codes: list[str] = Field(
        default_factory=list, max_length=20
    )
    reveals_final_answer: bool = False

    @field_validator(
        "referenced_concept_codes",
        "referenced_problem_type_codes",
        "referenced_learning_outcome_codes",
    )
    @classmethod
    def normalize_codes(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().upper() for item in value]
        if any(not item for item in normalized):
            raise ValueError("Referenced concept codes cannot be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Referenced concept codes must be unique")
        return normalized
