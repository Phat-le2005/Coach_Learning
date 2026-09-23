from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ParentStudentSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: UUID
    student_name: str
    grade_level: int
    relationship_type: str
    school_name: str | None = None
    overall_learning_trend: str
    weekly_study_time_minutes: int
    active_alerts_count: int


class ParentSubjectProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_id: UUID
    subject_name: str
    mastery_score: float
    completed_topics_count: int
    total_topics_count: int


class ParentChapterProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chapter_id: UUID
    chapter_name: str
    subject_name: str
    mastery_score: float
    status: str


class ParentTopicProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic_id: UUID
    topic_name: str
    chapter_name: str
    mastery_score: float


class ParentMajorWeakAreaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    problem_type_id: UUID
    problem_type_name: str
    subject_name: str
    mastery_score: float
    parent_friendly_message: str
    related_concept_name: str | None = None
    attempt_count: int


class ParentStudyPlanCompletionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_tasks: int
    completed_tasks: int
    completion_rate: float


class ParentInterventionAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_code: str
    severity: str
    title: str
    message: str
    suggested_action_for_parent: str


class ParentExamTrendItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    date: datetime
    score: float
    total_questions: int
    assessment_type: str
    trend_direction: str = "STABLE"


class ParentStudentProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: UUID
    student_name: str
    grade_level: int
    relationship_type: str
    subject_progress: list[ParentSubjectProgressRead] = Field(default_factory=list)
    chapter_progress: list[ParentChapterProgressRead] = Field(default_factory=list)
    topic_progress: list[ParentTopicProgressRead] = Field(default_factory=list)
    major_weak_areas: list[ParentMajorWeakAreaRead] = Field(default_factory=list)
    study_plan_completion: ParentStudyPlanCompletionRead
    exam_trend: list[ParentExamTrendItem] = Field(default_factory=list)
    important_intervention_alerts: list[ParentInterventionAlertRead] = Field(default_factory=list)
    overall_learning_trend: str
    trend_description: str


class DailyStudyTimeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    day_of_week: str
    study_time_minutes: int
    questions_attempted: int


class ParentWeeklyDataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: UUID
    student_name: str
    week_start_date: date
    week_end_date: date
    total_study_time_minutes: int
    daily_study_time: list[DailyStudyTimeItem] = Field(default_factory=list)
    tasks_completed_this_week: int
    tasks_total_this_week: int
    weekly_completion_rate: float
    exam_trend: list[ParentExamTrendItem] = Field(default_factory=list)
    overall_weekly_summary: str


class ParentWeeklyAIInput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_name: str
    grade_level: int
    week_start_date: date
    week_end_date: date
    weekly_learning_time_minutes: int
    active_days_count: int
    study_plan_total_tasks: int
    study_plan_completed_tasks: int
    study_plan_completion_rate: float
    chapter_topic_trends: list[dict[str, Any]] = Field(default_factory=list)
    major_weak_problem_types: list[dict[str, Any]] = Field(default_factory=list)
    persistent_prerequisite_issues: list[dict[str, Any]] = Field(default_factory=list)
    important_intervention_alerts: list[dict[str, Any]] = Field(default_factory=list)
    exam_trend: list[dict[str, Any]] = Field(default_factory=list)


class ParentWeeklyAIOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    progress: str = Field(
        ...,
        description="Tiến độ và điểm tích cực trong tuần qua (thời lượng học, bài tập hoàn thành, sự chăm chỉ)",
    )
    current_challenge: str = Field(
        ...,
        description="Khó khăn hiện tại mà con đang gặp phải (ở cấp độ dạng bài/chủ đề hoặc kiến thức nền tảng)",
    )
    next_week: str = Field(
        ...,
        description="Định hướng và mục tiêu học tập trọng tâm trong tuần tới",
    )
    how_parent_can_help: list[str] = Field(
        default_factory=list,
        max_length=2,
        description="Tối đa 2 gợi ý hành động thiết thực cho phụ huynh đồng hành cùng con",
    )


class ParentWeeklyAISummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: UUID
    student_name: str
    week_start_date: date
    week_end_date: date
    progress: str
    current_challenge: str
    next_week: str
    how_parent_can_help: list[str] = Field(default_factory=list)
    is_fallback: bool = False
    generated_at: datetime
