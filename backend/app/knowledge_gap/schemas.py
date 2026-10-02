from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge_gap.models import RootCauseDiagnosisStatus, RootCauseDiagnosisType
from app.learning_evidence.models import LearningEvidenceSourceKind


class KnowledgeGapType(StrEnum):
    """Classification of a student's knowledge gap for a specific ProblemType."""

    CURRENT_PROBLEM_TYPE_GAP = "CURRENT_PROBLEM_TYPE_GAP"
    PREREQUISITE_CONCEPT_GAP = "PREREQUISITE_CONCEPT_GAP"
    PERSISTENT_MISCONCEPTION = "PERSISTENT_MISCONCEPTION"
    MULTI_CONCEPT_GAP = "MULTI_CONCEPT_GAP"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class KnowledgeGapResult(BaseModel):
    """Authoritative result produced by the KnowledgeGapService."""

    model_config = ConfigDict(extra="ignore")

    gap_type: KnowledgeGapType = Field(
        ...,
        description="Authoritative gap classification determined by backend policy.",
    )
    target_problem_type_id: UUID | None = Field(
        default=None,
        description="Target problem type ID associated with the gap.",
    )
    target_problem_type_code: str | None = Field(
        default=None,
        description="Target problem type code.",
    )
    target_concept_id: UUID | None = Field(
        default=None,
        description="Target concept ID associated with the gap (especially for prerequisite gaps).",
    )
    target_concept_code: str | None = Field(
        default=None,
        description="Target concept code.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="List of factual observations and diagnostic indicators supporting the classification.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence level of the diagnosis.",
    )
    reason_code: str = Field(
        ...,
        description="Standardized machine-readable code explaining the specific reason for the classification.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional academic context (e.g. mastery scores, attempt counts, AI insights).",
    )


class AIGapDiagnosisOutput(BaseModel):
    """Structured output from AI when consulting reasoning in borderline cases."""

    model_config = ConfigDict(extra="ignore")

    suggested_gap_type: KnowledgeGapType = Field(
        ...,
        description="The AI's recommended gap classification based on student scratchwork and curriculum context.",
    )
    target_concept_id: UUID | None = Field(
        default=None,
        description="Optional concept ID if the gap is identified as a specific concept or prerequisite.",
    )
    target_problem_type_id: UUID | None = Field(
        default=None,
        description="Optional problem type ID.",
    )
    observations: list[str] = Field(
        default_factory=list,
        description="Key diagnostic observations made from the student's reasoning.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the AI diagnosis.",
    )
    reason_code: str = Field(
        ...,
        description="Diagnostic summary code (e.g. 'PREREQUISITE_GAP_OBSERVED', 'SYNTHESIS_ERROR').",
    )

class RootCauseCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    candidate_type: RootCauseDiagnosisType
    concept_id: UUID | None
    problem_type_id: UUID | None
    misconception_definition_id: UUID | None
    graph_distance: int | None
    score: float
    confidence: float
    mastery_deficit_signal: float
    recent_error_signal: float
    structural_signal: float
    misconception_signal: float
    evidence_volume_signal: float
    supporting_event_count: int
    conflicting_event_count: int
    reason_codes: list[str]


class RootCauseSourceEventRead(BaseModel):
    id: UUID
    source_kind: LearningEvidenceSourceKind
    source_entity_id: UUID
    occurred_at: datetime


class RootCauseDiagnosisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    learning_evidence_event_id: UUID
    student_id: UUID
    subject_id: UUID
    classroom_id: UUID | None
    assignment_id: UUID | None
    target_problem_type_id: UUID | None
    diagnosis_type: RootCauseDiagnosisType
    status: RootCauseDiagnosisStatus
    root_concept_id: UUID | None
    misconception_definition_id: UUID | None
    confidence: float
    supporting_evidence_count: int
    reason_code: str
    explanation: str
    source_event: RootCauseSourceEventRead
    candidates: list[RootCauseCandidateRead]
    created_at: datetime
