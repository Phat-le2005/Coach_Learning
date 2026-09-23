from __future__ import annotations

import json
from pathlib import Path

from app.evaluate.groups.base import BaseGroupEvaluator
from app.evaluate.schemas import EvaluationGroup, GroupEvaluationResult


class AITutorEvaluator(BaseGroupEvaluator):
    """Evaluates AI Tutor quality across 7 pedagogical dimensions:
    - Correctness (mathematical precision)
    - Pedagogical quality (Socratic guiding)
    - Answer leakage (no premature disclosures)
    - Hallucination resistance
    - Source grounding
    - ProblemType relevance
    - Prerequisite diagnosis faithfulness.
    """

    group_name = EvaluationGroup.AI_TUTOR

    def evaluate(self, dataset_path: Path) -> GroupEvaluationResult:
        items = []
        with dataset_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    items.append(json.loads(line.strip()))

        total = len(items)
        if total == 0:
            return GroupEvaluationResult(
                group=self.group_name,
                passed=False,
                overall_score=0.0,
                sample_count=0,
                metrics=[],
                notes="AI Tutor evaluation dataset is empty.",
            )

        correct_count = sum(1 for x in items if x.get("is_correct"))
        socratic_count = sum(1 for x in items if x.get("is_socratic"))
        no_leak_count = sum(1 for x in items if not x.get("answer_leaked"))
        no_hallucination_count = sum(1 for x in items if not x.get("is_hallucinated"))
        grounded_count = sum(1 for x in items if x.get("is_grounded"))
        pt_relevant_count = sum(1 for x in items if x.get("is_pt_relevant"))
        prereq_faithful_count = sum(1 for x in items if x.get("prereq_faithful"))

        metrics = [
            self.make_metric(
                name="correctness",
                score=correct_count / total,
                threshold=0.85,
                unit="rate",
                description="Mathematical correctness and accuracy of reasoning steps.",
            ),
            self.make_metric(
                name="pedagogical_quality",
                score=socratic_count / total,
                threshold=0.75,
                unit="rate",
                description="Socratic pedagogical scaffolding rather than passive lecture dump.",
            ),
            self.make_metric(
                name="answer_leakage_prevention",
                score=no_leak_count / total,
                threshold=0.85,
                unit="rate",
                description="Resistance against prematurely revealing final answer on scaffolded levels.",
            ),
            self.make_metric(
                name="hallucination_resistance",
                score=no_hallucination_count / total,
                threshold=0.85,
                unit="rate",
                description="Absence of fabricated theorems, invalid rules, or imaginary curriculum codes.",
            ),
            self.make_metric(
                name="source_grounding",
                score=grounded_count / total,
                threshold=0.85,
                unit="rate",
                description="Degree of adherence to the provided question and compact student context.",
            ),
            self.make_metric(
                name="problem_type_relevance",
                score=pt_relevant_count / total,
                threshold=0.90,
                unit="rate",
                description="Focus stays relevant to the target ProblemType curriculum topic.",
            ),
            self.make_metric(
                name="prerequisite_diagnosis_faithfulness",
                score=prereq_faithful_count / total,
                threshold=0.85,
                unit="rate",
                description="Faithfulness and restraint in diagnosing prerequisite foundational gaps.",
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
            notes=f"Evaluated {total} interactive tutor turns across 7 quality dimensions.",
        )
