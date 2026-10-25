"""Typed public contracts for the API v2 mathematics workspace."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.questions.models import QuestionType


class SolutionContext(StrEnum):
    SELF_PRACTICE = "SELF_PRACTICE"
    CLASSROOM_ASSIGNMENT = "CLASSROOM_ASSIGNMENT"


class SolutionMode(StrEnum):
    GUIDED_LEARNING = "GUIDED_LEARNING"
    INDEPENDENT_SOLUTION = "INDEPENDENT_SOLUTION"


class StepKind(StrEnum):
    ASSUMPTION = "ASSUMPTION"
    DERIVATIVE_CALCULATION = "DERIVATIVE_CALCULATION"
    ROOT_FINDING = "ROOT_FINDING"
    SIGN_TABLE = "SIGN_TABLE"
    VARIATION_TABLE = "VARIATION_TABLE"
    CONCLUSION = "CONCLUSION"
    EXPLANATION = "EXPLANATION"
    CUSTOM = "CUSTOM"


class ArtifactKind(StrEnum):
    SIGN_TABLE = "SIGN_TABLE"
    VARIATION_TABLE = "VARIATION_TABLE"
    INTERVAL_SET = "INTERVAL_SET"
    SYSTEM_OF_EQUATIONS = "SYSTEM_OF_EQUATIONS"


class SolutionSourceKind(StrEnum):
    CANONICAL = "CANONICAL"
    TEACHER_MATERIAL = "TEACHER_MATERIAL"


class SolutionAttemptStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    EVALUATED = "EVALUATED"
    ABANDONED = "ABANDONED"


class VariationTablePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    x: str = Field(min_length=1, max_length=80)
    derivative: Literal["", "0", "undefined", "?"] = ""
    y: str = Field(default="", max_length=80)


class VariationTableInterval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sign: Literal["+", "-", "0", "?"]
    trend: Literal["UP", "DOWN", "FLAT", "UNKNOWN"]


class VariationTablePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    points: list[VariationTablePoint] = Field(min_length=2, max_length=12)
    intervals: list[VariationTableInterval] = Field(min_length=1, max_length=11)

    @model_validator(mode="after")
    def validate_columns(self) -> "VariationTablePayload":
        if len(self.intervals) != len(self.points) - 1:
            raise ValueError("A variation table needs one interval between adjacent x points.")
        if len({point.x for point in self.points}) != len(self.points):
            raise ValueError("x boundaries must be distinct.")
        expected = {"+": "UP", "-": "DOWN", "0": "FLAT", "?": "UNKNOWN"}
        for interval in self.intervals:
            if interval.trend != expected[interval.sign]:
                raise ValueError("The derivative sign conflicts with the drawn variation.")
        return self


class MathArtifactDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    artifact_type: ArtifactKind
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_variation_table(self) -> "MathArtifactDraft":
        if self.artifact_type == ArtifactKind.VARIATION_TABLE:
            self.payload = VariationTablePayload.model_validate(self.payload).model_dump(mode="json")
        return self


class SolutionStepDraft(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True
    )

    step_type: StepKind
    content_latex: str | None = Field(default=None, max_length=12000)
    explanation_text: str | None = Field(default=None, max_length=12000)
    artifact: MathArtifactDraft | None = None

    @model_validator(mode="after")
    def require_content(self) -> "SolutionStepDraft":
        if self.artifact and self.artifact.artifact_type == ArtifactKind.VARIATION_TABLE and self.step_type != StepKind.VARIATION_TABLE:
            raise ValueError("A variation table artifact requires a variation table step.")
        if not (
            (self.content_latex or "").strip()
            or (self.explanation_text or "").strip()
            or self.artifact
        ):
            raise ValueError("A solution step needs content or a structured artifact.")
        return self


class AttemptMutationToken(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expected_attempt_revision: int = Field(ge=1)
    client_action_id: UUID


class AttemptCreateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True
    )

    source_kind: SolutionSourceKind
    context_type: SolutionContext
    mode: SolutionMode
    create_idempotency_key: str = Field(min_length=1, max_length=100)
    question_id: UUID | None = None
    practice_session_id: UUID | None = None
    student_assignment_id: UUID | None = None
    assignment_student_question_id: UUID | None = None
    student_assignment_material_item_id: UUID | None = None
    rubric_id: UUID | None = None


class StepMutationRequest(AttemptMutationToken):
    step_type: StepKind
    content_latex: str | None = Field(default=None, max_length=12000)
    explanation_text: str | None = Field(default=None, max_length=12000)
    artifact: MathArtifactDraft | None = None

    @model_validator(mode="after")
    def require_step_content(self) -> "StepMutationRequest":
        self.to_draft()
        return self

    def to_draft(self) -> SolutionStepDraft:
        return SolutionStepDraft(
            step_type=self.step_type,
            content_latex=self.content_latex,
            explanation_text=self.explanation_text,
            artifact=self.artifact,
        )


class ReorderStepsRequest(AttemptMutationToken):
    step_ids: list[UUID] = Field(min_length=1, max_length=500)

    @field_validator("step_ids")
    @classmethod
    def require_unique_steps(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Step identifiers must be unique")
        return value


class RollbackStepRequest(AttemptMutationToken):
    to_revision: int = Field(ge=1)


class MathArtifactRead(BaseModel):
    artifact_type: ArtifactKind
    payload: dict[str, Any]


class SolutionStepRead(BaseModel):
    id: UUID
    step_index: int = Field(ge=1)
    step_type: StepKind
    content_latex: str | None
    explanation_text: str | None
    step_revision_number: int = Field(ge=1)
    artifact: MathArtifactRead | None


class SolutionAttemptRead(BaseModel):
    id: UUID
    status: SolutionAttemptStatus
    context_type: SolutionContext
    source_kind: SolutionSourceKind
    mode: SolutionMode
    attempt_revision_number: int = Field(ge=1)
    question_id: UUID | None = None
    practice_session_id: UUID | None = None
    student_assignment_id: UUID | None = None
    assignment_student_question_id: UUID | None = None
    student_assignment_material_item_id: UUID | None = None
    steps: list[SolutionStepRead]
    started_at: datetime
    updated_at: datetime
    submitted_at: datetime | None


class StepRevisionRead(BaseModel):
    id: UUID
    step_revision_number: int = Field(ge=1)
    step_index_at_revision: int = Field(ge=1)
    content_latex: str | None
    explanation_text: str | None
    artifact: MathArtifactRead | None
    change_reason: str
    created_at: datetime


class ProblemOptionRead(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    id: UUID
    label: str
    content: str
    order_index: int


class ProblemSourceMetadataRead(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    title: str | None = None
    subject_id: UUID | None = None
    grade_level: int | None = None
    page_start: int | None = None
    page_end: int | None = None


class ProblemRead(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    id: UUID
    source_kind: SolutionSourceKind
    context_type: SolutionContext
    content: str
    question_type: QuestionType
    options: list[ProblemOptionRead] = Field(default_factory=list)
    order_index: int | None = None
    is_read_only: bool = False

    question_id: UUID | None = None
    practice_session_id: UUID | None = None
    assignment_id: UUID | None = None
    student_assignment_id: UUID | None = None
    assignment_student_question_id: UUID | None = None
    student_assignment_material_item_id: UUID | None = None

    source_metadata: ProblemSourceMetadataRead | None = None


class PrepareAssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    student_assignment_id: UUID
    status: str
    item_count: int
    problems: list[ProblemRead]


class PaginatedSolutionAttemptsRead(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    items: list[SolutionAttemptRead]
    total: int
    page: int
    size: int
    total_pages: int

