from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.assignments.models import AssignmentStatus, StudentAssignmentStatus


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
    REVIEW_OVERDUE = "REVIEW_OVERDUE"
    ASSIGNMENT_OVERDUE = "ASSIGNMENT_OVERDUE"


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
    observed_student_target_pairs: int = Field(default=0, ge=0)
    total_possible_student_target_pairs: int = Field(default=0, ge=0)
    coverage_percentage: float = Field(default=0.0, ge=0.0, le=100.0)


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
    total_evidence_past_7_days: int = Field(default=0, ge=0)
    scored_evidence_past_7_days: int = Field(default=0, ge=0)
    recent_average_score: float = Field(..., ge=0.0, le=1.0)
    previous_average_score: float | None = Field(default=None, ge=0.0, le=1.0)
    correct_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    score_delta: float | None = Field(default=None)
    trend_direction: str = Field(
        ...,
        description="IMPROVING, DECLINING, STABLE, or INSUFFICIENT_DATA",
    )


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


class EvidenceSourceSummaryRead(BaseModel):
    """Breakdown of classroom learning evidence sources."""

    practice_count: int = Field(default=0, ge=0)
    assignment_question_count: int = Field(default=0, ge=0)
    teacher_material_count: int = Field(default=0, ge=0)
    total_count: int = Field(default=0, ge=0)


class AssignmentCompletionRead(BaseModel):
    """Classroom-level teacher assignment completion metrics."""

    assignment_count: int = Field(default=0, ge=0)
    assigned_student_count: int = Field(default=0, ge=0)
    not_started_count: int = Field(default=0, ge=0)
    in_progress_count: int = Field(default=0, ge=0)
    submitted_count: int = Field(default=0, ge=0)
    graded_count: int = Field(default=0, ge=0)
    overdue_count: int = Field(default=0, ge=0)
    average_score: float | None = Field(default=None, ge=0.0, le=1.0)
    completion_rate: float = Field(default=0.0, ge=0.0, le=100.0)


class ReviewDueSummaryRead(BaseModel):
    """Classroom-level spaced repetition review schedule summary."""

    due_now_count: int = Field(default=0, ge=0)
    due_next_3_days_count: int = Field(default=0, ge=0)
    students_due_count: int = Field(default=0, ge=0)
    problem_type_due_count: int = Field(default=0, ge=0)
    concept_due_count: int = Field(default=0, ge=0)


class VerifiedRootCauseMetricRead(BaseModel):
    """Classroom-level verified pedagogical root cause summary."""

    target_type: str
    target_id: UUID
    target_name: str
    affected_student_count: int = Field(default=0, ge=0)
    student_ids: list[UUID] = Field(default_factory=list)
    affects_current_plan: bool = False


class RepairSummaryRead(BaseModel):
    """Classroom-level adaptive repair session progress and outcomes."""

    active_count: int = Field(default=0, ge=0)
    completed_count: int = Field(default=0, ge=0)
    resolved_count: int = Field(default=0, ge=0)
    needs_more_practice_count: int = Field(default=0, ge=0)
    bank_exhausted_count: int = Field(default=0, ge=0)
    resolution_rate: float = Field(default=0.0, ge=0.0, le=100.0)


class LearningEvidenceSummaryRead(BaseModel):
    """Classroom-level learning evidence volume and evaluation status summary."""

    total_events: int = Field(default=0, ge=0)
    scored_events: int = Field(default=0, ge=0)
    correct_events: int = Field(default=0, ge=0)
    average_score: float | None = Field(default=None, ge=0.0, le=1.0)
    correct_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_response_time_seconds: float | None = Field(default=None, ge=0.0)
    average_hint_count: float | None = Field(default=None, ge=0.0)
    needs_teacher_review_count: int = Field(default=0, ge=0)
    needs_evaluation_count: int = Field(default=0, ge=0)


class ActiveTeachingPlanSummaryRead(BaseModel):
    """Current active teaching plan context for the classroom."""

    teaching_plan_id: UUID
    subject_id: UUID
    active_problem_type_ids: list[UUID] = Field(default_factory=list)
    active_learning_outcome_ids: list[UUID] = Field(default_factory=list)


