from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HeatmapView(StrEnum):
    """View dimension for the competency heatmap."""

    PROBLEM_TYPE = "problem_type"
    CONCEPT = "concept"
    TOPIC = "topic"
    CHAPTER = "chapter"


class AlertRuleCode(StrEnum):
    """Deterministic pedagogical intervention rule codes."""

    LOW_PROBLEM_TYPE_MASTERY = "LOW_PROBLEM_TYPE_MASTERY"
    PREREQUISITE_GAP = "PREREQUISITE_GAP"
    PERSISTENT_MISCONCEPTION = "PERSISTENT_MISCONCEPTION"
    FAILED_REPAIR = "FAILED_REPAIR"
    DECLINING_PERFORMANCE = "DECLINING_PERFORMANCE"
    INACTIVE_STUDY = "INACTIVE_STUDY"


class AlertSeverity(StrEnum):
    """Severity tier for pedagogical intervention alerts."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MasteryLevel(StrEnum):
    """Competency band based on numerical mastery score."""

    MASTERED = "MASTERED"  # >= 0.80
    PROFICIENT = "PROFICIENT"  # 0.60 - 0.79
    STRUGGLING = "STRUGGLING"  # 0.40 - 0.59
    CRITICAL = "CRITICAL"  # < 0.40
    NOT_STARTED = "NOT_STARTED"


# ------------------------------------------------------------------------------
# Dashboard Analytics Schemas
# ------------------------------------------------------------------------------


class MetricItemRead(BaseModel):
    """Summary metric for a single ProblemType or Concept."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str
    average_score: float = Field(..., ge=0.0, le=1.0)
    student_count: int = Field(..., ge=0)


class SubjectProgressRead(BaseModel):
    """Progress overview for a subject within the classroom."""

    subject_id: UUID
    subject_name: str
    subject_code: str
    average_mastery: float = Field(..., ge=0.0, le=1.0)
    completion_percentage: float = Field(..., ge=0.0, le=100.0)


class ChapterProgressRead(BaseModel):
    """Progress overview for a specific curriculum chapter."""

    chapter_id: UUID
    chapter_name: str
    chapter_code: str
    subject_name: str
    average_mastery: float = Field(..., ge=0.0, le=1.0)
    proficient_student_count: int = Field(..., ge=0)
    total_student_count: int = Field(..., ge=0)


class TopicProgressRead(BaseModel):
    """Progress overview for a specific curriculum topic."""

    topic_id: UUID
    topic_name: str
    topic_code: str
    chapter_name: str
    average_mastery: float = Field(..., ge=0.0, le=1.0)


class MisconceptionMetricRead(BaseModel):
    """Classroom-level aggregation of active misconceptions."""

    definition_id: UUID
    code: str
    name: str
    affected_students_count: int = Field(..., ge=0)
    affected_student_names: list[str] = Field(default_factory=list)


class RecentTrendsRead(BaseModel):
    """7-day activity and score progression compared to previous cycle."""

    total_attempts_past_7_days: int = Field(..., ge=0)
    recent_average_score: float = Field(..., ge=0.0, le=1.0)
    previous_average_score: float | None = Field(default=None, ge=0.0, le=1.0)
    trend_direction: str = Field(..., description="IMPROVING, DECLINING, or STABLE")


class StudyCompletionRead(BaseModel):
    """Classroom study task adherence metrics."""

    assigned_tasks_count: int = Field(..., ge=0)
    completed_tasks_count: int = Field(..., ge=0)
    completion_rate: float = Field(..., ge=0.0, le=100.0)


class StudentAttentionRead(BaseModel):
    """Summary of a student requiring immediate teacher intervention."""

    student_id: UUID
    student_name: str
    alert_codes: list[AlertRuleCode] = Field(default_factory=list)
    highest_severity: AlertSeverity
    summary_reason: str
    alert_count: int = Field(..., ge=1)


class ClassroomAnalyticsDashboardRead(BaseModel):
    """Comprehensive analytics dashboard for a teacher's classroom."""

    classroom_id: UUID
    classroom_name: str
    student_count: int
    subject_progress: list[SubjectProgressRead]
    chapter_progress: list[ChapterProgressRead]
    topic_progress: list[TopicProgressRead]
    strong_problem_types: list[MetricItemRead]
    weak_problem_types: list[MetricItemRead]
    strong_concepts: list[MetricItemRead]
    weak_concepts: list[MetricItemRead]
    common_misconceptions: list[MisconceptionMetricRead]
    recent_trends: RecentTrendsRead
    study_completion: StudyCompletionRead
    students_needing_attention: list[StudentAttentionRead]


# ------------------------------------------------------------------------------
# Heatmap Schemas
# ------------------------------------------------------------------------------


class HeatmapColumnRead(BaseModel):
    """Dimension column representing an item (ProblemType/Concept/Topic/Chapter)."""

    id: UUID
    name: str
    code: str
    parent_name: str | None = None
    order_index: int = 0


class HeatmapRowRead(BaseModel):
    """Dimension row representing an enrolled student."""

    student_id: UUID
    student_name: str
    is_synthetic: bool = False


class HeatmapCellRead(BaseModel):
    """Individual cell intersection of Student and Column Item."""

    student_id: UUID
    column_id: UUID
    score: float | None = None
    level: MasteryLevel
    attempt_count: int = 0


class ClassroomHeatmapRead(BaseModel):
    """Multi-view competency heatmap data structure."""

    classroom_id: UUID
    view: HeatmapView
    columns: list[HeatmapColumnRead]
    rows: list[HeatmapRowRead]
    cells: list[HeatmapCellRead]
    column_averages: dict[str, float] = Field(
        default_factory=dict,
        description="Average mastery score of the class for each column ID.",
    )
    row_averages: dict[str, float] = Field(
        default_factory=dict,
        description="Average mastery score across all columns for each student ID.",
    )


# ------------------------------------------------------------------------------
# Intervention Alerts Schemas
# ------------------------------------------------------------------------------


class InterventionAlertRead(BaseModel):
    """Individual pedagogical alert flagged by deterministic rules."""

    id: str = Field(..., description="Deterministic or unique identifier for the alert.")
    student_id: UUID
    student_name: str
    rule_code: AlertRuleCode
    severity: AlertSeverity
    title: str
    message: str
    target_id: UUID | None = None
    target_name: str | None = None
    metric_value: float | None = None
    detected_at: datetime
    suggested_action: str


class ClassroomAlertsRead(BaseModel):
    """Full list of intervention alerts for a classroom."""

    classroom_id: UUID
    total_alerts: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    alerts: list[InterventionAlertRead]
