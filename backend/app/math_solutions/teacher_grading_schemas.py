from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GradingQueueItem(BaseModel):
    attempt_id: UUID
    student_id: UUID
    student_name: str
    assignment_id: UUID | None = None
    assignment_title: str | None = None
    classroom_id: UUID | None = None
    classroom_name: str | None = None
    question_id: UUID | None = None
    question_title: str | None = None
    submitted_at: datetime | None = None
    status: str  # "PENDING_REVIEW", "PROVISIONAL_AI", "EVALUATED", "OVERRIDDEN"
    provisional_score: float | None = None
    final_score: float | None = None
    is_correct: bool | None = None
    step_count: int = 0
    unverified_steps_count: int = 0
    needs_teacher_review: bool = False
    review_source: str | None = None
    decision_id: UUID | None = None


class PaginatedGradingQueue(BaseModel):
    items: list[GradingQueueItem]
    total: int
    page: int
    size: int
    total_pages: int
    pending_count: int = 0


class StepEvaluationDetail(BaseModel):
    math_validity: str
    score: float | None = None
    confidence: float | None = None
    error_detected: bool | None = None
    error_description: str | None = None


class StepDetail(BaseModel):
    step_id: UUID
    step_index: int
    step_type: str
    content_latex: str | None = None
    explanation_text: str | None = None
    evaluation: StepEvaluationDetail | None = None


class OverrideHistoryItem(BaseModel):
    override_id: UUID
    override_version: int
    previous_score: float
    new_score: float
    previous_is_correct: bool
    new_is_correct: bool
    reason: str
    created_at: datetime


class AttemptGradingDetail(BaseModel):
    attempt_id: UUID
    student_id: UUID
    student_name: str
    assignment_id: UUID | None = None
    assignment_title: str | None = None
    classroom_id: UUID | None = None
    classroom_name: str | None = None
    question_id: UUID | None = None
    question_title: str | None = None
    question_latex: str | None = None
    submitted_at: datetime | None = None
    steps: list[StepDetail] = []
    status: str
    provisional_score: float | None = None
    final_score: float | None = None
    is_correct: bool | None = None
    decision_source: str | None = None
    decision_id: UUID | None = None
    sync_status: str = "SYNCED"
    overrides: list[OverrideHistoryItem] = []


class BatchApproveRequest(BaseModel):
    attempt_ids: list[UUID] = Field(..., min_length=1, max_length=50)
    note: str | None = None


class BatchApproveResultItem(BaseModel):
    attempt_id: UUID
    status: str  # "APPROVED", "FAILED"
    score: float | None = None
    message: str | None = None


class BatchApproveResponse(BaseModel):
    approved_count: int
    failed_count: int
    results: list[BatchApproveResultItem]


class TeacherOverrideRequest(BaseModel):
    new_score: float = Field(..., ge=0.0, le=1.0)
    new_is_correct: bool
    reason: str = Field(..., min_length=1, max_length=500)


class TeacherOverrideResponse(BaseModel):
    attempt_id: UUID
    decision_id: UUID
    override_id: UUID
    previous_score: float
    new_score: float
    new_is_correct: bool
    sync_status: str = "SYNCED"


class RetrySyncResponse(BaseModel):
    attempt_id: UUID
    student_id: UUID
    sync_status: str = "SYNCED"
    affected_skills: int
    recalculated_at: datetime
