from enum import StrEnum
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.recommendations.schemas import PriorityReasonCode


class LearningMixCategory(StrEnum):
    CURRENT_LEARNING = "CURRENT_LEARNING"
    WEAKNESS_REPAIR = "WEAKNESS_REPAIR"
    REVIEW_DUE = "REVIEW_DUE"
    OTHER = "OTHER"


class LearningMixConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    current_weight: float = Field(default=0.70, ge=0.0)
    weakness_weight: float = Field(default=0.20, ge=0.0)
    review_weight: float = Field(default=0.10, ge=0.0)

    @model_validator(mode="after")
    def check_weights_positive(self) -> "LearningMixConfig":
        total = self.current_weight + self.weakness_weight + self.review_weight
        if total <= 0:
            raise ValueError("At least one learning mix weight must be greater than zero.")
        return self

    @property
    def total_weight(self) -> float:
        return self.current_weight + self.weakness_weight + self.review_weight

    @property
    def current_ratio(self) -> float:
        return self.current_weight / self.total_weight

    @property
    def weakness_ratio(self) -> float:
        return self.weakness_weight / self.total_weight

    @property
    def review_ratio(self) -> float:
        return self.review_weight / self.total_weight

    def allocate_quotas(self, total_count: int) -> dict[LearningMixCategory, int]:
        if total_count <= 0:
            return {
                LearningMixCategory.CURRENT_LEARNING: 0,
                LearningMixCategory.WEAKNESS_REPAIR: 0,
                LearningMixCategory.REVIEW_DUE: 0,
            }

        # Hare-Niemeyer / largest remainder quota allocation
        exact_current = total_count * self.current_ratio
        exact_weakness = total_count * self.weakness_ratio
        exact_review = total_count * self.review_ratio

        floor_current = math.floor(exact_current)
        floor_weakness = math.floor(exact_weakness)
        floor_review = math.floor(exact_review)

        allocated = floor_current + floor_weakness + floor_review
        remainder = total_count - allocated

        remainders = [
            (exact_current - floor_current, LearningMixCategory.CURRENT_LEARNING),
            (exact_weakness - floor_weakness, LearningMixCategory.WEAKNESS_REPAIR),
            (exact_review - floor_review, LearningMixCategory.REVIEW_DUE),
        ]
        remainders.sort(key=lambda item: item[0], reverse=True)

        quotas = {
            LearningMixCategory.CURRENT_LEARNING: floor_current,
            LearningMixCategory.WEAKNESS_REPAIR: floor_weakness,
            LearningMixCategory.REVIEW_DUE: floor_review,
        }

        for i in range(remainder):
            cat = remainders[i % 3][1]
            quotas[cat] += 1

        return quotas


def categorize_priority_reason(reason_code: PriorityReasonCode) -> LearningMixCategory:
    if reason_code == PriorityReasonCode.CURRENT_LESSON:
        return LearningMixCategory.CURRENT_LEARNING
    if reason_code in {
        PriorityReasonCode.PREREQUISITE_REPAIR,
        PriorityReasonCode.WEAK_PROBLEM_TYPE,
        PriorityReasonCode.WEAK_CONCEPT,
        PriorityReasonCode.DIAGNOSTIC_FOLLOWUP,
    }:
        return LearningMixCategory.WEAKNESS_REPAIR
    if reason_code == PriorityReasonCode.REVIEW_DUE:
        return LearningMixCategory.REVIEW_DUE
    return LearningMixCategory.OTHER
