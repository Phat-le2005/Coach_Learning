from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.evaluate.schemas import EvaluationGroup, GroupEvaluationResult, MetricScore, MetricStatus


class BaseGroupEvaluator(ABC):
    """Abstract base class for domain evaluation groups."""

    group_name: EvaluationGroup

    @abstractmethod
    def evaluate(self, dataset_path: Path) -> GroupEvaluationResult:
        """Execute evaluation over the group's evaluation dataset."""
        ...

    @staticmethod
    def calculate_f1(precision: float, recall: float) -> float:
        """Calculate harmonic mean F1 score."""
        if precision + recall == 0.0:
            return 0.0
        return 2 * (precision * recall) / (precision + recall)

    @staticmethod
    def make_metric(
        name: str,
        score: float,
        threshold: float,
        unit: str = "",
        description: str = "",
        higher_is_better: bool = True,
        details: dict[str, Any] | None = None,
    ) -> MetricScore:
        """Helper to create a MetricScore with automatic status assignment."""
        passed = (score >= threshold) if higher_is_better else (score <= threshold)
        status = MetricStatus.PASS if passed else MetricStatus.FAIL
        return MetricScore(
            name=name,
            score=round(score, 4),
            status=status,
            threshold=threshold,
            unit=unit,
            description=description,
            details=details or {},
        )
