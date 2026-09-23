from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from app.evaluate.groups.base import BaseGroupEvaluator
from app.evaluate.schemas import EvaluationGroup, GroupEvaluationResult


class MisconceptionEvaluator(BaseGroupEvaluator):
    """Evaluates Misconception Detection performance:
    - Precision
    - Recall
    - Macro/Weighted F1
    - Full Confusion Matrix
    - Granular breakdown by Concept and ProblemType.
    """

    group_name = EvaluationGroup.MISCONCEPTION

    def evaluate(self, dataset_path: Path) -> GroupEvaluationResult:
        items = []
        with dataset_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    items.append(json.loads(line.strip()))

        if not items:
            return GroupEvaluationResult(
                group=self.group_name,
                passed=False,
                overall_score=0.0,
                sample_count=0,
                metrics=[],
                notes="Evaluation dataset is empty.",
            )

        # 1. Confusion Matrix & Label stats
        all_labels = sorted(list({item["expected_label"] for item in items} | {item["predicted_label"] for item in items}))
        confusion_matrix: dict[str, dict[str, int]] = {
            exp: {pred: 0 for pred in all_labels} for exp in all_labels
        }

        true_positives: dict[str, int] = defaultdict(int)
        false_positives: dict[str, int] = defaultdict(int)
        false_negatives: dict[str, int] = defaultdict(int)
        support: dict[str, int] = defaultdict(int)

        for item in items:
            exp = item["expected_label"]
            pred = item["predicted_label"]
            confusion_matrix[exp][pred] += 1
            support[exp] += 1

            if exp == pred:
                true_positives[exp] += 1
            else:
                false_positives[pred] += 1
                false_negatives[exp] += 1

        # Calculate per-class metrics
        precisions: dict[str, float] = {}
        recalls: dict[str, float] = {}
        f1s: dict[str, float] = {}

        for label in all_labels:
            tp = true_positives[label]
            fp = false_positives[label]
            fn = false_negatives[label]

            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            precisions[label] = p
            recalls[label] = r
            f1s[label] = self.calculate_f1(p, r)

        # Global metrics
        total_samples = len(items)
        macro_precision = sum(precisions.values()) / len(all_labels) if all_labels else 0.0
        macro_recall = sum(recalls.values()) / len(all_labels) if all_labels else 0.0
        macro_f1 = sum(f1s.values()) / len(all_labels) if all_labels else 0.0

        total_tp = sum(true_positives.values())
        micro_accuracy = total_tp / total_samples if total_samples > 0 else 0.0

        # Weighted F1
        weighted_f1 = sum(f1s[label] * support[label] for label in all_labels) / total_samples if total_samples > 0 else 0.0

        # 2. Concept Breakdown
        concept_breakdown: dict[str, dict[str, float]] = {}
        concept_items: dict[str, list[dict]] = defaultdict(list)
        for item in items:
            concept_items[item.get("concept", "UNKNOWN")].append(item)

        for c_code, c_list in concept_items.items():
            c_tp = sum(1 for x in c_list if x["expected_label"] == x["predicted_label"])
            c_acc = c_tp / len(c_list) if c_list else 0.0
            concept_breakdown[c_code] = {
                "accuracy": round(c_acc, 4),
                "count": len(c_list),
            }

        # 3. ProblemType Breakdown
        pt_breakdown: dict[str, dict[str, float]] = {}
        pt_items: dict[str, list[dict]] = defaultdict(list)
        for item in items:
            pt_items[item.get("problem_type", "UNKNOWN")].append(item)

        for pt_code, pt_list in pt_items.items():
            pt_tp = sum(1 for x in pt_list if x["expected_label"] == x["predicted_label"])
            pt_acc = pt_tp / len(pt_list) if pt_list else 0.0
            pt_breakdown[pt_code] = {
                "accuracy": round(pt_acc, 4),
                "count": len(pt_list),
            }

        metrics = [
            self.make_metric(
                name="precision_macro",
                score=macro_precision,
                threshold=0.80,
                unit="rate",
                description="Macro-averaged precision across all misconception classes.",
                details={"per_class_precision": {k: round(v, 4) for k, v in precisions.items()}},
            ),
            self.make_metric(
                name="recall_macro",
                score=macro_recall,
                threshold=0.75,
                unit="rate",
                description="Macro-averaged recall across all misconception classes.",
                details={"per_class_recall": {k: round(v, 4) for k, v in recalls.items()}},
            ),
            self.make_metric(
                name="f1_macro",
                score=macro_f1,
                threshold=0.75,
                unit="rate",
                description="Harmonic mean of macro-precision and macro-recall.",
            ),
            self.make_metric(
                name="f1_weighted",
                score=weighted_f1,
                threshold=0.80,
                unit="rate",
                description="Support-weighted F1 score across all classes.",
            ),
            self.make_metric(
                name="accuracy_overall",
                score=micro_accuracy,
                threshold=0.80,
                unit="rate",
                description="Overall classification accuracy on the evaluation dataset.",
                details={"correct_predictions": total_tp, "total_samples": total_samples},
            ),
        ]

        overall_score = weighted_f1
        all_passed = all(m.status.value == "PASS" for m in metrics)

        return GroupEvaluationResult(
            group=self.group_name,
            passed=all_passed,
            overall_score=round(overall_score, 4),
            sample_count=total_samples,
            metrics=metrics,
            breakdown={
                "by_concept": concept_breakdown,
                "by_problem_type": pt_breakdown,
            },
            confusion_matrix=confusion_matrix,
            notes=f"Evaluated {total_samples} diagnosis samples across {len(all_labels)} classes.",
        )
