from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import ApplicationError


class OpenResponseEvaluationOutput(BaseModel):
    """Structured response schema returned by AI for open response evaluation."""

    model_config = ConfigDict(extra="ignore")

    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Awarded score normalized between 0.0 and 1.0",
    )
    is_correct: bool = Field(
        ...,
        description="Whether the response meets the threshold of correctness",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Pedagogical explanation of the evaluation and feedback",
    )
    evidence: str = Field(
        ...,
        description="Direct quotes or specific references from the student's submission",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score in this evaluation from 0.0 to 1.0",
    )
    demonstrated_concept_codes: list[str] = Field(
        default_factory=list,
        description="Concepts from supplied list demonstrably understood",
    )
    weak_concept_codes: list[str] = Field(
        default_factory=list,
        description="Concepts from supplied list showing gaps or misconceptions",
    )
    demonstrated_learning_outcome_codes: list[str] = Field(
        default_factory=list,
        description="Learning outcomes from supplied list achieved by student",
    )

    def validate_against_whitelist(
        self,
        *,
        allowed_concept_codes: set[str],
        allowed_learning_outcome_codes: set[str],
    ) -> None:
        """Enforce strict whitelist: AI cannot hallucinate new Concept or LearningOutcome codes."""
        unknown_demonstrated = set(self.demonstrated_concept_codes) - allowed_concept_codes
        if unknown_demonstrated:
            raise ApplicationError(
                422,
                "UNAUTHORIZED_CONCEPT_CODE",
                f"AI returned unauthorized concept codes: {sorted(unknown_demonstrated)}",
            )
        unknown_weak = set(self.weak_concept_codes) - allowed_concept_codes
        if unknown_weak:
            raise ApplicationError(
                422,
                "UNAUTHORIZED_CONCEPT_CODE",
                f"AI returned unauthorized weak concept codes: {sorted(unknown_weak)}",
            )
        unknown_lo = (
            set(self.demonstrated_learning_outcome_codes) - allowed_learning_outcome_codes
        )
        if unknown_lo:
            raise ApplicationError(
                422,
                "UNAUTHORIZED_LEARNING_OUTCOME_CODE",
                f"AI returned unauthorized learning outcome codes: {sorted(unknown_lo)}",
            )


class AIEvaluateAttemptRequest(BaseModel):
    rubric: str | None = None
    confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
