from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class PriorityReasonCode(StrEnum):
    VERIFIED_ROOT_CAUSE = "VERIFIED_ROOT_CAUSE"
    CURRENT_LESSON = "CURRENT_LESSON"
    WEAK_PROBLEM_TYPE = "WEAK_PROBLEM_TYPE"
    PREREQUISITE_REPAIR = "PREREQUISITE_REPAIR"
    WEAK_CONCEPT = "WEAK_CONCEPT"
    REVIEW_DUE = "REVIEW_DUE"
    DIFFICULTY_PROGRESSION = "DIFFICULTY_PROGRESSION"
    DIAGNOSTIC_FOLLOWUP = "DIAGNOSTIC_FOLLOWUP"


class PriorityTargetType(StrEnum):
    PROBLEM_TYPE = "PROBLEM_TYPE"
    CONCEPT = "CONCEPT"


@dataclass(frozen=True, slots=True)
class ActiveTeachingPlanContext:
    problem_type_ids: tuple[UUID, ...]
    priority_by_problem_type: dict[UUID, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AcademicGoalContext:
    target_problem_type_ids: tuple[UUID, ...] = ()
    exam_relevance_multiplier: float = 1.0


class LearningPriorityRead(BaseModel):
    target_type: PriorityTargetType
    problem_type_id: UUID | None = None
    concept_id: UUID | None = None
    reason_code: PriorityReasonCode
    priority_score: float = Field(ge=0.0)
    mastery_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    desired_difficulty: float = Field(ge=0.0, le=1.0)


class QuestionRecommendationRead(BaseModel):
    question_id: UUID
    target_problem_types: list[UUID]
    target_concepts: list[UUID]
    difficulty: float = Field(ge=0.0, le=1.0)
    reason_code: PriorityReasonCode

