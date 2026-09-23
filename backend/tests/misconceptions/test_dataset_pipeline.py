from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.misconceptions.dataset.anonymizer import PIISanitizer
from app.misconceptions.dataset.cli import run_pipeline
from app.misconceptions.dataset.clusterer import (
    QuestionClusterer,
    normalize_question_text,
    token_jaccard_similarity,
)
from app.misconceptions.dataset.curator import build_curated_samples
from app.misconceptions.dataset.exporter import DatasetExporter
from app.misconceptions.dataset.schemas import (
    CognitiveTaxonomy,
    MisconceptionSample,
    MisconceptionSeverity,
    RecommendedHintType,
)
from app.misconceptions.dataset.splitter import LeakFreeSplitter, LeakageError
from app.misconceptions.dataset.validator import QualityValidationError, QualityValidator
from app.misconceptions.models import MisconceptionCategory


# --------------------------------------------------------------------------
# 1. PII Sanitizer Tests
# --------------------------------------------------------------------------


def test_pii_sanitizer_detects_and_redacts_email_and_phones() -> None:
    text_with_email = "Học sinh gửi bài qua email student.math@school.edu.vn để chấm."
    assert PIISanitizer.contains_pii(text_with_email)
    sanitized = PIISanitizer.sanitize_text(text_with_email)
    assert "[REDACTED_EMAIL]" in sanitized
    assert "student.math@school.edu.vn" not in sanitized

    text_with_phone = "Liên hệ số 0987654321 hoặc +84912345678 khi cần giải đáp."
    assert PIISanitizer.contains_pii(text_with_phone)
    sanitized_phone = PIISanitizer.sanitize_text(text_with_phone)
    assert "[REDACTED_PHONE]" in sanitized_phone
    assert "0987654321" not in sanitized_phone
    assert "+84912345678" not in sanitized_phone


def test_pii_sanitizer_detects_and_redacts_school_and_names() -> None:
    text_with_school = "Đề thi thử học kỳ 1 của Trường THPT Chu Văn An năm học 2026."
    assert PIISanitizer.contains_pii(text_with_school)
    sanitized = PIISanitizer.sanitize_text(text_with_school)
    assert "[REDACTED_SCHOOL]" in sanitized
    assert "THPT Chu Văn An" not in sanitized

    text_with_name = "Họ và tên: Nguyễn Văn An, bài làm câu 1."
    assert PIISanitizer.contains_pii(text_with_name)
    sanitized_name = PIISanitizer.sanitize_text(text_with_name)
    assert "[REDACTED_NAME]" in sanitized_name


def test_pii_sanitizer_strips_forbidden_keys() -> None:
    raw_dict = {
        "student_id": "123e4567-e89b-12d3-a456-426614174000",
        "full_name": "Lê Hoàng Phúc",
        "parent_phone": "0909123456",
        "question": "Tìm cực trị của hàm số.",
        "student_solution": "Học sinh giải: x = 2.",
    }
    sanitized = PIISanitizer.sanitize_sample_dict(raw_dict)
    assert "student_id" not in sanitized
    assert "full_name" not in sanitized
    assert "parent_phone" not in sanitized
    assert "question" in sanitized
    assert "student_solution" in sanitized


# --------------------------------------------------------------------------
# 2. Quality Validator Tests
# --------------------------------------------------------------------------


def test_quality_validator_approves_curated_samples() -> None:
    samples = build_curated_samples()
    validator = QualityValidator()
    assert len(samples) > 20
    for sample in samples:
        errors = validator.validate_sample(sample)
        assert errors == [], f"Curated sample {sample.id} failed validation: {errors}"
        assert validator.is_approved(sample)


def test_quality_validator_rejects_invalid_misconception_label() -> None:
    samples = build_curated_samples()
    sample = samples[0].model_copy()
    sample.verified_misconception_label = "INVENTED_HALLUCINATED_CODE"

    validator = QualityValidator()
    errors = validator.validate_sample(sample)
    assert any("not in the approved active taxonomy" in e for e in errors)
    assert not validator.is_approved(sample)
    with pytest.raises(QualityValidationError):
        validator.assert_approved(sample)


def test_quality_validator_rejects_identical_solutions() -> None:
    samples = build_curated_samples()
    sample = samples[0].model_copy()
    sample.student_solution = sample.reference_solution

    validator = QualityValidator()
    errors = validator.validate_sample(sample)
    assert any("cannot be identical to correct reference solution" in e for e in errors)


def test_quality_validator_rejects_unredacted_pii() -> None:
    samples = build_curated_samples()
    sample = samples[0].model_copy()
    sample.student_solution = "Em là học sinh Trần Văn B, số điện thoại 0912345678 làm bài."

    validator = QualityValidator()
    errors = validator.validate_sample(sample)
    assert any("personally identifiable information" in e for e in errors)


# --------------------------------------------------------------------------
# 3. Near-Duplicate Question Clustering Tests
# --------------------------------------------------------------------------


