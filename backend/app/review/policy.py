from dataclasses import dataclass

from app.review.models import ReviewResult


@dataclass(frozen=True)
class ReviewThresholds:
    initial_interval_days: float = 1.0
    growth_factor: float = 2.0
    reduction_factor: float = 0.5
    min_interval_days: float = 1.0
    max_interval_days: float = 90.0
    good_score_threshold: float = 0.60
    concept_schedule_mastery_threshold: float = 0.80


class ReviewPolicy:
    def __init__(self, thresholds: ReviewThresholds | None = None) -> None:
        self.thresholds = thresholds or ReviewThresholds()

    def evaluate_performance(
        self, score: float | None, is_correct: bool | None
    ) -> ReviewResult:
        if score is not None:
            return (
                ReviewResult.GOOD
                if score >= self.thresholds.good_score_threshold
                else ReviewResult.POOR
            )
        if is_correct is not None:
            return ReviewResult.GOOD if is_correct else ReviewResult.POOR
        return ReviewResult.POOR

    def calculate_next_interval(
        self, current_interval: float, result: ReviewResult
    ) -> float:
        if result == ReviewResult.GOOD:
            expanded = current_interval * self.thresholds.growth_factor
            return round(min(self.thresholds.max_interval_days, expanded), 2)
        else:
            contracted = current_interval * self.thresholds.reduction_factor
            return round(max(self.thresholds.min_interval_days, contracted), 2)
