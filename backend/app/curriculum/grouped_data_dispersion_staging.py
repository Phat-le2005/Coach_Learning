from __future__ import annotations

from pathlib import Path
from typing import Any

from app.curriculum.vector_staging import (
    VECTOR_HASH_FILES,
    VECTOR_LIST_FILES,
    VectorCurriculumStagingValidator,
    VectorStagingIssue,
    VectorStagingReport,
)


DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "grouped_data_dispersion_v0_1"
)
GROUPED_DATA_DISPERSION_LIST_FILES = VECTOR_LIST_FILES
GROUPED_DATA_DISPERSION_HASH_FILES = VECTOR_HASH_FILES
EXPECTED_GROUPED_DATA_DISPERSION_COUNTS = {
    "chapters": 1,
    "topics": 4,
    "problem_types": 12,
    "concepts": 15,
    "official_learning_outcomes": 4,
    "learning_outcomes": 4,
    "concept_relations": 21,
    "problem_type_concepts": 40,
    "problem_type_learning_outcomes": 12,
}
EXPECTED_GROUPED_DATA_DISPERSION_CONTENT_SHA256 = (
    "fac7ede33fde8c1cd875158da0bbf020301235f6b2dd9f5558cc0d945ca12229"
)
EXPECTED_CLASSIFICATION = {
    "official_learning_outcomes": "OFFICIAL_NORMALIZED",
    "topics": "COACH_LEARNING_DERIVED",
    "problem_types": "COACH_LEARNING_DERIVED",
    "concepts": "COACH_LEARNING_DERIVED",
    "concept_relations": "COACH_LEARNING_DERIVED",
    "weights": "COACH_LEARNING_DERIVED_INITIAL_EXPERT_WEIGHTS",
    "difficulty": "COACH_LEARNING_DERIVED_INITIAL_EXPERT_DIFFICULTY",
}
EXPECTED_PROBLEM_TYPE_CODES = {
    "CALCULATE_GROUPED_RANGE",
    "CALCULATE_GROUPED_IQR",
    "CALCULATE_GROUPED_VARIANCE",
    "CALCULATE_GROUPED_STANDARD_DEVIATION",
    "COMPARE_GROUPED_RANGE",
    "COMPARE_GROUPED_IQR",
    "COMPARE_GROUPED_VARIANCE_SD",
    "IDENTIFY_MORE_STABLE_GROUPED_DATA",
    "INTERPRET_GROUPED_DISPERSION_MEASURE",
    "CONCLUDE_FROM_GROUPED_DISPERSION",
    "PARAMETER_FROM_GROUPED_VARIANCE_SD",
    "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS",
}
EXPECTED_SCOPE_BOUNDARY = (
    "Grade-12 target is dispersion of grouped data: range, interquartile range, "
    "variance, standard deviation, interpretation/comparison/application. "
    "Mean/median/mode/quartiles asked as standalone central-tendency/location "
    "tasks are Grade-11/prerequisite and are not target questions for this chapter."
)
PREREQUISITE_CONCEPT_CODES = {
    "GROUPED_QUARTILE_INTERPOLATION",
    "GROUPED_MEAN_FOR_DISPERSION",
}

GroupedDataDispersionStagingIssue = VectorStagingIssue
GroupedDataDispersionStagingReport = VectorStagingReport


