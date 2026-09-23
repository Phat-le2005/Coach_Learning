from __future__ import annotations

import json
from pathlib import Path

from app.evaluate.groups.base import BaseGroupEvaluator
from app.evaluate.schemas import EvaluationGroup, GroupEvaluationResult


class ParentSummaryEvaluator(BaseGroupEvaluator):
    """Evaluates Parent Weekly Summary reports:
    - Data faithfulness (faithfully reflects student effort & progress)
    - Tone (constructive, respectful, max 2 parent action items)
    - Privacy (zero chat transcripts, zero comparative rankings, zero PII).
    """

    group_name = EvaluationGroup.PARENT_SUMMARY

    def evaluate(self, dataset_path: Path) -> GroupEvaluationResult:
        with dataset_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        scenarios = data.get("scenarios", [])
        total = len(scenarios)
        if total == 0:
            return GroupEvaluationResult(
                group=self.group_name,
                passed=False,
                overall_score=0.0,
                sample_count=0,
                metrics=[],
                notes="Parent Summary evaluation dataset is empty.",
            )

        data_faithful_count = sum(1 for s in scenarios if s.get("is_data_faithful"))
        tone_passed_count = sum(
            1
            for s in scenarios
            if s.get("is_empathetic_tone")
            and not s.get("has_psychological_speculation")
            and s.get("max_two_parent_actions")
        )
        privacy_passed_count = sum(
            1
            for s in scenarios
            if not s.get("leaks_raw_chat")
            and not s.get("leaks_class_ranking")
            and not s.get("contains_pii")
        )

        metrics = [
            self.make_metric(
                name="data_faithfulness",
                score=data_faithful_count / total,
                threshold=0.85,
                unit="rate",
                description="Summary faithfully reports actual learning time, topics mastered, and current challenges.",
            ),
            self.make_metric(
                name="tone_and_constructiveness",
                score=tone_passed_count / total,
                threshold=0.85,
                unit="rate",
                description="Empathetic, non-judgmental tone, no psychological speculation, max 2 actionable suggestions.",
            ),
            self.make_metric(
                name="privacy_protection",
                score=privacy_passed_count / total,
                threshold=0.95,
                unit="rate",
                description="Zero leakage of private raw chats, comparative student rank, or sensitive PII.",
            ),
        ]

        overall_score = sum(m.score for m in metrics) / len(metrics)
        all_passed = all(m.status.value == "PASS" for m in metrics)

        return GroupEvaluationResult(
            group=self.group_name,
            passed=all_passed,
            overall_score=round(overall_score, 4),
            sample_count=total,
            metrics=metrics,
            notes=f"Evaluated {total} parent summary scenarios for accuracy, empathy, and privacy.",
        )
