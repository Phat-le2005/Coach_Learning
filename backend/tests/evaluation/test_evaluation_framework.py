from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.evaluate.groups.ai_tutor import AITutorEvaluator
from app.evaluate.groups.learning_engine import LearningEngineEvaluator
from app.evaluate.groups.misconception import MisconceptionEvaluator
from app.evaluate.groups.parent_summary import ParentSummaryEvaluator
from app.evaluate.groups.rag import RAGEvaluator
from app.evaluate.groups.system_ai import SystemAIEvaluator
from app.evaluate.groups.teacher_copilot import TeacherCopilotEvaluator
from app.evaluate.runner import EvaluationRunner
from app.evaluate.schemas import EvaluationGroup, MetricStatus


DATA_DIR = Path("data/evaluation")


# --------------------------------------------------------------------------
# 1. Learning Engine Evaluator Tests
# --------------------------------------------------------------------------


def test_learning_engine_evaluator() -> None:
    evaluator = LearningEngineEvaluator()
    dataset_path = DATA_DIR / "learning_engine.json"
    result = evaluator.evaluate(dataset_path)

    assert result.group == EvaluationGroup.LEARNING_ENGINE
    assert result.passed is True
    assert result.overall_score >= 0.95
    assert result.sample_count > 10

    metric_names = {m.name for m in result.metrics}
    expected_names = {
        "concept_mastery_consistency",
        "problem_type_mastery_consistency",
        "aggregate_chapter_topic_consistency",
        "recommendation_behavior",
        "diagnostic_behavior",
        "repair_effectiveness_rules",
    }
    assert expected_names.issubset(metric_names)

    for m in result.metrics:
        assert m.status == MetricStatus.PASS


# --------------------------------------------------------------------------
# 2. Misconception Evaluator Tests
# --------------------------------------------------------------------------


def test_misconception_evaluator() -> None:
    evaluator = MisconceptionEvaluator()
    dataset_path = DATA_DIR / "misconceptions.jsonl"
    result = evaluator.evaluate(dataset_path)

    assert result.group == EvaluationGroup.MISCONCEPTION
    assert result.passed is True
    assert result.overall_score >= 0.80
    assert result.sample_count >= 15

    # Check confusion matrix
    assert result.confusion_matrix is not None
    assert len(result.confusion_matrix) > 5

    # Check breakdown
    assert "by_concept" in result.breakdown
    assert "by_problem_type" in result.breakdown
    assert len(result.breakdown["by_concept"]) > 3
    assert len(result.breakdown["by_problem_type"]) > 3


# --------------------------------------------------------------------------
# 3. RAG Evaluator Tests
# --------------------------------------------------------------------------


def test_rag_evaluator() -> None:
    evaluator = RAGEvaluator()
    dataset_path = DATA_DIR / "rag.json"
    result = evaluator.evaluate(dataset_path)

    assert result.group == EvaluationGroup.RAG
    assert result.passed is True
    assert result.overall_score >= 0.90

    metric_map = {m.name: m for m in result.metrics}
    assert "retrieval_relevance_mrr" in metric_map
    assert "source_correctness" in metric_map
    assert "curriculum_filtering_accuracy" in metric_map

    assert metric_map["curriculum_filtering_accuracy"].score >= 0.95
    assert metric_map["source_correctness"].score >= 0.90


# --------------------------------------------------------------------------
# 4. AI Tutor Evaluator Tests
# --------------------------------------------------------------------------


def test_ai_tutor_evaluator() -> None:
    evaluator = AITutorEvaluator()
    dataset_path = DATA_DIR / "ai_tutor.jsonl"
    result = evaluator.evaluate(dataset_path)

    assert result.group == EvaluationGroup.AI_TUTOR
    assert result.passed is True
    assert result.overall_score >= 0.85

    metric_map = {m.name: m for m in result.metrics}
    expected_metrics = [
        "correctness",
        "pedagogical_quality",
        "answer_leakage_prevention",
        "hallucination_resistance",
        "source_grounding",
        "problem_type_relevance",
        "prerequisite_diagnosis_faithfulness",
    ]
    for name in expected_metrics:
        assert name in metric_map
        assert metric_map[name].status == MetricStatus.PASS


