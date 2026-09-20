from datetime import datetime
from math import fsum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.hints.models import HintLevel
from app.questions.models import CognitiveLevel, QuestionStatus, QuestionType


class QuestionHintInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True
    )

    hint_level: HintLevel
    content: str = Field(min_length=1, max_length=4000)


class QuestionOptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    label: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=1, max_length=10000)
    order_index: int = Field(ge=0, le=2147483647, strict=True)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        return value.upper()


class QuestionConceptInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    concept_id: UUID
    weight: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)


class QuestionProblemTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    problem_type_id: UUID
    weight: float | None = Field(default=None, gt=0.0, le=1.0, allow_inf_nan=False)
    is_primary: bool = False


class QuestionLearningOutcomeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    learning_outcome_id: UUID
    weight: float | None = Field(default=None, gt=0.0, le=1.0, allow_inf_nan=False)


class QuestionWriteBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)

    @staticmethod
    def validate_collections(
        question_type: QuestionType,
        options: list[QuestionOptionInput],
        concepts: list[QuestionConceptInput],
        problem_types: list[QuestionProblemTypeInput] | None = None,
        learning_outcomes: list[QuestionLearningOutcomeInput] | None = None,
        hints: list[QuestionHintInput] | None = None,
    ) -> None:
        problem_types = problem_types or []
        learning_outcomes = learning_outcomes or []
        hints = hints or []
        if question_type == QuestionType.MULTIPLE_CHOICE:
            if not 2 <= len(options) <= 10:
                raise ValueError("MULTIPLE_CHOICE requires 2 to 10 options")
        elif options:
            raise ValueError("Only MULTIPLE_CHOICE accepts options")
        if len({option.label for option in options}) != len(options) or len({option.order_index for option in options}) != len(options):
            raise ValueError("Option labels and order indexes must be unique")
        if len({link.concept_id for link in concepts}) != len(concepts):
            raise ValueError("Concept links must be unique")
        if fsum(link.weight for link in concepts) > 1.000001:
            raise ValueError("Concept weights cannot total more than 1")
        if len({link.problem_type_id for link in problem_types}) != len(problem_types):
            raise ValueError("Problem type links must be unique")
        if sum(link.is_primary for link in problem_types) > 1:
            raise ValueError("Only one problem type can be primary")
        if len({link.learning_outcome_id for link in learning_outcomes}) != len(
            learning_outcomes
        ):
            raise ValueError("Learning outcome links must be unique")
        if len({hint.hint_level for hint in hints}) != len(hints):
            raise ValueError("Predefined hint levels must be unique")


class QuestionCreate(QuestionWriteBase):
    subject_id: UUID
    content: str = Field(min_length=1, max_length=20000)
    question_type: QuestionType
    difficulty: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    correct_answer: str | None = Field(default=None, min_length=1, max_length=10000)
    explanation: str | None = Field(default=None, min_length=1, max_length=20000)
    source_type: str = Field(min_length=1, max_length=50)
    source_reference: str | None = Field(default=None, min_length=1, max_length=500)
    source_year: int | None = Field(default=None, ge=1900, le=2100, strict=True)
    cognitive_level: CognitiveLevel | None = None
    exam_weight: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    options: list[QuestionOptionInput] = Field(default_factory=list, max_length=10)
    concepts: list[QuestionConceptInput] = Field(default_factory=list, max_length=20)
    problem_types: list[QuestionProblemTypeInput] = Field(default_factory=list, max_length=20)
    learning_outcomes: list[QuestionLearningOutcomeInput] = Field(
        default_factory=list, max_length=20
    )
    hints: list[QuestionHintInput] = Field(default_factory=list, max_length=4)

    @field_validator("source_type")
    @classmethod
    def normalize_source_type(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_question_shape(self) -> "QuestionCreate":
        self.validate_collections(
            self.question_type,
            self.options,
            self.concepts,
            self.problem_types,
            self.learning_outcomes,
            self.hints,
        )
        return self


class QuestionPatch(QuestionWriteBase):
    subject_id: UUID | None = None
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    question_type: QuestionType | None = None
    difficulty: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    correct_answer: str | None = Field(default=None, min_length=1, max_length=10000)
    explanation: str | None = Field(default=None, min_length=1, max_length=20000)
    source_type: str | None = Field(default=None, min_length=1, max_length=50)
    source_reference: str | None = Field(default=None, min_length=1, max_length=500)
    source_year: int | None = Field(default=None, ge=1900, le=2100, strict=True)
    cognitive_level: CognitiveLevel | None = None
    exam_weight: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    status: QuestionStatus | None = None
    options: list[QuestionOptionInput] | None = Field(default=None, max_length=10)
    concepts: list[QuestionConceptInput] | None = Field(default=None, max_length=20)
    problem_types: list[QuestionProblemTypeInput] | None = Field(default=None, max_length=20)
    learning_outcomes: list[QuestionLearningOutcomeInput] | None = Field(
        default=None, max_length=20
    )
    hints: list[QuestionHintInput] | None = Field(default=None, max_length=4)

    @field_validator("source_type")
    @classmethod
    def normalize_source_type(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "QuestionPatch":
        nullable = {
            "correct_answer",
            "explanation",
            "source_reference",
            "source_year",
            "cognitive_level",
        }
        if any(getattr(self, field) is None for field in self.model_fields_set - nullable):
            raise ValueError("Required question fields cannot be null")
        return self


class QuestionOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    label: str
    content: str
    order_index: int


class QuestionConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    concept_id: UUID
    weight: float


class QuestionProblemTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    problem_type_id: UUID
    weight: float | None
    is_primary: bool


class QuestionLearningOutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    learning_outcome_id: UUID
    weight: float | None


class QuestionHintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hint_level: HintLevel
    content: str


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    subject_id: UUID
    content: str
    question_type: QuestionType
    difficulty: float
    correct_answer: str | None
    explanation: str | None
    source_type: str
    source_reference: str | None
    source_year: int | None
    cognitive_level: CognitiveLevel | None
    exam_weight: float
    status: QuestionStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    options: list[QuestionOptionRead]
    concepts: list[QuestionConceptRead] = Field(validation_alias="concept_links")
    problem_types: list[QuestionProblemTypeRead] = Field(validation_alias="problem_type_links")
    learning_outcomes: list[QuestionLearningOutcomeRead] = Field(
        validation_alias="learning_outcome_links"
    )
    hints: list[QuestionHintRead] = Field(default_factory=list)
