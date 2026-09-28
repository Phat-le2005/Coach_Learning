from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.curriculum.vector_staging import DEFAULT_VECTOR_STAGING_PATH
from app.questions.vector_source_staging import DEFAULT_VECTOR_SOURCE_STAGING_PATH


DEFAULT_VECTOR_MATERIALIZATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "vector_coordinates_v0_1"
    / "staging"
    / "materialized_v0_1"
)

EXPECTED_BASE_COMMIT = "1bbd044497b873df78fa5cfdcb388ca8ecff9035"
EXPECTED_AGGREGATE_SEMANTIC_SHA256 = (
    "6ee45529e5cdc78d7f07c02f94e9b0c0a6a42b1b9117fdf80e424df8f9eae697"
)
EXPECTED_SCOPE_DECISIONS = {
    "M12_VECTOR_CAND_0019": "EXCLUDE_OUT_OF_SCOPE_GRADE12",
    "M12_VECTOR_CAND_0035": "EXCLUDE_OUT_OF_SCOPE_GRADE12",
    "M12_VECTOR_CAND_0037": "EXCLUDE_OUT_OF_SCOPE_GRADE12",
    "M12_VECTOR_CAND_0046": "HOLD_VECTOR_OXYZ_BOUNDARY",
}
EXPECTED_EXCLUDED_IDS = (
    "M12_VECTOR_CAND_0019",
    "M12_VECTOR_CAND_0035",
    "M12_VECTOR_CAND_0037",
)
EXPECTED_BOUNDARY_HOLD_IDS = ("M12_VECTOR_CAND_0046",)
EXPECTED_COUNTS: dict[str, Any] = {
    "materialization_code": "MATH12_VECTOR_MATERIALIZATION_V0_1",
    "status": "STRUCTURAL_REVIEW_REQUIRED",
    "raw_included_occurrences": 132,
    "materialized_unique_candidates": 72,
    "standalone_candidates": 58,
    "true_false_four_groups": 14,
    "structural_holds": 0,
    "question_type_counts": {
        "MULTIPLE_CHOICE": 54,
        "TRUE_FALSE_GROUP": 14,
        "SHORT_ANSWER": 4,
    },
    "selected_source_counts": {
        "SRC_MOET_EXAM_2025_SOLUTION_COMPILATION": 4,
        "SRC_PROVINCIAL_TRIAL_2025_COLLECTION": 11,
        "SRC_TRUONG_NGOC_VY_40_2026": 57,
    },
    "all_provenance_occurrence_counts": {
        "SRC_MOET_EXAM_2025_SOLUTION_COMPILATION": 8,
        "SRC_PROVINCIAL_TRIAL_2025_COLLECTION": 23,
        "SRC_TRUONG_NGOC_VY_40_2026": 101,
    },
    "answer_detected_count": 47,
    "mixed_scope_group_count": 12,
    "visual_required_count": 53,
    "problem_types_total": 15,
    "problem_types_with_candidates": 9,
    "problem_type_gaps": [
        "VECTOR_SCALAR_MULTIPLICATION_3D",
        "POINT_COORDINATES_3D",
        "VECTOR_COORDINATES_FROM_POINTS_3D",
        "VECTOR_COORDINATE_LINEAR_OPERATIONS_3D",
        "VECTOR_COORDINATE_DOT_PRODUCT_3D",
        "MIDPOINT_CENTROID_COORDINATES_3D",
    ],
    "production_release_eligible": 0,
    "academic_review_complete": False,
}
EXPECTED_SOURCE_LOCKS = {
    "SRC_TRUONG_NGOC_VY_40_2026": {
        "source_key": "NGOC_VY_40_DE_2026",
        "file_id": "1kVuA8ZIb402-_TM_fqI_tj1WuS0CBwg1",
        "sha256": "15579d487c6ad6cdd6386c96ac829c48710c3ca66104acfbd0fc9e9183b586b4",
        "page_count": 778,
    },
    "SRC_PROVINCIAL_TRIAL_2025_COLLECTION": {
        "source_key": "PROVINCIAL_TRIAL_2025",
        "file_id": "1RK3hOLaqhf2ZXDo_R1hJu2IwkYzZbvlP",
        "sha256": "d3f2158ee028431e01b2f30f7e446d66d75e364c27d49c53f3e09c193325b7e0",
        "page_count": 191,
    },
    "SRC_MOET_EXAM_2025_SOLUTION_COMPILATION": {
        "source_key": "OFFICIAL_EXAM_SOLUTIONS_2025",
        "file_id": "1jGjnJ3Wq2ynISxB4P1g9mk2CXibl-YXy",
        "sha256": "90d5cb68a6f91418287c6643548f4f40ea9bb1598705a177b41bce07b09df11f",
        "page_count": 71,
    },
}
SEMANTIC_FILES = (
    "candidate_questions.json",
    "standalone_candidates.json",
    "question_group_candidates.json",
    "structural_holds.json",
    "coverage_report.json",
    "extraction_stats.json",
    "source_hash_verification.json",
    "materialization_policy.json",
    "scope_review_overrides.json",
    "effective_candidates.json",
    "effective_standalone_candidates.json",
    "effective_review_stats.json",
)
EXPECTED_EFFECTIVE_REVIEW_COUNTS: dict[str, Any] = {
    "candidates": 68,
    "standalone": 54,
    "true_false_four_groups": 14,
    "question_type_counts": {
        "MULTIPLE_CHOICE": 51,
        "TRUE_FALSE_GROUP": 14,
        "SHORT_ANSWER": 3,
    },
    "visual_required": 50,
    "answer_detected": 47,
    "mixed_scope_groups": 12,
    "problem_types_total": 15,
    "problem_types_with_candidates": 9,
    "problem_type_gaps": EXPECTED_COUNTS["problem_type_gaps"],
    "verified": 0,
    "approved": 0,
    "production_release_eligible": 0,
}


