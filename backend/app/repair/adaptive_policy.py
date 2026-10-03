from dataclasses import dataclass

from app.knowledge_gap.models import RootCauseVerificationTargetType
from app.repair.models import AdaptiveRepairPhase


@dataclass(frozen=True, slots=True)
class AdaptiveRepairPolicy:
    min_difficulty: float = 0.20
    max_difficulty: float = 0.80
    correct_step: float = 0.10
    correct_with_hint_step: float = 0.05
    wrong_step: float = 0.10
    wrong_with_hint_step: float = 0.15
    concept_exit_difficulty: float = 0.50
    problem_type_exit_difficulty: float = 0.60
    max_questions: int = 8
    min_attempts_for_final: int = 3
    min_attempts_for_resolution: int = 4
    required_correct_streak: int = 2
    recent_window: int = 3
    recent_score_threshold: float = 0.67

    def clamp(self, value: float) -> float:
        return round(min(self.max_difficulty, max(self.min_difficulty, value)), 2)

    def initial_difficulty(self, target_type: RootCauseVerificationTargetType, verification_average: float | None) -> float:
        signal = 0.50 if verification_average is None else verification_average
        if target_type == RootCauseVerificationTargetType.PROBLEM_TYPE:
            value = 0.40 if signal <= 0.25 else 0.45 if signal <= 0.50 else 0.50
        else:
            value = 0.30 if signal <= 0.25 else 0.35 if signal <= 0.50 else 0.40
        return self.clamp(value)

    def exit_difficulty(self, target_type: RootCauseVerificationTargetType) -> float:
        return self.problem_type_exit_difficulty if target_type == RootCauseVerificationTargetType.PROBLEM_TYPE else self.concept_exit_difficulty

    @staticmethod
    def initial_phase(verification_average: float | None) -> AdaptiveRepairPhase:
        return AdaptiveRepairPhase.FOUNDATION if verification_average is None or verification_average <= 0.50 else AdaptiveRepairPhase.TARGET_PRACTICE

    def adjusted_difficulty(self, current: float, *, is_correct: bool, hint_count: int) -> float:
        if is_correct:
            return self.clamp(current + (self.correct_with_hint_step if hint_count > 0 else self.correct_step))
        return self.clamp(current - (self.wrong_with_hint_step if hint_count > 0 else self.wrong_step))

    def ready_for_final(self, *, attempted_count: int, consecutive_correct: int, current_difficulty: float, target_exit_difficulty: float, recent_scores: list[float]) -> bool:
        return (
            attempted_count >= self.min_attempts_for_final
            and consecutive_correct >= self.required_correct_streak
            and current_difficulty >= target_exit_difficulty - 0.10
            and len(recent_scores) >= self.recent_window
            and sum(recent_scores[-self.recent_window:]) / self.recent_window >= self.recent_score_threshold
        )

    def can_resolve(self, *, attempted_count: int, recent_scores: list[float], final_correct: bool) -> bool:
        return (
            final_correct
            and attempted_count >= self.min_attempts_for_resolution
            and len(recent_scores) >= self.recent_window
            and sum(recent_scores[-self.recent_window:]) / self.recent_window >= self.recent_score_threshold
        )
