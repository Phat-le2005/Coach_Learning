from enum import StrEnum
from typing import Generic, TypeVar
from pydantic import BaseModel, Field


class AITaskType(StrEnum):
    TUTOR = "TUTOR"
    HINT = "HINT"
    OPEN_RESPONSE_EVALUATION = "OPEN_RESPONSE_EVALUATION"
    MISCONCEPTION_ANALYSIS = "MISCONCEPTION_ANALYSIS"
    RAG = "RAG"
    STUDY_PLAN_EXPLANATION = "STUDY_PLAN_EXPLANATION"
    TEACHER_COPILOT = "TEACHER_COPILOT"
    PARENT_SUMMARY = "PARENT_SUMMARY"
    QUESTION_GENERATION = "QUESTION_GENERATION"
    EXAM_ANALYSIS = "EXAM_ANALYSIS"
    ADMISSION_ASSISTANT = "ADMISSION_ASSISTANT"


class AIRoutingTier(StrEnum):
    FAST = "FAST"
    STANDARD = "STANDARD"
    REASONING = "REASONING"


DEFAULT_TASK_TIER_MAPPING: dict[AITaskType, AIRoutingTier] = {
    AITaskType.TUTOR: AIRoutingTier.FAST,
    AITaskType.HINT: AIRoutingTier.FAST,
    AITaskType.RAG: AIRoutingTier.FAST,
    AITaskType.OPEN_RESPONSE_EVALUATION: AIRoutingTier.STANDARD,
    AITaskType.MISCONCEPTION_ANALYSIS: AIRoutingTier.STANDARD,
    AITaskType.STUDY_PLAN_EXPLANATION: AIRoutingTier.STANDARD,
    AITaskType.TEACHER_COPILOT: AIRoutingTier.STANDARD,
    AITaskType.PARENT_SUMMARY: AIRoutingTier.STANDARD,
    AITaskType.QUESTION_GENERATION: AIRoutingTier.STANDARD,
    AITaskType.ADMISSION_ASSISTANT: AIRoutingTier.STANDARD,
    AITaskType.EXAM_ANALYSIS: AIRoutingTier.REASONING,
}


class AIRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class AIMessage(BaseModel):
    role: AIRole | str = AIRole.USER
    content: str


class AIResponse(BaseModel):
    content: str
    model: str
    tier: AIRoutingTier
    tokens_used: int | None = None
    latency_ms: float = 0.0


T = TypeVar("T", bound=BaseModel)


class AIStructuredResponse(BaseModel, Generic[T]):
    data: T
    raw_content: str
    model: str
    tier: AIRoutingTier
    latency_ms: float = 0.0


class AIStreamChunk(BaseModel):
    delta: str
    is_final: bool = False


class EmbeddingResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dimension: int
    latency_ms: float = 0.0
