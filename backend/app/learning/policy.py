from dataclasses import dataclass
from uuid import UUID

from app.learning.models import ConceptSignalLevel, QuickCheckVerdict


@dataclass(frozen=True)
class QuickCheckThresholds:
    min_questions: int = 3
    max_questions: int = 7
    problem_type_pass_score: float = 0.60
    problem_type_weak_score: float = 0.40
    understood_ratio: float = 0.65
    weak_ratio: float = 0.50
    concept_strong_score: float = 0.80
    concept_adequate_score: float = 0.50


class QuickCheckPolicy:
    def __init__(self, thresholds: QuickCheckThresholds | None = None) -> None:
        self.thresholds = thresholds or QuickCheckThresholds()

    def evaluate_problem_type(self, total: int, correct: int, score: float) -> QuickCheckVerdict:
        if total == 0:
            return QuickCheckVerdict.WEAK
        if score >= self.thresholds.problem_type_pass_score:
            return QuickCheckVerdict.UNDERSTOOD
        if score >= self.thresholds.problem_type_weak_score:
            return QuickCheckVerdict.PARTIAL
        return QuickCheckVerdict.WEAK

    def evaluate_concept_signal(self, total: int, correct: int, score: float) -> ConceptSignalLevel:
        if total == 0:
            return ConceptSignalLevel.NEEDS_ATTENTION
        if score >= self.thresholds.concept_strong_score:
            return ConceptSignalLevel.STRONG
        if score >= self.thresholds.concept_adequate_score:
            return ConceptSignalLevel.ADEQUATE
        return ConceptSignalLevel.NEEDS_ATTENTION

    def evaluate_verdict(
        self,
        problem_type_results: list[dict],
        core_problem_type_ids: set[UUID],
    ) -> QuickCheckVerdict:
        if not problem_type_results:
            return QuickCheckVerdict.WEAK

        total_pts = len(problem_type_results)
        passed_pts = sum(
            1 for pt in problem_type_results if pt["status"] == QuickCheckVerdict.UNDERSTOOD
        )

        has_weak_core = any(
            pt["status"] == QuickCheckVerdict.WEAK
            for pt in problem_type_results
            if pt["problem_type_id"] in core_problem_type_ids
        )

        pass_ratio = passed_pts / total_pts if total_pts > 0 else 0.0

        if has_weak_core or pass_ratio < self.thresholds.weak_ratio:
            return QuickCheckVerdict.WEAK

        if pass_ratio >= self.thresholds.understood_ratio:
            return QuickCheckVerdict.UNDERSTOOD

        return QuickCheckVerdict.PARTIAL
