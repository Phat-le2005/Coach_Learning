from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.exams.models import ExamAttemptStatus, ExamStatus, ExamType
from app.questions.models import CognitiveLevel, QuestionType


# --------------------------------------------------------------------------
# Blueprint Schemas
# --------------------------------------------------------------------------

class ExamBlueprintRule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chapter_id: UUID | None = None
    topic_id: UUID | None = None
    problem_type_id: UUID | None = None
    difficulty_min: float | None = None
    difficulty_max: float | None = None
    cognitive_level: CognitiveLevel | None = None
    question_type: QuestionType | None = None
    count: int = Field(gt=0, default=1)
    points_per_question: float = Field(gt=0, default=1.0)


class ExamBlueprintConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rules: list[ExamBlueprintRule] = Field(default_factory=list)
    shuffle_questions: bool = False


# --------------------------------------------------------------------------
# Exam CRUD Schemas
# --------------------------------------------------------------------------

class ExamCreate(BaseModel):
    subject_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    duration_minutes: int = Field(gt=0, default=90)
    exam_type: ExamType = ExamType.REAL_SIMULATION
    total_points: float = Field(gt=0, default=10.0)
    passing_score: float | None = None
    blueprint_config: ExamBlueprintConfig | None = None


class ExamUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    duration_minutes: int | None = Field(None, gt=0)
    status: ExamStatus | None = None
    exam_type: ExamType | None = None
    total_points: float | None = Field(None, gt=0)
    passing_score: float | None = None
    blueprint_config: ExamBlueprintConfig | None = None


class ExamSectionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    order_index: int = Field(ge=0, default=0)
    duration_minutes: int | None = Field(None, gt=0)
    section_points: float | None = Field(None, gt=0)
    blueprint_config: ExamBlueprintConfig | None = None


class ExamQuestionCreate(BaseModel):
    question_id: UUID
    section_id: UUID | None = None
    order_index: int = Field(ge=0, default=0)
    points: float = Field(gt=0, default=1.0)


class ExamOptionSanitizedRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    content: str
    order_index: int


class ExamQuestionSanitizedRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID  # ExamQuestion.id
    question_id: UUID
    section_id: UUID | None = None
    order_index: int
    points: float
    content: str
    question_type: QuestionType
    difficulty: float
    cognitive_level: CognitiveLevel | None = None
    options: list[ExamOptionSanitizedRead] = Field(default_factory=list)


class ExamSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    exam_id: UUID
    title: str
    description: str | None = None
    order_index: int
    duration_minutes: int | None = None
    section_points: float | None = None
    blueprint_config: dict[str, Any] | None = None


class ExamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_id: UUID
    title: str
    description: str | None = None
    duration_minutes: int
    status: ExamStatus
    exam_type: ExamType
    total_questions: int
    total_points: float
    passing_score: float | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class ExamDetailRead(ExamRead):
    sections: list[ExamSectionRead] = Field(default_factory=list)
    questions: list[ExamQuestionSanitizedRead] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Student Simulation Flow Schemas
# --------------------------------------------------------------------------

class ExamAttemptStartRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_id: UUID
    exam_id: UUID
    exam_title: str
    exam_type: ExamType
    duration_minutes: int
    started_at: datetime
    expires_at: datetime
    time_remaining_seconds: int
    total_questions: int
    total_points: float
    sections: list[ExamSectionRead] = Field(default_factory=list)
    questions: list[ExamQuestionSanitizedRead] = Field(default_factory=list)


class ExamResponseSubmitRequest(BaseModel):
    question_id: UUID
    student_answer: str
    selected_option_id: UUID | None = None
    response_time_seconds: float | None = Field(None, ge=0)


class ExamResponseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_id: UUID
    question_id: UUID
    student_answer: str | None = None
    selected_option_id: UUID | None = None
    is_correct: bool | None = None
    score_awarded: float | None = None
    response_time_seconds: float | None = None
    answered_at: datetime | None = None
    order_answered: int = 0


class ExamAttemptStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_id: UUID
    exam_id: UUID
    status: ExamAttemptStatus
    started_at: datetime
    submitted_at: datetime | None = None
    duration_seconds: int
    time_remaining_seconds: int
    answered_count: int
    total_questions: int
    responses: list[ExamResponseRead] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Exam Analytics & Metrics Schemas
# --------------------------------------------------------------------------

class ExamChapterPerformance(BaseModel):
    chapter_id: UUID
    chapter_name: str
    total_questions: int
    correct_count: int
    accuracy: float
    score_earned: float
    max_score: float


class ExamTopicPerformance(BaseModel):
    topic_id: UUID
    topic_name: str
    chapter_name: str
    total_questions: int
    correct_count: int
    accuracy: float
    score_earned: float
    max_score: float


class ExamProblemTypePerformance(BaseModel):
    problem_type_id: UUID
    problem_type_name: str
    topic_name: str
    total_questions: int
    correct_count: int
    accuracy: float
    score_earned: float
    max_score: float


class ExamConceptEvidence(BaseModel):
    concept_id: UUID
    concept_name: str
    is_prerequisite: bool
    questions_tested: int
    correct_count: int
    accuracy: float
    diagnostic_signal: str  # "STRONG", "NEEDS_PRACTICE", "PREREQUISITE_GAP"


class ExamDifficultyPerformance(BaseModel):
    difficulty_level: str  # "EASY", "MEDIUM", "HARD"
    total_questions: int
    correct_count: int
    accuracy: float
    score_earned: float
    max_score: float


class ExamTimePerQuestion(BaseModel):
    average_seconds_per_question: float
    total_time_seconds: int
    fastest_question_id: UUID | None = None
    slowest_question_id: UUID | None = None


class ExamAccuracyOverTime(BaseModel):
    first_half_accuracy: float
    second_half_accuracy: float
    time_pressure_detected: bool
    summary: str


class ExamQuestionOrderBehavior(BaseModel):
    is_sequential: bool
    skip_count: int
    answered_order_sequence: list[int] = Field(default_factory=list)
    behavior_summary: str


class ExamAnalyticsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_id: UUID
    exam_id: UUID
    student_id: UUID
    exam_title: str
    exam_type: ExamType
    duration_seconds: int
    score: float
    score_10: float
    total_points: float
    accuracy: float
    total_questions: int
    correct_count: int
    incorrect_count: int
    unanswered_count: int
    unanswered_question_ids: list[UUID] = Field(default_factory=list)
    chapter_performance: list[ExamChapterPerformance] = Field(default_factory=list)
    topic_performance: list[ExamTopicPerformance] = Field(default_factory=list)
    problem_type_performance: list[ExamProblemTypePerformance] = Field(default_factory=list)
    concept_evidence: list[ExamConceptEvidence] = Field(default_factory=list)
    difficulty_performance: list[ExamDifficultyPerformance] = Field(default_factory=list)
    time_per_question: ExamTimePerQuestion
    accuracy_over_time: ExamAccuracyOverTime
    question_order_behavior: ExamQuestionOrderBehavior


class ExamAttemptResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_id: UUID
    exam_id: UUID
    student_id: UUID
    status: ExamAttemptStatus
    score: float
    score_10: float
    total_points: float
    accuracy: float
    duration_seconds: int
    analytics: ExamAnalyticsRead
    official_mastery_updated: bool = False
