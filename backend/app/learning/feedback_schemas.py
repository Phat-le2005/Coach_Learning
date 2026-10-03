from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.knowledge_gap.models import RootCauseVerificationTargetType
from app.learning.feedback_models import LearningFeedbackAction, LearningFeedbackReasonCode
from app.questions.models import QuestionType
from app.recommendations.schemas import PriorityReasonCode, PriorityTargetType


class LearningFeedbackTargetInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: RootCauseVerificationTargetType | None = None
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    name: str | None = None
    code: str | None = None


class LearningFeedbackReviewInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schedule_id: UUID | None = None
    next_review_at: datetime | None = None


class LearningFeedbackQuestionOptionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    content: str
    order_index: int


class LearningFeedbackQuestionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content: str
    question_type: QuestionType
    difficulty: float
    options: list[LearningFeedbackQuestionOptionInfo] = []


class LearningFeedbackNextLearningInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_type: PriorityTargetType | None = None
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    reason_code: PriorityReasonCode | None = None
    recommended_question_id: UUID | None = None
    recommended_question: LearningFeedbackQuestionInfo | None = None


class LearningFeedbackRetryInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    allowed: bool
    max_cycles: int
    current_cycle: int


class LearningFeedbackDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    adaptive_repair_session_id: UUID
    action: LearningFeedbackAction
    reason_code: LearningFeedbackReasonCode
    repair_cycle_index: int
    target: LearningFeedbackTargetInfo | None = None
    review: LearningFeedbackReviewInfo | None = None
    next_learning: LearningFeedbackNextLearningInfo | None = None
    retry: LearningFeedbackRetryInfo
    created_at: datetime
