from __future__ import annotations

from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.misconceptions.models import MisconceptionCategory


class MisconceptionSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecommendedHintType(StrEnum):
    CONCEPT_RECALL = "CONCEPT_RECALL"          # Level 1: Khơi gợi khái niệm hoặc định lý cốt lõi
    STRATEGY_DIRECTION = "STRATEGY_DIRECTION"  # Level 2: Định hướng chiến lược tiếp cận
    NEXT_STEP = "NEXT_STEP"                    # Level 3: Chỉ dẫn bước lập luận kế tiếp hoặc điểm kiểm tra
    WORKED_EXAMPLE = "WORKED_EXAMPLE"          # Level 4: Ví dụ tương tự hoặc gần lời giải chi tiết


class CognitiveTaxonomy(StrEnum):
    REMEMBER = "REMEMBER"
    UNDERSTAND = "UNDERSTAND"
    APPLY = "APPLY"
    ANALYZE = "ANALYZE"


class MisconceptionSample(BaseModel):
    """Normalized, validated, and anonymized single sample for Misconception Detection."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Anonymized unique sample identifier (e.g. smp_a1b2c3d4)")
    question: str = Field(..., min_length=5, description="Full question text content and options if any")
    problem_type: str = Field(..., min_length=2, description="Canonical ProblemType code or name")
    concepts: list[str] = Field(..., min_length=1, description="List of mapped Concept codes")
    learning_outcomes: list[str] | None = Field(
        default=None, description="Optional list of mapped Learning Outcome codes"
    )
    taxonomy: CognitiveTaxonomy = Field(
        ..., description="Cognitive taxonomy level (REMEMBER, UNDERSTAND, APPLY, ANALYZE)"
    )
    student_solution: str = Field(
        ..., min_length=2, description="Submitted student answer, explanation, and reasoning steps"
    )
    reference_solution: str = Field(
        ..., min_length=2, description="Expected correct answer and complete reference explanation"
    )
    verified_misconception_label: str = Field(
        ..., min_length=2, description="Canonical code of the verified misconception definition"
    )
    error_category: MisconceptionCategory = Field(
        ..., description="Standardized error category (CONCEPTUAL, PROCEDURAL, CALCULATION, READING, CARELESS, OTHER)"
    )
    severity: MisconceptionSeverity = Field(
        ..., description="Severity impact of the diagnosed misconception"
    )
    recommended_hint_type: RecommendedHintType = Field(
        ..., description="Pedagogical hint strategy recommended for this mistake"
    )
    cluster_id: str | None = Field(
        default=None, description="Question cluster identifier used for leak-free splitting"
    )
    split: str | None = Field(
        default=None, description="Designated split partition (train, validation, test)"
    )


class SFTRecord(BaseModel):
    """Supervised Fine-Tuning (SFT) formatted representation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    instruction: str
    input: dict[str, Any]
    output: dict[str, Any]


class SplitStats(BaseModel):
    sample_count: int
    percentage: float
    question_clusters_count: int
    cluster_ids: list[str]


class LeakageCheckResult(BaseModel):
    is_leak_free: bool
    train_val_cluster_overlap: int
    train_test_cluster_overlap: int
    val_test_cluster_overlap: int
    train_val_question_text_overlap: int
    train_test_question_text_overlap: int
    val_test_question_text_overlap: int
    notes: str


class DatasetReport(BaseModel):
    """Comprehensive dataset report metrics."""

    dataset_version: str
    total_samples: int
    unique_question_clusters: int
    problem_type_distribution: dict[str, int]
    concept_distribution: dict[str, int]
    class_distribution: dict[str, int]
    error_category_distribution: dict[str, int]
    severity_distribution: dict[str, int]
    recommended_hint_type_distribution: dict[str, int]
    taxonomy_distribution: dict[str, int]
    missing_values: dict[str, int]
    duplicates_detected: int
    splits: dict[str, SplitStats]
    leakage_check: LeakageCheckResult
