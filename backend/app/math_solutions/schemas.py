"""Typed public contracts for the API v2 mathematics workspace."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class MathArtifactDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    artifact_type: ArtifactKind
    payload: dict[str, Any]


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