class GroupedDataDispersionStagingValidator:
    """Validate the non-importable grouped-data dispersion review candidate."""

    def validate(
        self, dataset_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH
    ) -> GroupedDataDispersionStagingReport:
        path = dataset_path.resolve()
        initial: list[VectorStagingIssue] = []
        rows = {
            name: VectorCurriculumStagingValidator._load_list(path, name, initial)
            for name in GROUPED_DATA_DISPERSION_LIST_FILES
        }
        metadata = VectorCurriculumStagingValidator._load_object(
            path, "taxonomy_metadata", initial
        )
        supplied_report = VectorCurriculumStagingValidator._load_object(
            path, "validation_report", initial
        )
        content_hash = VectorCurriculumStagingValidator.content_hash(path, initial)
        counts = {
            name: len(rows[name]) for name in GROUPED_DATA_DISPERSION_LIST_FILES
        }
        checks_to_errors = {
            "dataset_files": [
                error for error in initial if error.check == "dataset_files"
            ],
            "manifest_absent": self._validate_manifest_absent(path),
            "exact_counts": self._validate_counts(counts, supplied_report),
            "unique_codes": VectorCurriculumStagingValidator._validate_unique_codes(
                rows
            ),
            "references_resolve": (
                VectorCurriculumStagingValidator._validate_references(rows, metadata)
            ),
            "grade_level": VectorCurriculumStagingValidator._validate_grade(
                rows, metadata
            ),
            "difficulty_range": (
                VectorCurriculumStagingValidator._validate_difficulty(rows)
            ),
            "primary_concept": (
                VectorCurriculumStagingValidator._validate_primary_concepts(rows)
            ),
            "concept_weight_totals": (
                VectorCurriculumStagingValidator._validate_weight_totals(
                    rows, "problem_type_concepts", "concept"
                )
            ),
            "learning_outcome_weight_totals": (
                VectorCurriculumStagingValidator._validate_weight_totals(
                    rows, "problem_type_learning_outcomes", "learning_outcome"
                )
            ),
            "prerequisite_graph_acyclic": (
                VectorCurriculumStagingValidator._validate_graph(rows)
            ),
            "subject_chapter_status": self._validate_identity(metadata, rows),
            "provenance_boundary": self._validate_provenance(metadata, rows),
            "grade11_boundary": self._validate_grade11_boundary(metadata, rows),
            "deterministic_content_hash": self._validate_hash(content_hash),
        }
        errors = list(initial)
        for name, check_errors in checks_to_errors.items():
            if name != "dataset_files":
                errors.extend(check_errors)
        checks = {
            name: not check_errors
            for name, check_errors in checks_to_errors.items()
        }
        ordered_errors = tuple(sorted(set(errors)))
        return VectorStagingReport(
            dataset_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts=counts,
            content_sha256=content_hash,
            errors=ordered_errors,
        )

    @staticmethod
    def _validate_manifest_absent(path: Path) -> list[VectorStagingIssue]:
        if not (path / "manifest.json").exists():
            return []
        return [
            VectorStagingIssue(
                "manifest_absent",
                "STAGING_MANIFEST_FORBIDDEN",
                "manifest.json",
                "Review staging must not contain a canonical manifest.",
            )
        ]

    @staticmethod
    def _validate_counts(
        counts: dict[str, int], supplied: dict[str, Any]
    ) -> list[VectorStagingIssue]:
        valid = (
            counts == EXPECTED_GROUPED_DATA_DISPERSION_COUNTS
            and supplied.get("counts") == EXPECTED_GROUPED_DATA_DISPERSION_COUNTS
            and supplied.get("status") == "PASS_STRUCTURAL_CONTRACT"
            and supplied.get("promotion_ready") is False
            and supplied.get("academic_review_complete") is False
            and supplied.get("question_candidates_materialized") is False
            and supplied.get("canonical_curriculum_modified") is False
            and supplied.get("database_import_allowed") is False
        )
        if valid:
            return []
        return [
            VectorStagingIssue(
                "exact_counts",
                "UNEXPECTED_DATASET_COUNTS_OR_BOUNDARY",
                "validation_report.json",
                f"Expected {EXPECTED_GROUPED_DATA_DISPERSION_COUNTS}; found {counts}.",
            )
        ]

    @staticmethod
    def _validate_identity(
        metadata: dict[str, Any], rows: dict[str, list[dict[str, Any]]]
    ) -> list[VectorStagingIssue]:
        chapters = rows["chapters"]
        valid = (
            metadata.get("status") == "REVIEW_CANDIDATE"
            and metadata.get("subject_code") == "MATH_G12"
            and metadata.get("chapter_code") == "GROUPED_DATA_DISPERSION"
            and len(chapters) == 1
            and chapters[0].get("code") == "GROUPED_DATA_DISPERSION"
            and all(row.get("is_active") is True for row in rows["problem_types"])
        )
        if valid:
            return []
        return [
            VectorStagingIssue(
                "subject_chapter_status",
                "SUBJECT_CHAPTER_STATUS_MISMATCH",
                "taxonomy_metadata.json",
                "Expected MATH_G12/GROUPED_DATA_DISPERSION REVIEW_CANDIDATE.",
            )
        ]

    @staticmethod
    def _validate_provenance(
        metadata: dict[str, Any], rows: dict[str, list[dict[str, Any]]]
    ) -> list[VectorStagingIssue]:
        valid = (
            metadata.get("classification") == EXPECTED_CLASSIFICATION
            and all(
                row.get("provenance_type") == "OFFICIAL_NORMALIZED"
                for row in rows["official_learning_outcomes"]
            )
        )
        if valid:
            return []
        return [
            VectorStagingIssue(
                "provenance_boundary",
                "INVALID_TAXONOMY_PROVENANCE",
                "taxonomy_metadata.json",
                "Only normalized outcomes are official; taxonomy remains derived.",
            )
        ]

    @staticmethod
    def _validate_grade11_boundary(
        metadata: dict[str, Any], rows: dict[str, list[dict[str, Any]]]
    ) -> list[VectorStagingIssue]:
        problem_types = {str(row.get("code")) for row in rows["problem_types"]}
        concepts = {str(row.get("code")) for row in rows["concepts"]}
        forbidden_tokens = ("MEAN_ONLY", "MEDIAN", "MODE", "QUARTILE_ONLY")
        valid = (
            problem_types == EXPECTED_PROBLEM_TYPE_CODES
            and metadata.get("scope_boundary") == EXPECTED_SCOPE_BOUNDARY
            and PREREQUISITE_CONCEPT_CODES <= concepts
            and not any(
                token in code
                for code in problem_types
                for token in forbidden_tokens
            )
        )
        if valid:
            return []
        return [
            VectorStagingIssue(
                "grade11_boundary",
                "GRADE11_SCOPE_BOUNDARY_VIOLATION",
                "problem_types.json",
                "Standalone central-tendency/location tasks are outside Grade 12 dispersion.",
            )
        ]

    @staticmethod
    def _validate_hash(content_hash: str) -> list[VectorStagingIssue]:
        if content_hash == EXPECTED_GROUPED_DATA_DISPERSION_CONTENT_SHA256:
            return []
        return [
            VectorStagingIssue(
                "deterministic_content_hash",
                "CONTENT_HASH_MISMATCH",
                "dataset",
                (
                    f"Expected {EXPECTED_GROUPED_DATA_DISPERSION_CONTENT_SHA256}; "
                    f"found {content_hash}."
                ),
            )
        ]
