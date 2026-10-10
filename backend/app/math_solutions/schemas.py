"""Public-neutral typed DTOs for upcoming math-solution v2 services.

No FastAPI routes are registered in STEP-ARCH-01.
"""
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


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


class MathArtifactDraft(BaseModel):
    artifact_type: ArtifactKind
    payload: dict[str, Any]


class SolutionStepDraft(BaseModel):
    step_type: StepKind
    content_latex: str | None = Field(default=None, max_length=12000)
    explanation_text: str | None = Field(default=None, max_length=12000)
    artifact: MathArtifactDraft | None = None

    @model_validator(mode="after")
    def require_content(self):
        if not ((self.content_latex or "").strip() or (self.explanation_text or "").strip() or self.artifact):
            raise ValueError("A solution step needs content or a structured artifact.")
        return self


class AttemptMutationToken(BaseModel):
    expected_attempt_revision: int = Field(ge=1)
    client_action_id: UUID
