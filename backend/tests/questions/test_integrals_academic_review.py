from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import pytest

from app.questions.integrals_academic_review import (
    DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256,
    EXPECTED_COUNTS,
    EXPECTED_GAP,
    EXPECTED_HOLD_TYPE_COUNTS,
    EXPECTED_PROBLEM_TYPE_COUNTS,
    EXPECTED_SEMANTIC_HASHES,
    EXPECTED_VERIFIED_TYPE_COUNTS,
    IntegralsAcademicReviewValidator,
)
from app.validate_integrals_academic_review import main


def _load(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write(root: Path, name: str, value: Any) -> None:
    (root / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _copy_dataset(tmp_path: Path) -> Path:
    destination = tmp_path / "academic_review" / "v0_1"
    shutil.copytree(DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH, destination)
    return destination


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


def test_validator_reports_exact_data_math12_023_state() -> None:
    report = IntegralsAcademicReviewValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.counts == EXPECTED_COUNTS
    assert report.verified_question_type_counts == EXPECTED_VERIFIED_TYPE_COUNTS
    assert report.hold_question_type_counts == EXPECTED_HOLD_TYPE_COUNTS
    assert report.problem_type_coverage == EXPECTED_PROBLEM_TYPE_COUNTS
    assert report.problem_type_gaps == (EXPECTED_GAP,)
    assert report.aggregate_semantic_sha256 == EXPECTED_AGGREGATE_SEMANTIC_SHA256
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False
    assert report.canonical_snapshot_allowed is False
    assert all(report.checks.values())


def test_source_registry_contains_exact_22_real_source_lineages() -> None:
    sources = _load(DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH, "source_registry.json")

    assert len(sources) == 22
    assert len({row["source_code"] for row in sources}) == 22
    assert len({row["source_file_id"] for row in sources}) == 22
    assert len({row["source_pdf_sha256"] for row in sources}) == 22
    assert sum(row["integral_candidate_occurrences_detected"] for row in sources) == 210
    assert sum(row["verified_occurrence_contributions"] for row in sources) == 133
    assert sum(row["primary_verified_candidates"] for row in sources) == 77
    assert sum(row["hold_occurrence_contributions"] for row in sources) == 77
    assert all(row["rights_status"] == "REVIEW_REQUIRED" for row in sources)
    assert not list(DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH.rglob("*.pdf"))


def test_official_scope_and_derived_taxonomy_boundary_is_preserved() -> None:
    taxonomy = _load(
        DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH, "taxonomy_candidate.json"
    )
    binding = taxonomy["official_scope_binding"]

    assert taxonomy["subject_code"] == "MATH_G12"
    assert taxonomy["chapter_code"] == "INTEGRALS"
    assert taxonomy["topic_code"] == "INTEGRAL_TOPIC"
    assert binding["official_scope_code"] == (
        "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL"
    )
    assert binding["official_content_title"] == "Nguyên hàm. Tích phân"
    assert taxonomy["classification_policy"][
        "problem_types_concepts_and_weights_are"
    ] == "COACH_LEARNING_DERIVED"
    assert all(
        row["provenance_type"] == "COACH_LEARNING_DERIVED"
        for row in taxonomy["concepts"]
    )
    assert taxonomy["classification_policy"]["synthetic_question_fill_allowed"] is False


def test_verified_partition_answers_mappings_and_evidence_are_exact() -> None:
    root = DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH
    questions = _load(root, "verified_questions.json")
    evidence = {row["candidate_id"]: row for row in _load(root, "source_evidence.json")}
    taxonomy = _load(root, "taxonomy_candidate.json")

    assert len(questions) == 77
    assert len(evidence) == 77
    assert Counter(row["question_type"] for row in questions) == (
        EXPECTED_VERIFIED_TYPE_COUNTS
    )
    for row in questions:
        source_evidence = evidence[row["candidate_id"]]
        problem_type = row["problem_type_code"]
        assert row["review_status"] == "VERIFIED_SOURCE_ANSWER"
        assert row["answer_verification"] == "SOURCE_SOLUTION_EXPLICIT"
        assert row["correct_answer"] == source_evidence["source_claimed_answer"]
        assert row["question_pages"] == source_evidence["question_pages"]
        assert row["solution_answer_page"] == source_evidence["solution_answer_page"]
        assert row["concepts"] == taxonomy["mappings"][problem_type]
        assert row["learning_outcomes"] == [
            {
                "learning_outcome_code": taxonomy[
                    "problem_type_learning_outcome"
                ][problem_type],
                "weight": 1.0,
            }
        ]


def test_hold_partition_remains_answerless_and_non_importable() -> None:
    holds = _load(DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH, "hold_candidates.json")

    assert len(holds) == 67
    assert Counter(row["question_type"] for row in holds) == EXPECTED_HOLD_TYPE_COUNTS
    assert all(row["review_status"] == "HOLD_SOURCE_ANSWER_UNPARSED" for row in holds)
    assert all("correct_answer" not in row for row in holds)
    assert all(row["detected_answers"] == [] for row in holds)
    assert all(row["promotion_ready"] is False for row in holds)
    assert all(row["database_import_allowed"] is False for row in holds)
    assert all(row["canonical_snapshot_allowed"] is False for row in holds)


def test_duplicate_clusters_preserve_exact_dedupe_policy() -> None:
    root = DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH
    clusters = _load(root, "duplicate_clusters.json")
    verified = {
        row["candidate_id"]: row for row in _load(root, "verified_questions.json")
    }

    assert len(clusters) == 52
    assert len({row["cluster_id"] for row in clusters}) == 52
    assert {row["canonical_candidate_id"] for row in clusters} == {
        candidate_id
        for candidate_id, row in verified.items()
        if row["duplicate_occurrence_count"] > 1
    }
    for cluster in clusters:
        canonical = verified[cluster["canonical_candidate_id"]]
        assert cluster["dedupe_basis"] == "EXACT_NORMALIZED_QUESTION_TEXT"
        assert cluster["answer_consistency"] == "CONSISTENT"
        assert cluster["occurrence_count"] == canonical["duplicate_occurrence_count"]


def test_coverage_preserves_real_gap_and_no_synthetic_fill() -> None:
    root = DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH
    coverage = _load(root, "coverage.json")
    stats = _load(root, "review_stats.json")
    contract = _load(root, "data_contract.json")

    counts = {row["problem_type_code"]: row["verified_candidates"] for row in coverage}
    assert counts == EXPECTED_PROBLEM_TYPE_COUNTS
    assert [row["problem_type_code"] for row in coverage if row["status"] == "GAP"] == [
        EXPECTED_GAP
    ]
    assert stats["problem_type_gaps"] == [EXPECTED_GAP]
    assert contract["locked_problem_type_gaps"] == [EXPECTED_GAP]
    assert contract["policy"]["no_synthetic_gap_fill"] is True
    assert stats["visual_asset_required_verified"] == 28


def test_semantic_hashes_and_locked_aggregate_are_exact() -> None:
    root = DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH
    contract = _load(root, "data_contract.json")

    assert contract["semantic_sha256"] == EXPECTED_SEMANTIC_HASHES
    assert contract["aggregate_semantic_sha256"] == (
        EXPECTED_AGGREGATE_SEMANTIC_SHA256
    )
    for name, expected in EXPECTED_SEMANTIC_HASHES.items():
        value = _load(root, name)
        assert IntegralsAcademicReviewValidator.semantic_sha256(value) == expected


def test_validation_is_read_only_and_deterministic() -> None:
    root = DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH
    before = {
        file.name: hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.iterdir()
        if file.is_file()
    }

    first = IntegralsAcademicReviewValidator().validate()
    second = IntegralsAcademicReviewValidator().validate()
    after = {
        file.name: hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.iterdir()
        if file.is_file()
    }

    assert first.as_dict() == second.as_dict()
    assert before == after


def test_cli_reports_pass_and_locked_aggregate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"
    assert output["aggregate_semantic_sha256"] == EXPECTED_AGGREGATE_SEMANTIC_SHA256


Mutation = Callable[[Any], None]


@pytest.mark.parametrize(
    ("file_name", "mutate", "expected_code"),
    [
        (
            "verified_questions.json",
            lambda rows: rows[0].__setitem__("correct_answer", "A"),
            "INVALID_VERIFIED_RECORD",
        ),
        (
            "verified_questions.json",
            lambda rows: rows[0].__setitem__("review_status", "HOLD"),
            "INVALID_VERIFIED_RECORD",
        ),
        (
            "hold_candidates.json",
            lambda rows: rows[0].__setitem__("review_status", "VERIFIED_SOURCE_ANSWER"),
            "INVALID_HOLD_RECORD",
        ),
        (
            "verified_questions.json",
            lambda rows: rows[0].__setitem__("source_file_id", "changed-file-id"),
            "INVALID_VERIFIED_RECORD",
        ),
        (
            "verified_questions.json",
            lambda rows: rows[0].__setitem__("source_pdf_sha256", "0" * 64),
            "INVALID_VERIFIED_RECORD",
        ),
        (
            "verified_questions.json",
            lambda rows: rows[0].__setitem__("question_start_page", 999999),
            "INVALID_VERIFIED_RECORD",
        ),
        (
            "source_evidence.json",
            lambda rows: rows[0].__setitem__("solution_answer_page", 999999),
            "INVALID_SOURCE_EVIDENCE",
        ),
        (
            "duplicate_clusters.json",
            lambda rows: rows[0].__setitem__(
                "canonical_candidate_id", "M12_INT_CAND_9999"
            ),
            "INVALID_DUPLICATE_CLUSTER",
        ),
        (
            "verified_questions.json",
            lambda rows: rows[0].__setitem__(
                "problem_type_code", "CALCULATE_ANTIDERIVATIVE"
            ),
            "INVALID_VERIFIED_RECORD",
        ),
        (
            "coverage.json",
            lambda rows: next(
                row
                for row in rows
                if row["problem_type_code"] == "CALCULATE_DEFINITE_INTEGRAL"
            ).__setitem__("verified_candidates", 1),
            "COVERAGE_REPORT_MISMATCH",
        ),
        (
            "review_stats.json",
            lambda value: value.__setitem__("database_import_allowed", True),
            "RELEASE_BOUNDARY_VIOLATION",
        ),
        (
            "data_contract.json",
            lambda value: value["semantic_sha256"].__setitem__(
                "verified_questions.json", "0" * 64
            ),
            "SEMANTIC_HASH_MAP_MISMATCH",
        ),
    ],
)
def test_curated_mutations_are_rejected(
    tmp_path: Path,
    file_name: str,
    mutate: Mutation,
    expected_code: str,
) -> None:
    root = _copy_dataset(tmp_path)
    value = _load(root, file_name)
    mutate(value)
    _write(root, file_name, value)

    report = IntegralsAcademicReviewValidator().validate(root)

    assert not report.is_valid
    assert expected_code in _codes(report)
    assert (
        "SEMANTIC_FILE_HASH_MISMATCH" in _codes(report)
        or "DATA_CONTRACT_HASH_MISMATCH" in _codes(report)
    )


def test_source_pdf_binary_is_rejected(tmp_path: Path) -> None:
    root = _copy_dataset(tmp_path)
    (root / "source.pdf").write_bytes(b"%PDF-forbidden")

    report = IntegralsAcademicReviewValidator().validate(root)

    assert not report.is_valid
    assert "SOURCE_PDF_BINARY_PRESENT" in _codes(report)
