from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class EvaluationGroup(StrEnum):
    LEARNING_ENGINE = "LEARNING_ENGINE"
    MISCONCEPTION = "MISCONCEPTION"
    RAG = "RAG"
    AI_TUTOR = "AI_TUTOR"
    TEACHER_COPILOT = "TEACHER_COPILOT"
    PARENT_SUMMARY = "PARENT_SUMMARY"
    SYSTEM_AI = "SYSTEM_AI"


class MetricStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class MetricScore(BaseModel):
    """Evaluation metric outcome."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Canonical metric identifier")
    score: float = Field(..., description="Numeric score or rate (typically 0.0 to 1.0, or average value)")
    status: MetricStatus = Field(default=MetricStatus.PASS, description="Pass/Warn/Fail evaluation status")
    threshold: float | None = Field(default=None, description="Target threshold required for PASS")
    unit: str = Field(default="", description="Unit of measurement (%, ms, tokens, USD, etc.)")
    description: str = Field(default="", description="Brief description of what this metric assesses")
    details: dict[str, Any] = Field(default_factory=dict, description="Diagnostic breakdown or details")


class GroupEvaluationResult(BaseModel):
    """Aggregate result for one evaluation domain group."""

    model_config = ConfigDict(extra="ignore")

    group: EvaluationGroup = Field(..., description="The evaluation group name")
    passed: bool = Field(..., description="Whether all critical group metrics passed")
    overall_score: float = Field(..., description="Combined group score (0.0 to 1.0 or percentage)")
    sample_count: int = Field(..., description="Number of evaluation items assessed")
    metrics: list[MetricScore] = Field(default_factory=list, description="List of granular metric results")
    breakdown: dict[str, Any] = Field(
        default_factory=dict, description="Optional breakdowns (e.g. by Concept, ProblemType, TaskType)"
    )
    confusion_matrix: dict[str, Any] | None = Field(
        default=None, description="Optional confusion matrix (for classification tasks like Misconception)"
    )
    notes: str = Field(default="", description="Qualitative findings or warnings")


class FullEvaluationReport(BaseModel):
    """Complete evaluation report aggregating all evaluation groups."""

    model_config = ConfigDict(extra="ignore")

    evaluation_id: str
    timestamp: str
    framework_version: str = "v1.0"
    total_samples_evaluated: int
    overall_passed: bool
    groups: dict[str, GroupEvaluationResult]
    metadata: dict[str, Any] = Field(default_factory=dict)