# --------------------------------------------------------------------------
# 5. Teacher Copilot Evaluator Tests
# --------------------------------------------------------------------------


def test_teacher_copilot_evaluator() -> None:
    evaluator = TeacherCopilotEvaluator()
    dataset_path = DATA_DIR / "teacher_copilot.json"
    result = evaluator.evaluate(dataset_path)

    assert result.group == EvaluationGroup.TEACHER_COPILOT
    assert result.passed is True
    assert result.overall_score >= 0.90

    metric_map = {m.name: m for m in result.metrics}
    assert "data_consistency" in metric_map
    assert "actionability" in metric_map
    assert "hallucination_resistance" in metric_map


# --------------------------------------------------------------------------
# 6. Parent Summary Evaluator Tests
# --------------------------------------------------------------------------


def test_parent_summary_evaluator() -> None:
    evaluator = ParentSummaryEvaluator()
    dataset_path = DATA_DIR / "parent_summary.json"
    result = evaluator.evaluate(dataset_path)

    assert result.group == EvaluationGroup.PARENT_SUMMARY
    assert result.passed is True
    assert result.overall_score >= 0.90

    metric_map = {m.name: m for m in result.metrics}
    assert "data_faithfulness" in metric_map
    assert "tone_and_constructiveness" in metric_map
    assert "privacy_protection" in metric_map
    assert metric_map["privacy_protection"].score >= 0.95


# --------------------------------------------------------------------------
# 7. System AI Evaluator Tests
# --------------------------------------------------------------------------


def test_system_ai_evaluator() -> None:
    evaluator = SystemAIEvaluator()
    dataset_path = DATA_DIR / "system_ai.json"
    result = evaluator.evaluate(dataset_path)

    assert result.group == EvaluationGroup.SYSTEM_AI
    assert result.passed is True

    metric_map = {m.name: m for m in result.metrics}
    assert "average_latency" in metric_map
    assert "average_token_consumption" in metric_map
    assert "system_resilience_rate" in metric_map
    assert "average_cost_per_task" in metric_map


# --------------------------------------------------------------------------
# 8. Runner & Multi-Group Execution Tests
# --------------------------------------------------------------------------


def test_runner_executes_all_groups(tmp_path: Path) -> None:
    runner = EvaluationRunner(data_dir=DATA_DIR, output_dir=tmp_path)
    report, files = runner.run()

    assert report.total_samples_evaluated >= 50
    assert report.overall_passed is True
    assert len(report.groups) == 7

    # Check generated files
    assert files["json"].exists()
    assert files["markdown"].exists()

    with files["json"].open("r", encoding="utf-8") as f:
        json_data = json.load(f)
        assert json_data["overall_passed"] is True
        assert len(json_data["groups"]) == 7

    with files["markdown"].open("r", encoding="utf-8") as f:
        md_content = f.read()
        assert "ALL GROUPS PASSED" in md_content
        assert "LEARNING_ENGINE" in md_content
        assert "MISCONCEPTION" in md_content
        assert "RAG" in md_content
        assert "AI_TUTOR" in md_content
        assert "TEACHER_COPILOT" in md_content
        assert "PARENT_SUMMARY" in md_content
        assert "SYSTEM_AI" in md_content


def test_runner_executes_selected_groups(tmp_path: Path) -> None:
    runner = EvaluationRunner(data_dir=DATA_DIR, output_dir=tmp_path)
    report, files = runner.run(selected_groups=["MISCONCEPTION", "RAG"])

    assert len(report.groups) == 2
    assert "MISCONCEPTION" in report.groups
    assert "RAG" in report.groups
    assert "LEARNING_ENGINE" not in report.groups
