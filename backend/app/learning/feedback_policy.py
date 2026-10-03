from dataclasses import dataclass

from app.learning.feedback_models import (
    LearningFeedbackAction,
    LearningFeedbackReasonCode,
)
from app.repair.models import AdaptiveRepairOutcome


@dataclass(frozen=True, slots=True)
class LearningFeedbackPolicy:
    max_cycles: int = 2
    resolved_review_interval_days: float = 2.0
    retry_difficulty_offset: float = 0.10
    min_difficulty: float = 0.20
    max_difficulty: float = 0.80

    def retry_initial_difficulty(self, previous_difficulty: float) -> float:
        return round(
            max(self.min_difficulty, min(self.max_difficulty, previous_difficulty - self.retry_difficulty_offset)),
            2,
        )

    def decide(
        self,
        *,
        outcome: AdaptiveRepairOutcome,
        repair_cycle_index: int,
        has_fresh_question: bool,
        has_current_lesson: bool,
        has_other_learning_priority: bool,
    ) -> tuple[LearningFeedbackAction, LearningFeedbackReasonCode, bool]:
        """Deterministic policy resolution mapping repair outcome to next learning action."""
        if outcome == AdaptiveRepairOutcome.RESOLVED:
            if has_current_lesson:
                return (
                    LearningFeedbackAction.RETURN_TO_CURRENT_LEARNING,
                    LearningFeedbackReasonCode.CURRENT_LESSON_AVAILABLE,
                    False,
                )
            if has_other_learning_priority:
                return (
                    LearningFeedbackAction.RETURN_TO_CURRENT_LEARNING,
                    LearningFeedbackReasonCode.REPAIR_RESOLVED_REVIEW_SCHEDULED,
                    False,
                )
            return (
                LearningFeedbackAction.NO_ACTIVE_LEARNING,
                LearningFeedbackReasonCode.NO_ACTIVE_TEACHING_PLAN,
                False,
            )

        if outcome == AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE:
            if repair_cycle_index < self.max_cycles:
                if has_fresh_question:
                    return (
                        LearningFeedbackAction.RETRY_REPAIR,
                        LearningFeedbackReasonCode.REPAIR_NEEDS_MORE_RETRY_AVAILABLE,
                        True,
                    )
                return (
                    LearningFeedbackAction.QUESTION_SUPPLY_GAP,
                    LearningFeedbackReasonCode.REPAIR_NEEDS_MORE_NO_QUESTIONS,
                    False,
                )
            return (
                LearningFeedbackAction.COLLECT_MORE_EVIDENCE,
                LearningFeedbackReasonCode.REPAIR_RETRY_LIMIT_REACHED,
                False,
            )

        if outcome == AdaptiveRepairOutcome.BANK_EXHAUSTED:
            return (
                LearningFeedbackAction.QUESTION_SUPPLY_GAP,
                LearningFeedbackReasonCode.REPAIR_BANK_EXHAUSTED,
                False,
            )

        raise ValueError(f"Unsupported repair outcome for feedback decision: {outcome}")