class CurrentPlanMasteryRead(BaseModel):
    """Current mastery metrics aligned with active teaching plan problem types."""

    average_mastery: float | None = Field(default=None, ge=0.0, le=1.0)
    students_below_0_6: int = Field(default=0, ge=0)
    students_below_0_4: int = Field(default=0, ge=0)


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
    evidence_sources: EvidenceSourceSummaryRead = Field(default_factory=EvidenceSourceSummaryRead)
    assignment_completion: AssignmentCompletionRead = Field(default_factory=AssignmentCompletionRead)
    review_due: ReviewDueSummaryRead = Field(default_factory=ReviewDueSummaryRead)
    verified_root_causes: list[VerifiedRootCauseMetricRead] = Field(default_factory=list)
    repair_summary: RepairSummaryRead = Field(default_factory=RepairSummaryRead)
    evidence_summary: LearningEvidenceSummaryRead = Field(default_factory=LearningEvidenceSummaryRead)
    active_teaching_plan: ActiveTeachingPlanSummaryRead | None = None
    current_plan_mastery: CurrentPlanMasteryRead | None = None


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
    confidence: float | None = None
    last_practiced_at: datetime | None = None
    observed_target_count: int = 0
    total_target_count: int = 0


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


# ------------------------------------------------------------------------------
# Student Drilldown Analytics Schemas
# ------------------------------------------------------------------------------


class StudentMasteryItemRead(BaseModel):
    """Mastery progress for an individual student on a specific target."""

    target_id: UUID
    target_code: str
    target_name: str
    mastery_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    attempt_count: int = Field(..., ge=0)
    correct_count: int = Field(..., ge=0)
    last_practiced_at: datetime | None = None
    level: MasteryLevel


class StudentAssignmentSummaryRead(BaseModel):
    """Assignment completion summary for an individual student."""

    total_assigned: int = Field(default=0, ge=0)
    not_started_count: int = Field(default=0, ge=0)
    in_progress_count: int = Field(default=0, ge=0)
    submitted_count: int = Field(default=0, ge=0)
    graded_count: int = Field(default=0, ge=0)
    overdue_count: int = Field(default=0, ge=0)
    completion_rate: float = Field(default=0.0, ge=0.0, le=100.0)
    average_score: float | None = Field(default=None, ge=0.0, le=1.0)


class StudentLearningAnalyticsRead(BaseModel):
    """Detailed analytics drilldown for a single student in a classroom."""

    student_id: UUID
    student_name: str
    classroom_id: UUID
    subject_id: UUID | None = None
    problem_type_mastery: list[StudentMasteryItemRead] = Field(default_factory=list)
    concept_mastery: list[StudentMasteryItemRead] = Field(default_factory=list)
    recent_evidence: RecentTrendsRead
    evidence_sources: EvidenceSourceSummaryRead = Field(default_factory=EvidenceSourceSummaryRead)
    verified_root_causes: list[VerifiedRootCauseMetricRead] = Field(default_factory=list)
    repair_summary: RepairSummaryRead = Field(default_factory=RepairSummaryRead)
    reviews_due: ReviewDueSummaryRead = Field(default_factory=ReviewDueSummaryRead)
    assignment_summary: StudentAssignmentSummaryRead = Field(default_factory=StudentAssignmentSummaryRead)
    alerts: list[InterventionAlertRead] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# Assignment Analytics Schemas
# ------------------------------------------------------------------------------


class AssignmentTargetPerformanceRead(BaseModel):
    """Aggregated performance on a ProblemType, Concept, or LearningOutcome in an assignment."""

    target_id: UUID
    target_name: str
    target_code: str | None = None
    average_score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_count: int = Field(default=0, ge=0)


class AssignmentStudentRowRead(BaseModel):
    """Student status and performance on a specific assignment."""

    student_id: UUID
    student_name: str
    status: StudentAssignmentStatus
    score: float | None = None
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    is_overdue: bool = False


class AssignmentAnalyticsRead(BaseModel):
    """Detailed assignment performance report for teacher inspection."""

    assignment_id: UUID
    title: str
    status: AssignmentStatus
    due_at: datetime | None = None
    assigned_count: int = Field(default=0, ge=0)
    not_started_count: int = Field(default=0, ge=0)
    in_progress_count: int = Field(default=0, ge=0)
    submitted_count: int = Field(default=0, ge=0)
    graded_count: int = Field(default=0, ge=0)
    overdue_count: int = Field(default=0, ge=0)
    completion_rate: float = Field(default=0.0, ge=0.0, le=100.0)
    average_score: float | None = Field(default=None, ge=0.0, le=1.0)
    target_problem_types: list[AssignmentTargetPerformanceRead] = Field(default_factory=list)
    target_concepts: list[AssignmentTargetPerformanceRead] = Field(default_factory=list)
    target_learning_outcomes: list[AssignmentTargetPerformanceRead] = Field(default_factory=list)
    student_rows: list[AssignmentStudentRowRead] = Field(default_factory=list)