@dataclass(frozen=True, slots=True, order=True)
class VectorMaterializationIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class VectorMaterializationReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, Any]
    aggregate_semantic_sha256: str | None
    problem_type_gaps: tuple[str, ...]
    rights_status: str | None
    errors: tuple[VectorMaterializationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "problem_type_gaps": list(self.problem_type_gaps),
            "rights_status": self.rights_status,
            "errors": [asdict(error) for error in self.errors],
        }


class VectorQuestionMaterializationValidator:
    """Validate DATA-MATH12-016 without changing data or writing database rows."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_VECTOR_MATERIALIZATION_PATH,
        *,
        vector_staging_path: Path = DEFAULT_VECTOR_STAGING_PATH,
        source_staging_path: Path = DEFAULT_VECTOR_SOURCE_STAGING_PATH,
    ) -> VectorMaterializationReport:
        path = dataset_path.resolve()
        issues: list[VectorMaterializationIssue] = []
        manifest = self._load_object(path / "materialization_manifest.json", issues)
        policy = self._load_object(path / "materialization_policy.json", issues)
        verification = self._load_object(path / "source_hash_verification.json", issues)
        stats = self._load_object(path / "extraction_stats.json", issues)
        candidates = self._load_list(path / "candidate_questions.json", issues)
        standalone = self._load_list(path / "standalone_candidates.json", issues)
        groups = self._load_list(path / "question_group_candidates.json", issues)
        holds = self._load_list(path / "structural_holds.json", issues)
        coverage = self._load_list(path / "coverage_report.json", issues)
        overlay = self._load_object(path / "scope_review_overrides.json", issues)
        effective_candidates = self._load_list(
            path / "effective_candidates.json", issues
        )
        effective_standalone = self._load_list(
            path / "effective_standalone_candidates.json", issues
        )
        effective_stats = self._load_object(
            path / "effective_review_stats.json", issues
        )
        scope_report = self._load_object(path / "scope_review_report.json", issues)
        aggregate_contract = self._load_object(
            path / "aggregate_hash_contract.json", issues
        )
        effective_contract = self._load_object(
            path / "effective_materialization_contract.json", issues
        )
        review_rows = self._load_review_queue(path / "review_queue.csv", issues)
        source_manifest = self._load_object(
            source_staging_path.resolve() / "source_manifest.json", issues,
            check="source_registry",
        )
        problem_types = self._load_list(
            vector_staging_path.resolve() / "problem_types.json", issues,
            check="taxonomy_mappings",
        )
        concept_rows = self._load_list(
            vector_staging_path.resolve() / "problem_type_concepts.json", issues,
            check="taxonomy_mappings",
        )
        outcome_rows = self._load_list(
            vector_staging_path.resolve() / "problem_type_learning_outcomes.json",
            issues,
            check="taxonomy_mappings",
        )

        check_errors: dict[str, list[VectorMaterializationIssue]] = {
            "required_files": [i for i in issues if i.check == "required_files"],
            "manifest_boundary": self._validate_manifest(manifest, stats),
            "aggregate_contract": self._validate_aggregate_contract(
                aggregate_contract
            ),
            "effective_contract": self._validate_effective_contract(
                effective_contract
            ),
            "semantic_hashes": self._validate_semantic_hashes(path, manifest),
            "aggregate_integrity": self._validate_aggregate_integrity(
                path, manifest
            ),
            "exact_counts": self._validate_counts(candidates, standalone, groups, holds),
            "candidate_identity": self._validate_candidate_identity(candidates),
            "scope_overlay": self._validate_scope_overlay(
                candidates, groups, overlay
            ),
            "effective_projection": self._validate_effective_projection(
                candidates,
                standalone,
                groups,
                overlay,
                effective_candidates,
                effective_standalone,
                effective_stats,
                scope_report,
                problem_types,
            ),
            "review_boundary": self._validate_review_boundary(candidates, groups, policy),
            "source_registry": [
                *[i for i in issues if i.check == "source_registry"],
                *self._validate_sources(
                    candidates, groups, verification, source_manifest
                ),
            ],
            "taxonomy_mappings": [
                *[i for i in issues if i.check == "taxonomy_mappings"],
                *self._validate_taxonomy(
                    candidates, groups, problem_types, concept_rows, outcome_rows
                ),
            ],
            "standalone_projection": self._validate_standalone(candidates, standalone),
            "question_groups": self._validate_groups(candidates, standalone, groups),
            "coverage": self._validate_coverage(candidates, coverage, problem_types),
            "review_queue": self._validate_review_queue(
                effective_candidates, review_rows
            ),
            "visual_and_rights_boundary": self._validate_visual_boundary(
                path, candidates, policy, source_manifest
            ),
            "oxyz_boundary": self._validate_oxyz_boundary(candidates, standalone, groups, policy),
        }
        all_issues = list(issues)
        for name, errors in check_errors.items():
            if name != "required_files":
                all_issues.extend(errors)
        checks = {name: not errors for name, errors in check_errors.items()}
        counts = {
            "raw": self._derive_counts(
                candidates, standalone, groups, holds, problem_types
            ),
            "scope": {
                "excluded": len(EXPECTED_EXCLUDED_IDS),
                "boundary_holds": len(EXPECTED_BOUNDARY_HOLD_IDS),
            },
            "effective": self._derive_effective_counts(
                effective_candidates, effective_standalone, groups, problem_types
            ),
        }
        ordered = tuple(sorted(set(all_issues)))
        gaps = stats.get("problem_type_gaps", [])
        try:
            aggregate_sha256 = self.aggregate_semantic_sha256(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            aggregate_sha256 = None
        return VectorMaterializationReport(
            dataset_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts=counts,
            aggregate_semantic_sha256=aggregate_sha256,
            problem_type_gaps=tuple(gaps) if isinstance(gaps, list) else (),
            rights_status=source_manifest.get("rights_status"),
            errors=ordered,
        )

    @staticmethod
    def semantic_sha256(value: Any) -> str:
        payload = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def aggregate_semantic_sha256(cls, path: Path) -> str:
        """Hash canonical semantic files in the contract-defined order."""
        digest = hashlib.sha256()
        for name in SEMANTIC_FILES:
            value = json.loads((path / name).read_text(encoding="utf-8"))
            canonical = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(canonical)
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _add(
        errors: list[VectorMaterializationIssue],
        check: str,
        code: str,
        location: str,
        message: str,
    ) -> None:
        errors.append(VectorMaterializationIssue(check, code, location, message))

    @classmethod
    def _load_json(
        cls,
        path: Path,
        errors: list[VectorMaterializationIssue],
        check: str = "required_files",
    ) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            cls._add(errors, check, "INVALID_OR_MISSING_JSON", path.as_posix(), str(error))
            return None

    @classmethod
    def _load_object(
        cls,
        path: Path,
        errors: list[VectorMaterializationIssue],
        check: str = "required_files",
    ) -> dict[str, Any]:
        value = cls._load_json(path, errors, check)
        if value is not None and not isinstance(value, dict):
            cls._add(errors, check, "INVALID_JSON_SHAPE", path.as_posix(), "Expected object.")
        return value if isinstance(value, dict) else {}

    @classmethod
    def _load_list(
        cls,
        path: Path,
        errors: list[VectorMaterializationIssue],
        check: str = "required_files",
    ) -> list[dict[str, Any]]:
        value = cls._load_json(path, errors, check)
        valid = isinstance(value, list) and all(isinstance(row, dict) for row in value)
        if value is not None and not valid:
            cls._add(errors, check, "INVALID_JSON_SHAPE", path.as_posix(), "Expected object array.")
        return value if valid else []

    @classmethod
    def _load_review_queue(
        cls, path: Path, errors: list[VectorMaterializationIssue]
    ) -> list[dict[str, str]]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))
        except (OSError, csv.Error) as error:
            cls._add(errors, "required_files", "INVALID_OR_MISSING_CSV", path.as_posix(), str(error))
            return []

    @classmethod
    def _validate_manifest(
        cls, manifest: dict[str, Any], stats: dict[str, Any]
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        expected = {
            "dataset_code": "DATA-MATH12-016",
            "dataset_name": "MATH12_VECTOR_MATERIALIZATION_V0_1",
            "base_commit": EXPECTED_BASE_COMMIT,
            "status": "STRUCTURAL_REVIEW_REQUIRED",
            "chapter_code": "VECTORS_GEOMETRY",
            "subject_code": "MATH_G12",
            "source_pdf_binaries_in_repo": False,
            "db_migration_required": False,
            "canonical_curriculum_modified": False,
        }
        for field, value in expected.items():
            if manifest.get(field) != value:
                cls._add(errors, "manifest_boundary", "MANIFEST_VALUE_MISMATCH", field, f"Expected {value!r}.")
        if manifest.get("counts") != EXPECTED_COUNTS or stats != EXPECTED_COUNTS:
            cls._add(
                errors, "manifest_boundary", "SUPPLIED_STATS_MISMATCH", "counts",
                "Manifest counts and extraction_stats.json must match the locked DATA-016 counts.",
            )
        return errors

    @classmethod
    def _validate_semantic_hashes(
        cls, path: Path, manifest: dict[str, Any]
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        supplied = manifest.get("semantic_file_hashes")
        if not isinstance(supplied, dict) or set(supplied) != set(SEMANTIC_FILES):
            cls._add(errors, "semantic_hashes", "SEMANTIC_FILE_SET_MISMATCH", "materialization_manifest.json", repr(supplied))
            return errors
        for name in SEMANTIC_FILES:
            try:
                value = json.loads((path / name).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                cls._add(errors, "semantic_hashes", "SEMANTIC_FILE_UNREADABLE", name, str(error))
                continue
            actual = cls.semantic_sha256(value)
            if supplied.get(name) != actual:
                cls._add(errors, "semantic_hashes", "SEMANTIC_SHA256_MISMATCH", name, f"Expected {supplied.get(name)}; found {actual}.")
        return errors

    @classmethod
    def _validate_aggregate_contract(
        cls, contract: dict[str, Any]
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        algorithm = contract.get("algorithm")
        valid = (
            contract.get("contract_code") == "MATH12_VECTOR_AGGREGATE_HASH_V0_2"
            and isinstance(algorithm, dict)
            and algorithm.get("semantic_files_order") == list(SEMANTIC_FILES)
            and algorithm.get("canonicalization")
            == "JSON parse -> json.dumps(ensure_ascii=False, sort_keys=True, separators=(',', ':'))"
            and algorithm.get("aggregate_encoding")
            == "For each file in exact listed order: UTF-8 filename + NUL + canonical JSON bytes + NUL; SHA-256 over concatenation."
        )
        if not valid:
            cls._add(
                errors,
                "aggregate_contract",
                "AGGREGATE_HASH_CONTRACT_MISMATCH",
                "aggregate_hash_contract.json",
                "Semantic file order, canonicalization, or aggregate encoding changed.",
            )
        return errors

    @classmethod
    def _validate_effective_contract(
        cls, contract: dict[str, Any]
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        expected_effective_counts = {
            key: EXPECTED_EFFECTIVE_REVIEW_COUNTS[key]
            for key in (
                "candidates",
                "standalone",
                "true_false_four_groups",
                "question_type_counts",
                "visual_required",
                "answer_detected",
                "mixed_scope_groups",
                "problem_types_total",
                "problem_types_with_candidates",
                "production_release_eligible",
            )
        }
        valid = (
            contract.get("contract_code")
            == "MATH12_VECTOR_EFFECTIVE_MATERIALIZATION_V0_1"
            and contract.get("base_commit")
            == "8ca3eef5351fc7f42954bc40084bf364016031d4"
            and contract.get("raw_counts")
            == {
                "candidates": 72,
                "standalone": 58,
                "true_false_four_groups": 14,
                "structural_holds": 0,
            }
            and contract.get("scope_overlay_counts")
            == {"excluded": 3, "boundary_holds": 1}
            and contract.get("effective_review_counts")
            == expected_effective_counts
            and contract.get("effective_projection_rule")
            == "raw candidates minus EXCLUDE_* decisions minus HOLD_* decisions"
            and contract.get("group_rule")
            == "No TRUE_FALSE_FOUR group is excluded by this overlay; all 14 remain atomic."
            and contract.get("review_queue_rule")
            == "review_queue.csv must contain exactly the 68 effective candidates once each."
        )
        if not valid:
            cls._add(
                errors,
                "effective_contract",
                "EFFECTIVE_MATERIALIZATION_CONTRACT_MISMATCH",
                "effective_materialization_contract.json",
                "Raw/effective counts or explicit projection rules changed.",
            )
        return errors

    @classmethod
    def _validate_aggregate_integrity(
        cls, path: Path, manifest: dict[str, Any]
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        try:
            actual = cls.aggregate_semantic_sha256(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            cls._add(
                errors,
                "aggregate_integrity",
                "AGGREGATE_SEMANTIC_INPUT_INVALID",
                "semantic_files",
                str(error),
            )
            return errors
        declared = manifest.get("aggregate_semantic_sha256")
        if actual != declared or actual != EXPECTED_AGGREGATE_SEMANTIC_SHA256:
            cls._add(
                errors,
                "aggregate_integrity",
                "AGGREGATE_SEMANTIC_SHA256_MISMATCH",
                "materialization_manifest.json.aggregate_semantic_sha256",
                (
                    f"Recomputed {actual}; manifest declares {declared}; "
                    f"expected {EXPECTED_AGGREGATE_SEMANTIC_SHA256}."
                ),
            )
        return errors

    @classmethod
    def _validate_counts(
        cls,
        candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        holds: list[dict[str, Any]],
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        actual = {
            "candidates": len(candidates), "standalone": len(standalone),
            "groups": len(groups), "holds": len(holds),
            "types": dict(Counter(row.get("question_type_detected") for row in candidates)),
            "visual": sum(row.get("visual_required") is True for row in candidates),
            "answers": sum(row.get("answer_detected") is not None for row in candidates),
            "mixed": sum(row.get("mixed_scope") is True for row in groups),
        }
        expected = {
            "candidates": 72, "standalone": 58, "groups": 14, "holds": 0,
            "types": EXPECTED_COUNTS["question_type_counts"], "visual": 53,
            "answers": 47, "mixed": 12,
        }
        if actual != expected:
            cls._add(errors, "exact_counts", "MATERIALIZATION_COUNTS_MISMATCH", "dataset", f"Expected {expected}; found {actual}.")
        occurrences = Counter(
            occurrence.get("source_code")
            for row in candidates
            for occurrence in row.get("duplicate_occurrences", [])
            if isinstance(occurrence, dict)
        )
        selected = Counter(row.get("source_code") for row in candidates)
        if dict(selected) != EXPECTED_COUNTS["selected_source_counts"] or dict(occurrences) != EXPECTED_COUNTS["all_provenance_occurrence_counts"]:
            cls._add(errors, "exact_counts", "SOURCE_COUNTS_MISMATCH", "candidate_questions.json", f"Selected={dict(selected)}; occurrences={dict(occurrences)}.")
        return errors

    @classmethod
    def _validate_scope_overlay(
        cls,
        candidates: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        overlay: dict[str, Any],
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        decisions = overlay.get("decisions")
        if not isinstance(decisions, list) or not all(
            isinstance(row, dict) for row in decisions
        ):
            cls._add(
                errors,
                "scope_overlay",
                "INVALID_SCOPE_DECISIONS",
                "scope_review_overrides.json.decisions",
                "Scope decisions must be an array of objects.",
            )
            return errors
        ids = [row.get("candidate_id") for row in decisions]
        actual = {row.get("candidate_id"): row.get("decision") for row in decisions}
        raw_ids = {row.get("candidate_id") for row in candidates}
        group_source_ids = {row.get("source_candidate_id") for row in groups}
        policy = overlay.get("policy")
        required_policy = {
            "preserve_raw_candidate_ids": True,
            "preserve_raw_dedupe_hashes": True,
            "do_not_rewrite_source_provenance": True,
            "do_not_mark_verified": True,
            "do_not_mark_approved": True,
            "do_not_import_database": True,
            "effective_academic_review_projection_only": True,
        }
        if (
            overlay.get("overlay_code")
            != "MATH12_VECTOR_SCOPE_REVIEW_OVERRIDES_V0_1"
            or overlay.get("base_commit")
            != "8ca3eef5351fc7f42954bc40084bf364016031d4"
            or overlay.get("raw_materialization_dataset") != "DATA-MATH12-016"
            or policy != required_policy
        ):
            cls._add(
                errors,
                "scope_overlay",
                "SCOPE_OVERLAY_METADATA_MISMATCH",
                "scope_review_overrides.json",
                "Scope overlay identity or safety policy changed.",
            )
        if len(ids) != len(set(ids)):
            cls._add(
                errors,
                "scope_overlay",
                "DUPLICATE_SCOPE_DECISION",
                "scope_review_overrides.json.decisions",
                "Each raw candidate may have at most one scope decision.",
            )
        if any(candidate_id not in raw_ids for candidate_id in ids):
            cls._add(
                errors,
                "scope_overlay",
                "UNKNOWN_SCOPE_CANDIDATE",
                "scope_review_overrides.json.decisions",
                "Every overlay candidate ID must resolve in raw materialization.",
            )
        if actual != EXPECTED_SCOPE_DECISIONS:
            cls._add(
                errors,
                "scope_overlay",
                "SCOPE_DECISION_SET_MISMATCH",
                "scope_review_overrides.json.decisions",
                f"Expected {EXPECTED_SCOPE_DECISIONS}; found {actual}.",
            )
        if set(ids) & group_source_ids:
            cls._add(
                errors,
                "scope_overlay",
                "QUESTION_GROUP_SCOPE_DECISION_FORBIDDEN",
                "scope_review_overrides.json.decisions",
                "This overlay must preserve all 14 QuestionGroups.",
            )
        return errors

    @classmethod
    def _validate_effective_projection(
        cls,
        candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        overlay: dict[str, Any],
        effective_candidates: list[dict[str, Any]],
        effective_standalone: list[dict[str, Any]],
        effective_stats: dict[str, Any],
        scope_report: dict[str, Any],
        problem_types: list[dict[str, Any]],
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        decisions = overlay.get("decisions", [])
        blocked_ids = {
            row.get("candidate_id")
            for row in decisions
            if isinstance(row, dict)
        }
        expected_candidates = [
            row for row in candidates if row.get("candidate_id") not in blocked_ids
        ]
        expected_standalone = [
            row for row in standalone if row.get("candidate_id") not in blocked_ids
        ]
        if effective_candidates != expected_candidates:
            cls._add(
                errors,
                "effective_projection",
                "EFFECTIVE_CANDIDATE_PROJECTION_MISMATCH",
                "effective_candidates.json",
                "Effective candidates must equal raw candidates minus explicit overlay IDs.",
            )
        if effective_standalone != expected_standalone:
            cls._add(
                errors,
                "effective_projection",
                "EFFECTIVE_STANDALONE_PROJECTION_MISMATCH",
                "effective_standalone_candidates.json",
                "Effective standalone rows must be the exact filtered raw projection.",
            )
        effective_counts = cls._derive_effective_counts(
            effective_candidates, effective_standalone, groups, problem_types
        )
        if effective_counts != EXPECTED_EFFECTIVE_REVIEW_COUNTS:
            cls._add(
                errors,
                "effective_projection",
                "EFFECTIVE_COUNTS_MISMATCH",
                "effective_candidates.json",
                f"Expected {EXPECTED_EFFECTIVE_REVIEW_COUNTS}; found {effective_counts}.",
            )
        expected_stats = {
            "materialization_code": "MATH12_VECTOR_EFFECTIVE_REVIEW_V0_1",
            "status": "STRUCTURAL_REVIEW_REQUIRED",
            "raw_counts": {
                "candidates": 72,
                "standalone": 58,
                "true_false_four_groups": 14,
                "structural_holds": 0,
            },
            "scope_overlay_counts": {"excluded": 3, "boundary_holds": 1},
            "effective_review_counts": EXPECTED_EFFECTIVE_REVIEW_COUNTS,
            "academic_review_complete": False,
            "database_import_allowed": False,
            "canonical_snapshot_allowed": False,
        }
        if effective_stats != expected_stats:
            cls._add(
                errors,
                "effective_projection",
                "EFFECTIVE_STATS_MISMATCH",
                "effective_review_stats.json",
                "Effective stats must preserve the raw/effective count distinction.",
            )
        expected_report = {
            "overlay_code": "MATH12_VECTOR_SCOPE_REVIEW_OVERRIDES_V0_1",
            "status": "PASS",
            "raw_candidate_count": 72,
            "raw_standalone_count": 58,
            "decision_counts": {"excluded": 3, "boundary_holds": 1},
            "excluded_candidate_ids": list(EXPECTED_EXCLUDED_IDS),
            "boundary_hold_candidate_ids": list(EXPECTED_BOUNDARY_HOLD_IDS),
            "effective_candidate_count": 68,
            "effective_standalone_count": 54,
            "preserved_question_group_count": 14,
            "preserved_mixed_scope_group_count": 12,
            "raw_materialization_modified": False,
            "academic_review_started": False,
            "production_release_eligible": 0,
            "raw_candidate_semantic_sha256": (
                "1b364f145fcd6110ba99ee32dc91928a5d3909eac3347e315c40bd7e73fee1ab"
            ),
        }
        if scope_report != expected_report:
            cls._add(
                errors,
                "effective_projection",
                "SCOPE_REVIEW_REPORT_MISMATCH",
                "scope_review_report.json",
                "Scope review report does not match the explicit overlay projection.",
            )
        return errors

    @classmethod
    def _validate_candidate_identity(
        cls, candidates: list[dict[str, Any]]
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        ids = [row.get("candidate_id") for row in candidates]
        hashes = [row.get("dedupe_hash") for row in candidates]
        pattern = re.compile(r"^M12_VECTOR_CAND_\d{4}$")
        if any(not isinstance(value, str) or pattern.fullmatch(value) is None for value in ids):
            cls._add(errors, "candidate_identity", "INVALID_CANDIDATE_ID", "candidate_questions.json", "All IDs must match M12_VECTOR_CAND_####.")
        if len(ids) != len(set(ids)):
            cls._add(errors, "candidate_identity", "DUPLICATE_CANDIDATE_ID", "candidate_questions.json", "Candidate IDs must be unique.")
        if any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None for value in hashes) or len(hashes) != len(set(hashes)):
            cls._add(errors, "candidate_identity", "INVALID_OR_DUPLICATE_DEDUPE_HASH", "candidate_questions.json", "Canonical dedupe hashes must be unique SHA-256 values.")
        return errors

    @classmethod
    def _validate_review_boundary(
        cls,
        candidates: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        required_policy = {
            "candidate_status": "STRUCTURAL_CANDIDATE",
            "academic_review_status": "NOT_REVIEWED",
            "production_release_eligible": False,
        }
        if any(policy.get(field) != value for field, value in required_policy.items()):
            cls._add(errors, "review_boundary", "INVALID_REVIEW_POLICY", "materialization_policy.json", repr(required_policy))
        promotion = policy.get("promotion_policy")
        if not isinstance(promotion, dict) or any(promotion.get(field) is not False for field in ("verified_allowed", "approved_allowed", "database_import_allowed", "canonical_snapshot_allowed")):
            cls._add(errors, "review_boundary", "PROMOTION_POLICY_ENABLED", "materialization_policy.json", "All promotion paths must remain disabled.")
        for index, row in enumerate(candidates):
            location = f"candidate_questions.json[{index}]"
            if (
                row.get("status") != "STRUCTURAL_CANDIDATE"
                or row.get("academic_review_status") != "NOT_REVIEWED"
                or row.get("promotion_eligible") is not False
                or row.get("classification_method") != "RULE_BASED_INITIAL_FROM_SOURCE_TEXT"
            ):
                cls._add(errors, "review_boundary", "CANDIDATE_REVIEW_BOUNDARY_VIOLATION", location, str(row.get("candidate_id")))
            if "correct_answer" in row or "verified_answer" in row:
                cls._add(errors, "review_boundary", "DETECTED_ANSWER_PROMOTED", location, "Detected evidence cannot become a trusted answer field.")
        for index, group in enumerate(groups):
            if group.get("source_review_status") != "STRUCTURAL_CANDIDATE" or group.get("answer_status") != "NOT_REVIEWED" or group.get("child_taxonomy_status") != "NOT_REVIEWED":
                cls._add(errors, "review_boundary", "GROUP_REVIEW_BOUNDARY_VIOLATION", f"question_group_candidates.json[{index}]", str(group.get("group_candidate_id")))
        return errors

    @classmethod
    def _validate_sources(
        cls,
        candidates: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        verification: dict[str, Any],
        source_manifest: dict[str, Any],
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        manifest_sources = {
            row.get("source_key"): row
            for row in source_manifest.get("primary_sources", [])
            if isinstance(row, dict)
        }
        supplied = verification.get("sources")
        if verification.get("status") != "PASS_LOCAL_SHA256" or not isinstance(supplied, dict):
            cls._add(errors, "source_registry", "INVALID_SOURCE_VERIFICATION", "source_hash_verification.json", repr(verification.get("status")))
            supplied = {}
        for source_code, lock in EXPECTED_SOURCE_LOCKS.items():
            verified = supplied.get(source_code, {})
            registered = manifest_sources.get(lock["source_key"], {})
            if (
                verified.get("drive_file_id") != lock["file_id"]
                or verified.get("sha256") != lock["sha256"]
                or verified.get("page_count") != lock["page_count"]
                or registered.get("drive_file_id") != lock["file_id"]
                or registered.get("sha256") != lock["sha256"]
            ):
                cls._add(errors, "source_registry", "SOURCE_LOCK_MISMATCH", source_code, "DATA-015 source identity/SHA/page lock changed.")

        def validate_reference(row: dict[str, Any], location: str) -> None:
            lock = EXPECTED_SOURCE_LOCKS.get(row.get("source_code"))
            if lock is None:
                cls._add(errors, "source_registry", "UNKNOWN_SOURCE", location, repr(row.get("source_code")))
                return
            if row.get("source_key") != lock["source_key"] or row.get("source_file_id") != lock["file_id"] or row.get("source_sha256") != lock["sha256"]:
                cls._add(errors, "source_registry", "SOURCE_REFERENCE_MISMATCH", location, "Source key, file ID or SHA does not match its lock.")
            page = row.get("source_page")
            if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= lock["page_count"]:
                cls._add(errors, "source_registry", "SOURCE_PAGE_OUT_OF_RANGE", location, repr(page))

        for index, row in enumerate(candidates):
            validate_reference(row, f"candidate_questions.json[{index}]")
            occurrences = row.get("duplicate_occurrences")
            if not isinstance(occurrences, list) or not occurrences:
                cls._add(errors, "source_registry", "MISSING_PROVENANCE_OCCURRENCES", f"candidate_questions.json[{index}]", "At least the canonical source occurrence is required.")
                continue
            for occurrence_index, occurrence in enumerate(occurrences):
                if isinstance(occurrence, dict):
                    validate_reference(occurrence, f"candidate_questions.json[{index}].duplicate_occurrences[{occurrence_index}]")
                else:
                    cls._add(errors, "source_registry", "INVALID_PROVENANCE_OCCURRENCE", f"candidate_questions.json[{index}].duplicate_occurrences[{occurrence_index}]", repr(occurrence))
        for index, row in enumerate(groups):
            validate_reference(row, f"question_group_candidates.json[{index}]")
        return errors

    @classmethod
    def _validate_taxonomy(
        cls,
        candidates: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        problem_types: list[dict[str, Any]],
        concept_rows: list[dict[str, Any]],
        outcome_rows: list[dict[str, Any]],
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        codes = {row.get("code") for row in problem_types}
        concepts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        outcomes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in concept_rows:
            concepts[str(row.get("problem_type_code"))].append(row)
        for row in outcome_rows:
            outcomes[str(row.get("problem_type_code"))].append(row)
        for index, row in enumerate(candidates):
            code = row.get("problem_type_code")
            if code not in codes:
                cls._add(errors, "taxonomy_mappings", "UNKNOWN_PROBLEM_TYPE", f"candidate_questions.json[{index}]", repr(code))
            if row.get("concepts") != concepts.get(str(code), []) or row.get("learning_outcomes") != outcomes.get(str(code), []):
                cls._add(errors, "taxonomy_mappings", "TAXONOMY_MAPPING_MISMATCH", f"candidate_questions.json[{index}]", str(row.get("candidate_id")))
        for index, row in enumerate(groups):
            code = row.get("problem_type_code")
            if row.get("parent_concepts") != concepts.get(str(code), []) or row.get("parent_learning_outcomes") != outcomes.get(str(code), []):
                cls._add(errors, "taxonomy_mappings", "GROUP_TAXONOMY_MAPPING_MISMATCH", f"question_group_candidates.json[{index}]", str(row.get("group_candidate_id")))
        return errors

    @classmethod
    def _validate_standalone(
        cls, candidates: list[dict[str, Any]], standalone: list[dict[str, Any]]
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        candidate_by_id = {row.get("candidate_id"): row for row in candidates}
        ids = [row.get("candidate_id") for row in standalone]
        if len(ids) != len(set(ids)):
            cls._add(errors, "standalone_projection", "DUPLICATE_STANDALONE_ID", "standalone_candidates.json", "Standalone IDs must be unique.")
        for index, row in enumerate(standalone):
            candidate_id = row.get("candidate_id")
            if row.get("question_type_detected") not in {"MULTIPLE_CHOICE", "SHORT_ANSWER"} or row.get("requires_question_group_model") is not False:
                cls._add(errors, "standalone_projection", "INVALID_STANDALONE_TYPE", f"standalone_candidates.json[{index}]", str(candidate_id))
            if candidate_by_id.get(candidate_id) != row:
                cls._add(errors, "standalone_projection", "STANDALONE_NOT_EXACT_PROJECTION", f"standalone_candidates.json[{index}]", str(candidate_id))
        expected = {row.get("candidate_id") for row in candidates if row.get("requires_question_group_model") is False}
        if set(ids) != expected:
            cls._add(errors, "standalone_projection", "STANDALONE_SET_MISMATCH", "standalone_candidates.json", "Standalone rows must be exactly the non-group candidates.")
        return errors

    @classmethod
    def _validate_groups(
        cls,
        candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        candidate_by_id = {row.get("candidate_id"): row for row in candidates}
        standalone_ids = {row.get("candidate_id") for row in standalone}
        group_ids = [row.get("group_candidate_id") for row in groups]
        source_ids = [row.get("source_candidate_id") for row in groups]
        if len(group_ids) != len(set(group_ids)) or len(source_ids) != len(set(source_ids)):
            cls._add(errors, "question_groups", "DUPLICATE_GROUP_OR_SOURCE_ID", "question_group_candidates.json", "Group IDs and source candidate links must be one-to-one.")
        for index, row in enumerate(groups):
            location = f"question_group_candidates.json[{index}]"
            source = candidate_by_id.get(row.get("source_candidate_id"))
            if source is None or source.get("requires_question_group_model") is not True or source.get("question_type_detected") != "TRUE_FALSE_GROUP":
                cls._add(errors, "question_groups", "INVALID_GROUP_SOURCE", location, repr(row.get("source_candidate_id")))
                continue
            if row.get("source_candidate_id") in standalone_ids:
                cls._add(errors, "question_groups", "GROUP_SOURCE_IN_STANDALONE", location, str(row.get("source_candidate_id")))
            if row.get("group_type") != "TRUE_FALSE_FOUR" or not isinstance(row.get("group_context"), str) or not row.get("group_context", "").strip():
                cls._add(errors, "question_groups", "INVALID_GROUP_STRUCTURE", location, str(row.get("group_candidate_id")))
            items = row.get("items")
            if not isinstance(items, list) or len(items) != 4:
                cls._add(errors, "question_groups", "INVALID_GROUP_ITEMS", location, "Exactly four items are required.")
                continue
            if [item.get("label") for item in items if isinstance(item, dict)] != ["a", "b", "c", "d"] or [item.get("order_index") for item in items if isinstance(item, dict)] != [0, 1, 2, 3]:
                cls._add(errors, "question_groups", "INVALID_GROUP_ITEM_ORDER", location, "Expected a,b,c,d at indexes 0,1,2,3.")
            for child_index, item in enumerate(items):
                if not isinstance(item, dict) or item.get("correct_answer") is not None or item.get("answer_status") != "UNREVIEWED" or item.get("taxonomy_status") != "NOT_REVIEWED" or not isinstance(item.get("content"), str) or not item.get("content", "").strip():
                    cls._add(errors, "question_groups", "INVALID_UNREVIEWED_CHILD", f"{location}.items[{child_index}]", "Child must preserve text with null answer and unreviewed statuses.")
            mirrored = (
                row.get("source_code") == source.get("source_code")
                and row.get("source_key") == source.get("source_key")
                and row.get("source_file_id") == source.get("source_file_id")
                and row.get("source_sha256") == source.get("source_sha256")
                and row.get("source_page") == source.get("source_page")
                and row.get("dedupe_hash") == source.get("dedupe_hash")
                and row.get("mixed_scope") == source.get("mixed_scope")
            )
            if not mirrored:
                cls._add(errors, "question_groups", "GROUP_SOURCE_LINEAGE_MISMATCH", location, str(row.get("group_candidate_id")))
        expected_sources = {row.get("candidate_id") for row in candidates if row.get("requires_question_group_model") is True}
        if set(source_ids) != expected_sources:
            cls._add(errors, "question_groups", "GROUP_SOURCE_SET_MISMATCH", "question_group_candidates.json", "Every group candidate must materialize once and only once.")
        return errors

    @classmethod
    def _validate_coverage(
        cls,
        candidates: list[dict[str, Any]],
        coverage: list[dict[str, Any]],
        problem_types: list[dict[str, Any]],
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        pt_by_code = {row.get("code"): row for row in problem_types}
        coverage_by_code = {row.get("problem_type_code"): row for row in coverage}
        if len(coverage) != 15 or set(coverage_by_code) != set(pt_by_code):
            cls._add(errors, "coverage", "COVERAGE_PROBLEM_TYPE_SET_MISMATCH", "coverage_report.json", "Coverage must report all 15 DATA-015 ProblemTypes.")
            return errors
        for code in pt_by_code:
            rows = [row for row in candidates if row.get("problem_type_code") == code]
            actual = {
                "candidate_count": len(rows),
                "multiple_choice_count": sum(row.get("question_type_detected") == "MULTIPLE_CHOICE" for row in rows),
                "true_false_group_count": sum(row.get("question_type_detected") == "TRUE_FALSE_GROUP" for row in rows),
                "short_answer_count": sum(row.get("question_type_detected") == "SHORT_ANSWER" for row in rows),
                "mixed_scope_count": sum(row.get("mixed_scope") is True for row in rows),
                "visual_required_count": sum(row.get("visual_required") is True for row in rows),
                "coverage_status": "HAS_CANDIDATES" if rows else "GAP",
            }
            supplied = coverage_by_code[code]
            if supplied.get("problem_type_name") != pt_by_code[code].get("name") or any(supplied.get(field) != value for field, value in actual.items()):
                cls._add(errors, "coverage", "COVERAGE_ROW_MISMATCH", code, f"Expected {actual}.")
        gaps = [row.get("problem_type_code") for row in coverage if row.get("coverage_status") == "GAP"]
        if gaps != EXPECTED_COUNTS["problem_type_gaps"]:
            cls._add(errors, "coverage", "PROBLEM_TYPE_GAPS_MISMATCH", "coverage_report.json", repr(gaps))
        return errors

    @classmethod
    def _validate_review_queue(
        cls, candidates: list[dict[str, Any]], rows: list[dict[str, str]]
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        candidate_by_id = {row.get("candidate_id"): row for row in candidates}
        ids = [row.get("candidate_id") for row in rows]
        if (
            len(rows) != len(candidates)
            or len(ids) != len(set(ids))
            or set(ids) != set(candidate_by_id)
        ):
            cls._add(
                errors,
                "review_queue",
                "REVIEW_QUEUE_SET_MISMATCH",
                "review_queue.csv",
                (
                    "Review queue must contain each effective candidate exactly once; "
                    f"expected {len(candidates)} rows."
                ),
            )
        for index, row in enumerate(rows):
            candidate = candidate_by_id.get(row.get("candidate_id"))
            if candidate and (
                row.get("source_code") != candidate.get("source_code")
                or row.get("problem_type_code") != candidate.get("problem_type_code")
                or row.get("question_type") != candidate.get("question_type_detected")
                or row.get("academic_review_status") != "NOT_REVIEWED"
            ):
                cls._add(errors, "review_queue", "REVIEW_QUEUE_ROW_MISMATCH", f"review_queue.csv[{index}]", str(row.get("candidate_id")))
        return errors

    @classmethod
    def _validate_visual_boundary(
        cls,
        path: Path,
        candidates: list[dict[str, Any]],
        policy: dict[str, Any],
        source_manifest: dict[str, Any],
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        visual = policy.get("visual_policy")
        if (
            not isinstance(visual, dict)
            or visual.get("visual_required_is_preflight_only") is not True
            or visual.get("crop_or_redraw_in_this_phase") is not False
            or visual.get("rights_status") != "REVIEW_REQUIRED"
            or source_manifest.get("rights_status") != "REVIEW_REQUIRED"
        ):
            cls._add(errors, "visual_and_rights_boundary", "INVALID_VISUAL_OR_RIGHTS_POLICY", "materialization_policy.json", "Visual work is deferred and rights must stay REVIEW_REQUIRED.")
        if any(file.suffix.lower() == ".pdf" for file in path.rglob("*")):
            cls._add(errors, "visual_and_rights_boundary", "SOURCE_PDF_PRESENT", path.as_posix(), "Source PDFs must not be committed.")
        if sum(row.get("visual_required") is True for row in candidates) != 53:
            cls._add(errors, "visual_and_rights_boundary", "VISUAL_REQUIRED_COUNT_MISMATCH", "candidate_questions.json", "Expected 53 visual preflight flags.")
        return errors

    @classmethod
    def _validate_oxyz_boundary(
        cls,
        candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> list[VectorMaterializationIssue]:
        errors: list[VectorMaterializationIssue] = []
        expected = "Standalone candidates whose primary intent is plane/line/sphere must not enter vector corpus. Mixed TRUE_FALSE_FOUR may remain only with mixed_scope=true."
        if policy.get("oxyz_boundary") != expected:
            cls._add(errors, "oxyz_boundary", "OXYZ_POLICY_MISMATCH", "materialization_policy.json", repr(policy.get("oxyz_boundary")))
        if any(row.get("mixed_scope") is True for row in standalone):
            cls._add(errors, "oxyz_boundary", "MIXED_SCOPE_STANDALONE", "standalone_candidates.json", "Only atomic TRUE_FALSE_FOUR groups may cross the boundary.")
        mixed_candidate_ids = {row.get("candidate_id") for row in candidates if row.get("mixed_scope") is True}
        mixed_group_source_ids = {row.get("source_candidate_id") for row in groups if row.get("mixed_scope") is True}
        if mixed_candidate_ids != mixed_group_source_ids or len(mixed_group_source_ids) != 12:
            cls._add(errors, "oxyz_boundary", "MIXED_SCOPE_GROUP_SET_MISMATCH", "question_group_candidates.json", "The 12 mixed-scope candidates must remain complete groups.")
        return errors

    @staticmethod
    def _derive_counts(
        candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        holds: list[dict[str, Any]],
        problem_types: list[dict[str, Any]],
    ) -> dict[str, Any]:
        covered = {row.get("problem_type_code") for row in candidates}
        return {
            "raw_included_occurrences": sum(
                len(row.get("duplicate_occurrences", [])) for row in candidates
                if isinstance(row.get("duplicate_occurrences"), list)
            ),
            "materialized_unique_candidates": len(candidates),
            "standalone_candidates": len(standalone),
            "true_false_four_groups": len(groups),
            "structural_holds": len(holds),
            "question_type_counts": dict(Counter(row.get("question_type_detected") for row in candidates)),
            "visual_required_count": sum(row.get("visual_required") is True for row in candidates),
            "answer_detected_count": sum(row.get("answer_detected") is not None for row in candidates),
            "mixed_scope_group_count": sum(row.get("mixed_scope") is True for row in groups),
            "problem_types_total": len(problem_types),
            "problem_types_with_candidates": len(covered),
            "production_release_eligible": sum(row.get("promotion_eligible") is True for row in candidates),
        }

    @staticmethod
    def _derive_effective_counts(
        candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        problem_types: list[dict[str, Any]],
    ) -> dict[str, Any]:
        covered = {row.get("problem_type_code") for row in candidates}
        all_problem_types = [row.get("code") for row in problem_types]
        return {
            "candidates": len(candidates),
            "standalone": len(standalone),
            "true_false_four_groups": len(groups),
            "question_type_counts": dict(
                Counter(row.get("question_type_detected") for row in candidates)
            ),
            "visual_required": sum(
                row.get("visual_required") is True for row in candidates
            ),
            "answer_detected": sum(
                row.get("answer_detected") is not None for row in candidates
            ),
            "mixed_scope_groups": sum(
                row.get("mixed_scope") is True for row in groups
            ),
            "problem_types_total": len(problem_types),
            "problem_types_with_candidates": len(covered),
            "problem_type_gaps": [
                code for code in all_problem_types if code not in covered
            ],
            "verified": sum(
                row.get("academic_review_status") == "VERIFIED"
                for row in candidates
            ),
            "approved": sum(row.get("status") == "APPROVED" for row in candidates),
            "production_release_eligible": sum(
                row.get("promotion_eligible") is True for row in candidates
            ),
        }