def test_question_clusterer_groups_near_duplicates() -> None:
    q1 = "Tìm các khoảng nghịch biến của hàm số y = x^3 - 3x^2 + 2."
    q2 = "Xác định các khoảng nghịch biến của hàm số f(x) = x^3 - 3x^2 + 2."
    q_other = "Trong không gian Oxyz, tìm tọa độ vectơ AB."

    sample1 = MisconceptionSample(
        id="smp_1",
        question=q1,
        problem_type="MONOTONICITY_FROM_EXPRESSION",
        concepts=["DERIVATIVE"],
        taxonomy=CognitiveTaxonomy.UNDERSTAND,
        student_solution="y' < 0 nên đồng biến",
        reference_solution="y' < 0 nên nghịch biến",
        verified_misconception_label="DERIVATIVE_SIGN_DIRECTION",
        error_category=MisconceptionCategory.CONCEPTUAL,
        severity=MisconceptionSeverity.HIGH,
        recommended_hint_type=RecommendedHintType.CONCEPT_RECALL,
    )
    sample2 = sample1.model_copy(update={"id": "smp_2", "question": q2})
    sample3 = sample1.model_copy(update={"id": "smp_3", "question": q_other})

    clusterer = QuestionClusterer(similarity_threshold=0.60)
    clustered = clusterer.assign_clusters([sample1, sample2, sample3])

    # sample1 and sample2 are near-duplicates and MUST share the same cluster_id
    assert clustered[0].cluster_id == clustered[1].cluster_id
    # sample3 is completely distinct and must have a different cluster_id
    assert clustered[0].cluster_id != clustered[2].cluster_id


# --------------------------------------------------------------------------
# 4. Leak-Free Splitter Tests
# --------------------------------------------------------------------------


def test_leak_free_splitter_guarantees_zero_cross_split_leakage() -> None:
    samples = build_curated_samples()
    clusterer = QuestionClusterer(similarity_threshold=0.60)
    clustered_samples = clusterer.assign_clusters(samples)

    splitter = LeakFreeSplitter(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, random_seed=42)
    train, val, test = splitter.split(clustered_samples)

    assert len(train) > 0
    assert len(val) > 0
    assert len(test) > 0
    assert len(train) + len(val) + len(test) == len(samples)

    # 1. Zero cluster ID overlap
    train_clusters = {s.cluster_id for s in train}
    val_clusters = {s.cluster_id for s in val}
    test_clusters = {s.cluster_id for s in test}

    assert len(train_clusters & val_clusters) == 0
    assert len(train_clusters & test_clusters) == 0
    assert len(val_clusters & test_clusters) == 0

    # 2. Zero normalized question text overlap
    train_texts = {normalize_question_text(s.question) for s in train}
    val_texts = {normalize_question_text(s.question) for s in val}
    test_texts = {normalize_question_text(s.question) for s in test}

    assert len(train_texts & val_texts) == 0
    assert len(train_texts & test_texts) == 0
    assert len(val_texts & test_texts) == 0

    # 3. Near-duplicate questions MUST NOT be split across sets
    for t1 in train_texts:
        for t2 in val_texts | test_texts:
            sim = token_jaccard_similarity(t1, t2)
            assert sim < 0.60, f"Leakage: question '{t1}' in train is near-duplicate of '{t2}' with sim={sim}"

    # 4. verify_leak_free passes
    check_result = splitter.verify_leak_free(train, val, test)
    assert check_result.is_leak_free is True


def test_splitter_raises_on_invalid_ratios() -> None:
    with pytest.raises(ValueError, match="Ratios must sum to 1.0"):
        LeakFreeSplitter(train_ratio=0.8, val_ratio=0.3, test_ratio=0.1)


# --------------------------------------------------------------------------
# 5. Exporter & SFT Formats Tests
# --------------------------------------------------------------------------


def test_exporter_writes_all_files_and_sft_format(tmp_path: Path) -> None:
    samples = build_curated_samples()
    clusterer = QuestionClusterer(similarity_threshold=0.60)
    clustered_samples = clusterer.assign_clusters(samples)

    splitter = LeakFreeSplitter(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15)
    train, val, test = splitter.split(clustered_samples)

    exporter = DatasetExporter(output_dir=tmp_path)
    report = exporter.generate_report(clustered_samples, train, val, test, splitter)
    exported = exporter.export(clustered_samples, train, val, test, report)

    # Check that all expected files exist
    assert (tmp_path / "dataset_v1.jsonl").exists()
    assert (tmp_path / "train.jsonl").exists()
    assert (tmp_path / "val.jsonl").exists()
    assert (tmp_path / "test.jsonl").exists()
    assert (tmp_path / "sft_train.jsonl").exists()
    assert (tmp_path / "sft_val.jsonl").exists()
    assert (tmp_path / "sft_test.jsonl").exists()
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "DATASET_REPORT.md").exists()

    # Check SFT file structure
    with (tmp_path / "sft_train.jsonl").open("r", encoding="utf-8") as f:
        first_line = json.loads(f.readline())
        assert "instruction" in first_line
        assert "input" in first_line
        assert "output" in first_line
        assert "question" in first_line["input"]
        assert "problem_type" in first_line["input"]
        assert "concepts" in first_line["input"]
        assert "student_solution" in first_line["input"]
        assert "reference_solution" in first_line["input"]
        assert "misconception_label" in first_line["output"]
        assert "error_category" in first_line["output"]
        assert "severity" in first_line["output"]
        assert "recommended_hint_type" in first_line["output"]

    # Check Report contents
    assert report.total_samples == len(samples)
    assert report.leakage_check.is_leak_free is True
    assert report.missing_values["question"] == 0
    assert report.missing_values["verified_misconception_label"] == 0
    assert len(report.class_distribution) >= 8


# --------------------------------------------------------------------------
# 6. Full CLI Pipeline Test
# --------------------------------------------------------------------------


def test_cli_pipeline_execution(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli_test_dataset"
    report = run_pipeline(output_dir=out_dir)
    assert report.total_samples > 0
    assert report.leakage_check.is_leak_free is True
    assert (out_dir / "DATASET_REPORT.md").exists()
    assert (out_dir / "report.json").exists()
