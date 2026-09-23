from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.misconceptions.models import MisconceptionCategory, StudentMisconceptionStatus


class MisconceptionAnalysisOutput(BaseModel):
    """Structured output expected from AI or deterministic misconception diagnosis."""

    model_config = ConfigDict(extra="ignore")

    concept_id: UUID = Field(
        ...,
        description="ID of the concept where the misconception or error occurred.",
    )
    problem_type_id: UUID | None = Field(
        default=None,
        description="Optional ID of the specific problem type associated with this misconception.",
    )
    misconception_code: str = Field(
        ...,
        description="Canonical code of the diagnosed misconception from the supplied taxonomy, or 'UNKNOWN'.",
    )
    error_category: MisconceptionCategory = Field(
        ...,
        description="Category classification of the diagnosed mistake.",
    )
    first_wrong_step: str | None = Field(
        default=None,
        description="Description of the specific step or reasoning juncture where the error first emerged.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 of the diagnosis.",
    )
    possible_prerequisite_concept_id: UUID | None = Field(
        default=None,
        description="Optional concept ID if the root cause is a deficiency in a prerequisite concept.",
    )
    requires_prerequisite_check: bool = Field(
        default=False,
        description="Whether a diagnostic check on the prerequisite concept is recommended.",
    )

    def validate_against_taxonomy(
        self,
        allowed_codes: set[str],
        allowed_concept_ids: set[UUID],
        allowed_problem_type_ids: set[UUID],
        allowed_prerequisite_concept_ids: set[UUID],
    ) -> None:
        """Enforce strict taxonomy guardrails:
        - AI cannot invent new misconception codes.
        - AI cannot reference concepts outside the scoped question/prerequisite domain.
        """
        normalized_code = self.misconception_code.strip()
        if normalized_code != "UNKNOWN" and normalized_code not in allowed_codes:
            # Revert to UNKNOWN if AI generated an invented or out-of-scope code
            self.misconception_code = "UNKNOWN"

        if self.concept_id not in allowed_concept_ids:
            # If concept_id is invalid or out of scope, treat as UNKNOWN
            self.misconception_code = "UNKNOWN"

        if (
            self.problem_type_id is not None
            and self.problem_type_id not in allowed_problem_type_ids
        ):
            self.problem_type_id = None

        if (
            self.possible_prerequisite_concept_id is not None
            and self.possible_prerequisite_concept_id not in allowed_prerequisite_concept_ids
        ):
            self.possible_prerequisite_concept_id = None
            self.requires_prerequisite_check = False


class MisconceptionPipelineResult(BaseModel):
    """Complete result returned after processing an attempt through the misconception pipeline."""

    model_config = ConfigDict(extra="ignore")

    detected: bool = Field(
        ...,
        description="Whether a valid, active misconception was identified.",
    )
    detection_source: Literal["DETERMINISTIC", "AI", "NONE"] = Field(
        ...,
        description="Source of the detection: deterministic rule, AI analysis, or none.",
    )
    misconception_definition_id: UUID | None = Field(
        default=None,
        description="Database UUID of the identified MisconceptionDefinition if mapped.",
    )
    misconception_code: str | None = Field(
        default=None,
        description="Canonical code of the identified misconception definition.",
    )
    concept_id: UUID | None = Field(
        default=None,
        description="Concept ID associated with the error.",
    )
    problem_type_id: UUID | None = Field(
        default=None,
        description="Problem Type ID associated with the error.",
    )
    error_category: MisconceptionCategory | None = Field(
        default=None,
        description="Category classification.",
    )
    first_wrong_step: str | None = Field(
        default=None,
        description="First identified erroneous step.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score of the identification.",
    )
    possible_prerequisite_concept_id: UUID | None = Field(
        default=None,
        description="Prerequisite concept ID if a foundational gap was flagged.",
    )
    requires_prerequisite_check: bool = Field(
        default=False,
        description="Whether prerequisite follow-up is suggested.",
    )
    evidence_recorded: bool = Field(
        default=False,
        description="Whether evidence was recorded in student_misconceptions according to policy.",
    )
    student_misconception_status: StudentMisconceptionStatus | None = Field(
        default=None,
        description="Updated status of the student's misconception in the database.",
    )
    occurrence_count: int | None = Field(
        default=None,
        description="Updated total occurrences for this student and misconception.",
    )
    reason: str | None = Field(
        default=None,
        description="Explanatory diagnostic note or skip reason.",
    )
