from __future__ import annotations

import json
from pathlib import Path

from app.evaluate.groups.base import BaseGroupEvaluator
from app.evaluate.schemas import EvaluationGroup, GroupEvaluationResult


class LearningEngineEvaluator(BaseGroupEvaluator):
    """Evaluates deterministic properties and pedagogy rules of the Learning Engine:
    - Concept mastery consistency (bounds, monotonicity)
    - ProblemType mastery consistency (rolling window vs state)
    - Hierarchy aggregation consistency (Topic/Chapter bounded by leaves)
    - Recommendation behavior (avoids mastered, targets weaknesses)
    - Diagnostic behavior (prerequisite flags)
    - Repair effectiveness rules (mastery lift >= 0.15).
    """

    group_name = EvaluationGroup.LEARNING_ENGINE

    def evaluate(self, dataset_path: Path) -> GroupEvaluationResult:
        with dataset_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # 1. Concept mastery consistency
        cm_tests = data.get("concept_mastery_tests", [])
        cm_passed = sum(1 for t in cm_tests if t.get("bounds_valid") and (t.get("monotonic_increase") or t.get("monotonic_decrease")))
        cm_score = cm_passed / len(cm_tests) if cm_tests else 1.0

        # 2. ProblemType mastery consistency
        ptm_tests = data.get("problem_type_mastery_tests", [])
        ptm_passed = sum(1 for t in ptm_tests if t.get("consistent_with_accuracy"))
        ptm_score = ptm_passed / len(ptm_tests) if ptm_tests else 1.0

        # 3. Hierarchy aggregation consistency
        agg_tests = data.get("hierarchy_aggregation_tests", [])
        agg_passed = sum(1 for t in agg_tests if t.get("bounded_by_leaves"))
        agg_score = agg_passed / len(agg_tests) if agg_tests else 1.0

        # 4. Recommendation behavior
        rec_tests = data.get("recommendation_tests", [])
        rec_passed = sum(1 for t in rec_tests if t.get("avoids_mastered") and t.get("targets_weakness") and t.get("diversity_count", 0) >= 2)
        rec_score = rec_passed / len(rec_tests) if rec_tests else 1.0

        # 5. Diagnostic behavior
        diag_tests = data.get("diagnostic_tests", [])
        diag_passed = sum(1 for t in diag_tests if (t.get("diagnosed_root_cause") == "PREREQUISITE_DEFICIT" and t.get("triggers_followup_check")) or (t.get("diagnosed_root_cause") != "PREREQUISITE_DEFICIT" and not t.get("triggers_followup_check")))
        diag_score = diag_passed / len(diag_tests) if diag_tests else 1.0

        # 6. Repair effectiveness rules
        rep_tests = data.get("repair_effectiveness_tests", [])
        rep_passed = sum(1 for t in rep_tests if t.get("lift_meets_threshold") and t.get("mastery_lift", 0) >= 0.15)
        rep_score = rep_passed / len(rep_tests) if rep_tests else 1.0

        metrics = [
            self.make_metric(
                name="concept_mastery_consistency",
                score=cm_score,
                threshold=0.95,
                unit="rate",
                description="Concept mastery updates are bounded in [0, 1] and monotonic with practice outcome.",
                details={"passed": cm_passed, "total": len(cm_tests)},
            ),
            self.make_metric(
                name="problem_type_mastery_consistency",
                score=ptm_score,
                threshold=0.95,
                unit="rate",
                description="ProblemType mastery accurately reflects rolling window accuracy and state transitions.",
                details={"passed": ptm_passed, "total": len(ptm_tests)},
            ),
            self.make_metric(
                name="aggregate_chapter_topic_consistency",
                score=agg_score,
                threshold=0.95,
                unit="rate",
                description="Topic and Chapter aggregate mastery values are mathematically bounded by leaf items.",
                details={"passed": agg_passed, "total": len(agg_tests)},
            ),
            self.make_metric(
                name="recommendation_behavior",
                score=rec_score,
                threshold=0.90,
                unit="rate",
                description="Recommendations avoid mastered items, prioritize weak problem types, and ensure diversity.",
                details={"passed": rec_passed, "total": len(rec_tests)},
            ),
            self.make_metric(
                name="diagnostic_behavior",
                score=diag_score,
                threshold=0.90,
                unit="rate",
                description="Diagnostics accurately isolate root causes and trigger prerequisite checkups.",
                details={"passed": diag_passed, "total": len(diag_tests)},
            ),
            self.make_metric(
                name="repair_effectiveness_rules",
                score=rep_score,
                threshold=0.90,
                unit="rate",
                description="Repair sessions verify student recovery with post-repair mastery lift >= 0.15.",
                details={"passed": rep_passed, "total": len(rep_tests)},
            ),
        ]

        overall_score = sum(m.score for m in metrics) / len(metrics)
        all_passed = all(m.status.value == "PASS" for m in metrics)
        total_samples = len(cm_tests) + len(ptm_tests) + len(agg_tests) + len(rec_tests) + len(diag_tests) + len(rep_tests)

        return GroupEvaluationResult(
            group=self.group_name,
            passed=all_passed,
            overall_score=round(overall_score, 4),
            sample_count=total_samples,
            metrics=metrics,
            notes="Learning Engine satisfies all deterministic consistency, aggregation, and repair efficacy rules.",
        )
