import json
from datetime import datetime
from math import fsum
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.questions.models import (
    CognitiveLevel,
    ImportBatchStatus,
    ImportFileFormat,
    ImportRowStatus,
    QuestionType,
)


class ImportOptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)

    label: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=1, max_length=10000)
    order_index: int = Field(ge=0, le=2147483647)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        return value.upper()


class ImportConceptInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)

    code: str = Field(min_length=1, max_length=100)
    weight: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class ImportProblemTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    code: str = Field(min_length=1, max_length=100)
    weight: float | None = Field(default=None, gt=0.0, le=1.0, allow_inf_nan=False)
    is_primary: bool = False

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class ImportLearningOutcomeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    code: str = Field(min_length=1, max_length=100)
    weight: float | None = Field(default=None, gt=0.0, le=1.0, allow_inf_nan=False)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class QuestionImportRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        hide_input_in_errors=True,
        populate_by_name=True,
    )

    subject_code: str = Field(min_length=1, max_length=100)
    curriculum_version_code: str | None = Field(default=None, min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=20000)
    question_type: QuestionType
    difficulty: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    correct_answer: str | None = Field(default=None, min_length=1, max_length=10000)
    explanation: str | None = Field(default=None, min_length=1, max_length=20000)
    source: str = Field(
        min_length=1,
        max_length=50,
        validation_alias=AliasChoices("source", "source_type"),
    )
    source_reference: str | None = Field(default=None, min_length=1, max_length=500)
    source_year: int | None = Field(default=None, ge=1900, le=2100)
    cognitive_level: CognitiveLevel | None = None
    exam_weight: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    options: list[ImportOptionInput] = Field(default_factory=list, max_length=10)
    concepts: list[ImportConceptInput] = Field(min_length=1)
    problem_types: list[ImportProblemTypeInput] = Field(default_factory=list)
    learning_outcomes: list[ImportLearningOutcomeInput] = Field(default_factory=list)

    @field_validator(
        "options", "concepts", "problem_types", "learning_outcomes", mode="before"
    )
    @classmethod
    def parse_nested_json(cls, value: Any) -> Any:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as error:
                raise ValueError(f"must contain valid JSON: {error.msg}") from error
        return value

    @field_validator(
        "correct_answer", "explanation", "source_reference", mode="before"
    )
    @classmethod
    def blank_optional_to_none(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("subject_code", "curriculum_version_code", "source")
    @classmethod
    def normalize_uppercase(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def validate_question(self) -> "QuestionImportRecord":
        if self.question_type == QuestionType.MULTIPLE_CHOICE:
            if not 2 <= len(self.options) <= 10:
                raise ValueError("MULTIPLE_CHOICE requires 2 to 10 options")
        elif self.options:
            raise ValueError("Only MULTIPLE_CHOICE accepts options")
        if len({option.label for option in self.options}) != len(self.options):
            raise ValueError("Option labels must be unique")
        if len({option.order_index for option in self.options}) != len(self.options):
            raise ValueError("Option order indexes must be unique")
        if len({concept.code for concept in self.concepts}) != len(self.concepts):
            raise ValueError("Concept codes must be unique")
        if fsum(concept.weight for concept in self.concepts) > 1.000001:
            raise ValueError("Concept weights cannot total more than 1")
        if len({item.code for item in self.problem_types}) != len(self.problem_types):
            raise ValueError("Problem type codes must be unique")
        if sum(item.is_primary for item in self.problem_types) > 1:
            raise ValueError("Only one problem type can be primary")
        if len({item.code for item in self.learning_outcomes}) != len(
            self.learning_outcomes
        ):
            raise ValueError("Learning outcome codes must be unique")

        answer = self.correct_answer.upper() if self.correct_answer is not None else None
        if self.question_type == QuestionType.MULTIPLE_CHOICE:
            if answer is None or answer not in {option.label for option in self.options}:
                raise ValueError("MULTIPLE_CHOICE correct_answer must match an option label")
            self.correct_answer = answer
        elif self.question_type == QuestionType.TRUE_FALSE:
            if answer not in {"TRUE", "FALSE"}:
                raise ValueError("TRUE_FALSE correct_answer must be TRUE or FALSE")
            self.correct_answer = answer
        elif self.question_type == QuestionType.SHORT_ANSWER and answer is None:
            raise ValueError("SHORT_ANSWER requires correct_answer")
        return self


class QuestionImportReport(BaseModel):
    total: int
    valid: int
    invalid: int
    duplicate: int
    imported: int


class QuestionImportRowRead(BaseModel):
    row_number: int
    status: ImportRowStatus
    errors: list[str]
    data: dict[str, object] | None
    imported_question_id: UUID | None


class QuestionImportBatchRead(BaseModel):
    batch_id: UUID
    file_name: str
    file_format: ImportFileFormat
    trusted_seed_data: bool
    status: ImportBatchStatus
    created_at: datetime
    confirmed_at: datetime | None
    report: QuestionImportReport
    rows: list[QuestionImportRowRead]
