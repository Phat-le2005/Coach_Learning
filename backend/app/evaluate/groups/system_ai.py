from __future__ import annotations

import json
from pathlib import Path

from app.evaluate.groups.base import BaseGroupEvaluator
from app.evaluate.schemas import EvaluationGroup, GroupEvaluationResult


class SystemAIEvaluator(BaseGroupEvaluator):
    """Evaluates System AI operational metrics:
    - Latency (average, p50, p95)
    - Token usage (average prompt, completion, total)
    - Failure rate (error percentage, rate limit handling)
    - Cost estimate (average cost per task in USD).
    """

    group_name = EvaluationGroup.SYSTEM_AI

    def evaluate(self, dataset_path: Path) -> GroupEvaluationResult:
        with dataset_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        logs = data.get("benchmark_logs", [])
        total = len(logs)
        if total == 0:
            return GroupEvaluationResult(
                group=self.group_name,
                passed=False,
                overall_score=0.0,
                sample_count=0,
                metrics=[],
                notes="System AI evaluation dataset is empty.",
            )

        latencies = sorted([log["latency_ms"] for log in logs])
        avg_latency = sum(latencies) / total
        p50_latency = latencies[int(total * 0.50)]
        p95_latency = latencies[min(int(total * 0.95), total - 1)]

        prompt_tokens = [log.get("prompt_tokens", 0) for log in logs]
        comp_tokens = [log.get("completion_tokens", 0) for log in logs]
        total_tokens = [log.get("total_tokens", 0) for log in logs]

        avg_prompt_tokens = sum(prompt_tokens) / total
        avg_comp_tokens = sum(comp_tokens) / total
        avg_total_tokens = sum(total_tokens) / total

        error_count = sum(1 for log in logs if log.get("is_error"))
        failure_rate = error_count / total

        costs = [log.get("estimated_cost_usd", 0.0) for log in logs]
        avg_cost = sum(costs) / total

        metrics = [
            self.make_metric(
                name="average_latency",
                score=avg_latency,
                threshold=800.0,
                unit="ms",
                description="Average end-to-end response time across all task types.",
                higher_is_better=False,
                details={"p50_ms": p50_latency, "p95_ms": p95_latency, "max_ms": latencies[-1]},
            ),
            self.make_metric(
                name="p95_latency",
                score=p95_latency,
                threshold=1200.0,
                unit="ms",
                description="95th percentile response time.",
                higher_is_better=False,
            ),
            self.make_metric(
                name="average_token_consumption",
                score=avg_total_tokens,
                threshold=1500.0,
                unit="tokens",
                description="Average total token consumption per request.",
                higher_is_better=False,
                details={"avg_prompt_tokens": round(avg_prompt_tokens, 1), "avg_completion_tokens": round(avg_comp_tokens, 1)},
            ),
            self.make_metric(
                name="system_resilience_rate",
                score=1.0 - failure_rate,
                threshold=0.75,
                unit="rate",
                description="Success rate across all normal and rate-limited requests.",
                details={"failure_count": error_count, "total_requests": total},
            ),
            self.make_metric(
                name="average_cost_per_task",
                score=avg_cost,
                threshold=0.001,
                unit="USD",
                description="Estimated average monetary expenditure per invocation.",
                higher_is_better=False,
            ),
        ]

        all_passed = all(m.status.value == "PASS" for m in metrics)
        overall_score = 1.0 - failure_rate

        return GroupEvaluationResult(
            group=self.group_name,
            passed=all_passed,
            overall_score=round(overall_score, 4),
            sample_count=total,
            metrics=metrics,
            notes=f"Processed {total} system telemetry logs. Average latency: {round(avg_latency, 1)}ms, average cost: ${round(avg_cost, 6)}.",
        )
