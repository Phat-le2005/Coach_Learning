from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExamAIInputContext(BaseModel):
    """Normalized context aggregating 6 deterministic data sources for AI exam explanation."""

    model_config = ConfigDict(from_attributes=True)

    attempt_id: UUID
    exam_id: UUID
    student_id: UUID
    student_name: str
    exam_title: str
    exam_type: str
    duration_minutes: int
    actual_duration_seconds: int

    # Scoring & performance summary
    score: float
    score_10: float
    total_points: float
    accuracy: float
    total_questions: int
    correct_count: int
    incorrect_count: int
    unanswered_count: int

    # 1. Chapter, Topic & ProblemType breakdown
    chapter_performance: list[dict[str, Any]] = Field(default_factory=list)
    topic_performance: list[dict[str, Any]] = Field(default_factory=list)
    problem_type_performance: list[dict[str, Any]] = Field(default_factory=list)

    # 2. Concept evidence & prerequisite signals
    concept_evidence: list[dict[str, Any]] = Field(default_factory=list)

    # 3. Prior mastery
    prior_problem_type_mastery: list[dict[str, Any]] = Field(default_factory=list)
    prior_concept_mastery: list[dict[str, Any]] = Field(default_factory=list)

    # 4. Known misconceptions
    known_misconceptions: list[dict[str, Any]] = Field(default_factory=list)

    # 5. Time & sequence behavior
    time_behavior: dict[str, Any] = Field(default_factory=dict)
    question_order_behavior: dict[str, Any] = Field(default_factory=dict)

    # 6. Detailed question responses (focusing on incorrect / unanswered)
    incorrect_questions_detail: list[dict[str, Any]] = Field(default_factory=list)

    # Deterministic flag for careless accusation guardrail
    has_strong_careless_evidence: bool = False
    valid_curriculum_nodes: set[str] = Field(default_factory=set)


class ExamAIStructuredOutput(BaseModel):
    """Raw structured output schema enforced on AI Gateway responses."""

    model_config = ConfigDict(from_attributes=True)

    strengths: list[str] = Field(
        default_factory=list,
        description="Các dạng bài, chủ đề hoặc khái niệm học sinh thể hiện tốt.",
    )
    weak_problem_types: list[str] = Field(
        default_factory=list,
        description="Các dạng bài còn yếu cần củng cố.",
    )
    possible_prerequisite_weaknesses: list[str] = Field(
        default_factory=list,
        description="Các lỗ hổng kiến thức tiền đề tiềm ẩn.",
    )
    recurring_errors: list[str] = Field(
        default_factory=list,
        description="Lỗi sai lặp lại hoặc các ngộ nhận đã biết.",
    )
    possible_time_management_issue: str = Field(
        ...,
        description="Đánh giá khả năng quản lý và phân bổ thời gian làm bài.",
    )
    review_priorities: list[str] = Field(
        default_factory=list,
        description="Thứ tự ưu tiên ôn tập cụ thể (tối đa 3-4 mục).",
    )
    exam_strategy_suggestions: list[str] = Field(
        default_factory=list,
        description="Chiến thuật làm bài thi đề xuất (2-3 gợi ý).",
    )
    student_friendly_summary: str = Field(
        ...,
        description="Lời nhắn tổng kết gửi học sinh bằng giọng văn tích cực, sư phạm.",
    )


class ExamAIExplanationRead(BaseModel):
    """Public read model for Exam AI Explanation."""

    model_config = ConfigDict(from_attributes=True)

    attempt_id: UUID
    exam_id: UUID
    student_id: UUID
    exam_title: str
    score: float
    score_10: float
    accuracy: float
    strengths: list[str]
    weak_problem_types: list[str]
    possible_prerequisite_weaknesses: list[str]
    recurring_errors: list[str]
    possible_time_management_issue: str
    review_priorities: list[str]
    exam_strategy_suggestions: list[str]
    student_friendly_summary: str
    has_strong_careless_evidence: bool = False
    is_fallback: bool = False
    generated_at: datetime
