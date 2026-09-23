from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
import uuid

from app.evaluate.groups.ai_tutor import AITutorEvaluator
from app.evaluate.groups.base import BaseGroupEvaluator
from app.evaluate.groups.learning_engine import LearningEngineEvaluator
from app.evaluate.groups.misconception import MisconceptionEvaluator
from app.evaluate.groups.parent_summary import ParentSummaryEvaluator
from app.evaluate.groups.rag import RAGEvaluator
from app.evaluate.groups.system_ai import SystemAIEvaluator
from app.evaluate.groups.teacher_copilot import TeacherCopilotEvaluator
from app.evaluate.reporters.json_reporter import JSONReporter
from app.evaluate.reporters.markdown_reporter import MarkdownReporter
from app.evaluate.schemas import EvaluationGroup, FullEvaluationReport, GroupEvaluationResult


class EvaluationRunner:
    """Orchestrates comprehensive multi-group evaluation across EduMS."""

    DATASET_MAPPING: dict[EvaluationGroup, str] = {
        EvaluationGroup.LEARNING_ENGINE: "learning_engine.json",
        EvaluationGroup.MISCONCEPTION: "misconceptions.jsonl",
        EvaluationGroup.RAG: "rag.json",
        EvaluationGroup.AI_TUTOR: "ai_tutor.jsonl",
        EvaluationGroup.TEACHER_COPILOT: "teacher_copilot.json",
        EvaluationGroup.PARENT_SUMMARY: "parent_summary.json",
        EvaluationGroup.SYSTEM_AI: "system_ai.json",
    }

    EVALUATOR_REGISTRY: dict[EvaluationGroup, type[BaseGroupEvaluator]] = {
        EvaluationGroup.LEARNING_ENGINE: LearningEngineEvaluator,
        EvaluationGroup.MISCONCEPTION: MisconceptionEvaluator,
        EvaluationGroup.RAG: RAGEvaluator,
        EvaluationGroup.AI_TUTOR: AITutorEvaluator,
        EvaluationGroup.TEACHER_COPILOT: TeacherCopilotEvaluator,
        EvaluationGroup.PARENT_SUMMARY: ParentSummaryEvaluator,
        EvaluationGroup.SYSTEM_AI: SystemAIEvaluator,
    }

    def __init__(
        self,
        data_dir: Path | str = "data/evaluation",
        output_dir: Path | str = "data/evaluation/reports",
    ) -> None:
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        selected_groups: Sequence[EvaluationGroup | str] | None = None,
    ) -> tuple[FullEvaluationReport, dict[str, Path]]:
        """Run evaluation for selected groups (or all groups by default)."""
        if selected_groups:
            normalized_groups = []
            for g in selected_groups:
                if isinstance(g, EvaluationGroup):
                    normalized_groups.append(g)
                else:
                    normalized_groups.append(EvaluationGroup(g.strip().upper()))
        else:
            normalized_groups = list(self.EVALUATOR_REGISTRY.keys())

        group_results: dict[str, GroupEvaluationResult] = {}
        total_samples = 0

        for group in normalized_groups:
            evaluator_cls = self.EVALUATOR_REGISTRY.get(group)
            if not evaluator_cls:
                raise ValueError(f"No evaluator registered for group: {group}")

            filename = self.DATASET_MAPPING.get(group)
            if not filename:
                raise ValueError(f"No dataset configured for group: {group}")

            dataset_path = self.data_dir / filename
            if not dataset_path.exists():
                raise FileNotFoundError(f"Evaluation dataset missing: {dataset_path}")

            evaluator = evaluator_cls()
            result = evaluator.evaluate(dataset_path)
            group_results[group.value] = result
            total_samples += result.sample_count

        overall_passed = all(r.passed for r in group_results.values())
        eval_id = f"eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        report = FullEvaluationReport(
            evaluation_id=eval_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            framework_version="v1.0",
            total_samples_evaluated=total_samples,
            overall_passed=overall_passed,
            groups=group_results,
            metadata={"data_dir": str(self.data_dir), "output_dir": str(self.output_dir)},
        )

        # Write reports
        json_path = self.output_dir / "evaluation_report.json"
        md_path = self.output_dir / "EVALUATION_REPORT.md"

        JSONReporter.write_report(report, json_path)
        MarkdownReporter.write_report(report, md_path)

        return report, {"json": json_path, "markdown": md_path}
