from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.ai.types import AITaskType


class AIRequestLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None = None
    task: str
    provider: str
    model: str
    prompt_name: str
    prompt_version: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    success: bool
    error_type: str | None = None
    estimated_cost: float | None = None
    created_at: datetime


class DailyUsageMetric(BaseModel):
    date: str
    requests: int
    successful_requests: int
    failed_requests: int
    failure_rate: float
    average_latency_ms: float
    total_tokens: int
    estimated_cost: float


class TaskUsageMetric(BaseModel):
    task: str
    requests: int
    successful_requests: int
    failed_requests: int
    failure_rate: float
    average_latency_ms: float
    total_tokens: int
    average_tokens_per_task: float = 0.0
    estimated_cost: float
    average_cost_per_task: float = 0.0


class TaskTokenMetric(BaseModel):
    task: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    average_tokens_per_task: float = 0.0
    estimated_cost: float
    average_cost_per_task: float = 0.0


class StudentDailyUsageMetric(BaseModel):
    date: str
    unique_students: int
    total_requests: int
    average_requests_per_student: float


class AIUsageSummaryRead(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    failure_rate: float
    average_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_estimated_cost: float
    average_requests_per_student_per_day: float = 0.0
    requests_per_day: list[DailyUsageMetric] = Field(default_factory=list)
    requests_per_task: list[TaskUsageMetric] = Field(default_factory=list)
    tokens_per_task: list[TaskTokenMetric] = Field(default_factory=list)
    student_daily_usage: list[StudentDailyUsageMetric] = Field(default_factory=list)


class AIRequestLogPagination(BaseModel):
    items: list[AIRequestLogRead]
    total: int
    page: int
    page_size: int
    total_pages: int
