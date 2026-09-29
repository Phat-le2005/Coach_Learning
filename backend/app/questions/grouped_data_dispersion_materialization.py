from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.curriculum.grouped_data_dispersion_staging import (
    DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH,
    EXPECTED_PROBLEM_TYPE_CODES,
)
from app.questions.grouped_data_dispersion_source_staging import (
    DEFAULT_GROUPED_DATA_DISPERSION_SOURCE_PATH,
)


DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "grouped_data_dispersion_v0_1"
    / "staging"
    / "materialized_v0_1"
)
EXPECTED_BASE_COMMIT = "2de36e8b5c4e49c807b03c3c2b1ea7f00cfab976"
EXPECTED_AGGREGATE_SEMANTIC_SHA256 = (
    "d2d4d73ce06eaa7da40db0ad44904e1fd1f6308bd78ad36f292bf393ef881fd7"
)
SEMANTIC_FILES = (
    "candidate_questions.json",
    "standalone_candidates.json",
    "question_group_candidates.json",
    "structural_holds.json",
    "coverage_report.json",
    "extraction_stats.json",
    "source_hash_verification.json",
    "materialization_policy.json",
)
REQUIRED_FILES = (
    *SEMANTIC_FILES,
    "aggregate_hash_contract.json",
    "materialization_manifest.json",
    "review_queue.csv",
    "README.md",
)
EXPECTED_PROBLEM_TYPE_COVERAGE = {
    "CALCULATE_GROUPED_IQR": 11,
    "CALCULATE_GROUPED_RANGE": 7,
    "CALCULATE_GROUPED_STANDARD_DEVIATION": 14,
    "CALCULATE_GROUPED_VARIANCE": 5,
    "COMPARE_GROUPED_IQR": 1,
    "COMPARE_GROUPED_RANGE": 1,
    "COMPARE_GROUPED_VARIANCE_SD": 2,
}
EXPECTED_PROBLEM_TYPE_GAPS = (
    "IDENTIFY_MORE_STABLE_GROUPED_DATA",
    "INTERPRET_GROUPED_DISPERSION_MEASURE",
    "CONCLUDE_FROM_GROUPED_DISPERSION",
    "PARAMETER_FROM_GROUPED_VARIANCE_SD",
    "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS",
)
EXPECTED_SELECTED_SOURCE_COUNTS = {
    "NGOC_VY_40_DE_2026": 31,
    "PROVINCIAL_TRIAL_2025": 10,
}
EXPECTED_PROVENANCE_OCCURRENCE_COUNTS = {
    "NGOC_VY_40_DE_2026": 60,
    "PROVINCIAL_TRIAL_2025": 20,
}
EXPECTED_SOURCE_CODES = {
    "NGOC_VY_40_DE_2026": "SRC_NGOC_VY_40_DE_2026",
    "PROVINCIAL_TRIAL_2025": "SRC_PROVINCIAL_TRIAL_2025_COLLECTION",
}
EXPECTED_COUNTS: dict[str, Any] = {
    "raw_dispersion_occurrences": 80,
    "materialized_unique_candidates": 41,
    "standalone_candidates": 39,
    "true_false_four_groups": 2,
    "structural_holds": 0,
    "question_type_counts": {
        "MULTIPLE_CHOICE": 39,
        "TRUE_FALSE_GROUP": 2,
    },
    "selected_source_counts": EXPECTED_SELECTED_SOURCE_COUNTS,
    "all_provenance_occurrence_counts": (
        EXPECTED_PROVENANCE_OCCURRENCE_COUNTS
    ),
    "visual_required": 40,
    "answer_detected": 38,
    "mixed_scope_groups": 2,
    "problem_types_total": 12,
    "problem_types_with_candidates": 7,
    "problem_type_gaps": list(EXPECTED_PROBLEM_TYPE_GAPS),
    "production_release_eligible": 0,
}


@dataclass(frozen=True, slots=True, order=True)
class GroupedDataDispersionMaterializationIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class GroupedDataDispersionMaterializationReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, Any]
    aggregate_semantic_sha256: str | None
    problem_type_coverage: dict[str, int]
    problem_type_gaps: tuple[str, ...]
    rights_status: str | None
    production_release_eligible: int
    database_import_allowed: bool
    errors: tuple[GroupedDataDispersionMaterializationIssue, ...]

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
            "problem_type_coverage": self.problem_type_coverage,
            "problem_type_gaps": list(self.problem_type_gaps),
            "rights_status": self.rights_status,
            "production_release_eligible": self.production_release_eligible,
            "database_import_allowed": self.database_import_allowed,
            "errors": [asdict(error) for error in self.errors],
        }


class GroupedDataDispersionMaterializationValidator:
    """Validate DATA-MATH12-020 without changing source artifacts or the database."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH,
        *,
        curriculum_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH,
        source_staging_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_SOURCE_PATH,
    ) -> GroupedDataDispersionMaterializationReport:
        path = dataset_path.resolve()
        issues: list[GroupedDataDispersionMaterializationIssue] = []
        self._check_required_files(path, issues)
        manifest = self._load_object(path / "materialization_manifest.json", issues)
        policy = self._load_object(path / "materialization_policy.json", issues)
        contract = self._load_object(path / "aggregate_hash_contract.json", issues)
        stats = self._load_object(path / "extraction_stats.json", issues)
        verification = self._load_object(
            path / "source_hash_verification.json", issues
        )
        candidates = self._load_list(path / "candidate_questions.json", issues)
        standalone = self._load_list(path / "standalone_candidates.json", issues)
        groups = self._load_list(path / "question_group_candidates.json", issues)
        holds = self._load_list(path / "structural_holds.json", issues)
        coverage = self._load_list(path / "coverage_report.json", issues)
        review_queue = self._load_review_queue(path / "review_queue.csv", issues)

        source_manifest = self._load_object(
            source_staging_path.resolve() / "source_manifest.json",
            issues,
            check="source_registry",
        )
        taxonomy_root = curriculum_path.resolve()
        problem_types = self._load_list(
            taxonomy_root / "problem_types.json", issues, check="taxonomy_mappings"
        )
        concept_mappings = self._load_list(
            taxonomy_root / "problem_type_concepts.json",
            issues,
            check="taxonomy_mappings",
        )
        outcome_mappings = self._load_list(
            taxonomy_root / "problem_type_learning_outcomes.json",
            issues,
            check="taxonomy_mappings",
        )

        check_errors = {
            "required_files": [issue for issue in issues if issue.check == "required_files"],
            "manifest_boundary": self._validate_manifest(manifest, stats),
            "aggregate_contract": self._validate_aggregate_contract(contract, manifest),
            "semantic_hashes": self._validate_semantic_hashes(path, manifest),
            "aggregate_integrity": self._validate_aggregate_integrity(path, manifest),
            "exact_counts": self._validate_counts(
                candidates, standalone, groups, holds
            ),
            "candidate_identity": self._validate_candidate_identity(candidates),
            "source_registry": [
                *[issue for issue in issues if issue.check == "source_registry"],
                *self._validate_sources(
                    candidates, verification, source_manifest
                ),
            ],
            "taxonomy_mappings": [
                *[issue for issue in issues if issue.check == "taxonomy_mappings"],
                *self._validate_taxonomy(
                    candidates,
                    problem_types,
                    concept_mappings,
                    outcome_mappings,
                ),
            ],
            "standalone_projection": self._validate_standalone(
                candidates, standalone
            ),
            "question_groups": self._validate_groups(
                candidates, standalone, groups
            ),
            "coverage": self._validate_coverage(
                candidates, coverage, problem_types
            ),
            "review_queue": self._validate_review_queue(candidates, review_queue),
            "review_boundary": self._validate_review_boundary(
                candidates, groups, policy
            ),
            "visual_rights_boundary": self._validate_visual_rights(
                path, candidates, policy, source_manifest
            ),
            "grade11_scope_boundary": self._validate_grade11_boundary(
                candidates, groups, policy
            ),
        }
        all_issues = list(issues)
        for name, errors in check_errors.items():
            if name != "required_files":
                all_issues.extend(errors)
        checks = {name: not errors for name, errors in check_errors.items()}
        counts = self._derive_counts(
            candidates, standalone, groups, holds, problem_types
        )
        try:
            aggregate = self.aggregate_semantic_sha256(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            aggregate = None
        return GroupedDataDispersionMaterializationReport(
            dataset_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts=counts,
            aggregate_semantic_sha256=aggregate,
            problem_type_coverage={
                code: count for code, count in EXPECTED_PROBLEM_TYPE_COVERAGE.items()
            },
            problem_type_gaps=EXPECTED_PROBLEM_TYPE_GAPS,
            rights_status=source_manifest.get("rights_status"),
            production_release_eligible=sum(
                row.get("promotion_eligible") is True for row in candidates
            ),
            database_import_allowed=False,
            errors=tuple(sorted(set(all_issues))),
        )

    @staticmethod
    def semantic_sha256(value: Any) -> str:
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @classmethod
    def aggregate_semantic_sha256(cls, path: Path) -> str:
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

    @classmethod
    def _add(
        cls,
        errors: list[GroupedDataDispersionMaterializationIssue],
        check: str,
        code: str,
        location: str,
        message: str,
    ) -> None:
        errors.append(
            GroupedDataDispersionMaterializationIssue(
                check, code, location, message
            )
        )

    @classmethod
    def _check_required_files(
        cls,
        path: Path,
        errors: list[GroupedDataDispersionMaterializationIssue],
    ) -> None:
        for name in REQUIRED_FILES:
            if not (path / name).is_file():
                cls._add(
                    errors,
                    "required_files",
                    "REQUIRED_FILE_MISSING",
                    name,
                    "Required DATA-MATH12-020 artifact is missing.",
                )

    @classmethod
    def _load_json(
        cls,
        path: Path,
        errors: list[GroupedDataDispersionMaterializationIssue],
        check: str = "required_files",
    ) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            cls._add(
                errors,
                check,
                "INVALID_OR_MISSING_JSON",
                path.as_posix(),
                str(error),
            )
            return None

    @classmethod
    def _load_object(
        cls,
        path: Path,
        errors: list[GroupedDataDispersionMaterializationIssue],
        check: str = "required_files",
    ) -> dict[str, Any]:
        value = cls._load_json(path, errors, check)
        if value is not None and not isinstance(value, dict):
            cls._add(
                errors,
                check,
                "INVALID_JSON_SHAPE",
                path.as_posix(),
                "Expected a JSON object.",
            )
        return value if isinstance(value, dict) else {}

    @classmethod
    def _load_list(
        cls,
        path: Path,
        errors: list[GroupedDataDispersionMaterializationIssue],
        check: str = "required_files",
    ) -> list[dict[str, Any]]:
        value = cls._load_json(path, errors, check)
        valid = isinstance(value, list) and all(
            isinstance(row, dict) for row in value
        )
        if value is not None and not valid:
            cls._add(
                errors,
                check,
                "INVALID_JSON_SHAPE",
                path.as_posix(),
                "Expected an array of JSON objects.",
            )
        return value if valid else []

    @classmethod
    def _load_review_queue(
        cls,
        path: Path,
        errors: list[GroupedDataDispersionMaterializationIssue],
    ) -> list[dict[str, str]]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))
        except (OSError, csv.Error) as error:
            cls._add(
                errors,
                "required_files",
                "INVALID_OR_MISSING_CSV",
                path.as_posix(),
                str(error),
            )
            return []

    @classmethod
    def _validate_manifest(
        cls, manifest: dict[str, Any], stats: dict[str, Any]
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        expected = {
            "dataset_code": "DATA-MATH12-020",
            "dataset_name": "MATH12_GROUPED_DISPERSION_MATERIALIZATION_V0_1",
            "base_commit": EXPECTED_BASE_COMMIT,
            "status": "STRUCTURAL_REVIEW_REQUIRED",
            "subject_code": "MATH_G12",
            "chapter_code": "GROUPED_DATA_DISPERSION",
            "source_pdf_binaries_in_repo": False,
            "db_migration_required": False,
            "canonical_curriculum_modified": False,
            "database_import_allowed": False,
            "canonical_snapshot_allowed": False,
            "production_release_eligible": 0,
        }
        for field, expected_value in expected.items():
            if manifest.get(field) != expected_value:
                cls._add(
                    errors,
                    "manifest_boundary",
                    "MANIFEST_VALUE_MISMATCH",
                    field,
                    f"Expected {expected_value!r}; found {manifest.get(field)!r}.",
                )
        if manifest.get("counts") != EXPECTED_COUNTS or stats != EXPECTED_COUNTS:
            cls._add(
                errors,
                "manifest_boundary",
                "SUPPLIED_STATS_MISMATCH",
                "materialization_manifest.json.counts",
                "Manifest counts and extraction_stats.json must match DATA-020.",
            )
        return errors

    @classmethod
    def _validate_aggregate_contract(
        cls, contract: dict[str, Any], manifest: dict[str, Any]
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        valid = (
            contract.get("contract_code")
            == "MATH12_GROUPED_DISPERSION_AGGREGATE_HASH_V0_1"
            and contract.get("semantic_files_order") == list(SEMANTIC_FILES)
            and manifest.get("semantic_files_order") == list(SEMANTIC_FILES)
            and contract.get("canonicalization")
            == "JSON parse -> json.dumps(ensure_ascii=False, sort_keys=True, separators=(',', ':'))"
            and contract.get("aggregate_encoding")
            == "For each file in exact listed order: UTF-8 filename + NUL + canonical JSON bytes + NUL; SHA-256 over concatenation."
        )
        if valid:
            return []
        return [
            GroupedDataDispersionMaterializationIssue(
                "aggregate_contract",
                "AGGREGATE_HASH_CONTRACT_MISMATCH",
                "aggregate_hash_contract.json",
                "Semantic file order or canonicalization contract changed.",
            )
        ]

    @classmethod
    def _validate_semantic_hashes(
        cls, path: Path, manifest: dict[str, Any]
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        supplied = manifest.get("semantic_file_hashes")
        if not isinstance(supplied, dict) or set(supplied) != set(SEMANTIC_FILES):
            cls._add(
                errors,
                "semantic_hashes",
                "SEMANTIC_FILE_SET_MISMATCH",
                "materialization_manifest.json.semantic_file_hashes",
                repr(supplied),
            )
            return errors
        for name in SEMANTIC_FILES:
            try:
                value = json.loads((path / name).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                cls._add(
                    errors,
                    "semantic_hashes",
                    "SEMANTIC_FILE_UNREADABLE",
                    name,
                    str(error),
                )
                continue
            actual = cls.semantic_sha256(value)
            if supplied.get(name) != actual:
                cls._add(
                    errors,
                    "semantic_hashes",
                    "SEMANTIC_SHA256_MISMATCH",
                    name,
                    f"Expected {supplied.get(name)}; found {actual}.",
                )
        return errors

    @classmethod
    def _validate_aggregate_integrity(
        cls, path: Path, manifest: dict[str, Any]
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        try:
            actual = cls.aggregate_semantic_sha256(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            return [
                GroupedDataDispersionMaterializationIssue(
                    "aggregate_integrity",
                    "AGGREGATE_SEMANTIC_INPUT_INVALID",
                    "semantic_files",
                    str(error),
                )
            ]
        declared = manifest.get("aggregate_semantic_sha256")
        if actual == declared == EXPECTED_AGGREGATE_SEMANTIC_SHA256:
            return []
        return [
            GroupedDataDispersionMaterializationIssue(
                "aggregate_integrity",
                "AGGREGATE_SEMANTIC_SHA256_MISMATCH",
                "materialization_manifest.json.aggregate_semantic_sha256",
                (
                    f"Recomputed {actual}; manifest declares {declared}; "
                    f"expected {EXPECTED_AGGREGATE_SEMANTIC_SHA256}."
                ),
            )
        ]

    @classmethod
    def _validate_counts(
        cls,
        candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        holds: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        actual = {
            "candidates": len(candidates),
            "standalone": len(standalone),
            "groups": len(groups),
            "holds": len(holds),
            "types": dict(
                Counter(row.get("question_type_detected") for row in candidates)
            ),
            "visual": sum(
                row.get("visual_required") is True for row in candidates
            ),
            "answers": sum(
                row.get("answer_detected") is not None for row in candidates
            ),
            "mixed_groups": sum(row.get("mixed_scope") is True for row in groups),
            "occurrences": sum(
                len(row.get("duplicate_occurrences", []))
                for row in candidates
                if isinstance(row.get("duplicate_occurrences"), list)
            ),
            "selected_sources": dict(
                Counter(row.get("source_key") for row in candidates)
            ),
            "occurrence_sources": dict(
                Counter(
                    occurrence.get("source_key")
                    for row in candidates
                    for occurrence in row.get("duplicate_occurrences", [])
                    if isinstance(occurrence, dict)
                )
            ),
        }
        expected = {
            "candidates": 41,
            "standalone": 39,
            "groups": 2,
            "holds": 0,
            "types": EXPECTED_COUNTS["question_type_counts"],
            "visual": 40,
            "answers": 38,
            "mixed_groups": 2,
            "occurrences": 80,
            "selected_sources": EXPECTED_SELECTED_SOURCE_COUNTS,
            "occurrence_sources": EXPECTED_PROVENANCE_OCCURRENCE_COUNTS,
        }
        if actual == expected:
            return []
        return [
            GroupedDataDispersionMaterializationIssue(
                "exact_counts",
                "MATERIALIZATION_COUNTS_MISMATCH",
                "dataset",
                f"Expected {expected}; found {actual}.",
            )
        ]

    @classmethod
    def _validate_candidate_identity(
        cls, candidates: list[dict[str, Any]]
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        ids = [row.get("candidate_id") for row in candidates]
        hashes = [row.get("dedupe_hash") for row in candidates]
        if any(
            not isinstance(candidate_id, str)
            or re.fullmatch(r"M12_DISP_CAND_\d{4}", candidate_id) is None
            for candidate_id in ids
        ):
            cls._add(
                errors,
                "candidate_identity",
                "INVALID_CANDIDATE_ID",
                "candidate_questions.json",
                "Candidate IDs must match M12_DISP_CAND_####.",
            )
        if len(ids) != len(set(ids)):
            cls._add(
                errors,
                "candidate_identity",
                "DUPLICATE_CANDIDATE_ID",
                "candidate_questions.json",
                "Candidate IDs must be unique.",
            )
        if (
            any(
                not isinstance(value, str)
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in hashes
            )
            or len(hashes) != len(set(hashes))
        ):
            cls._add(
                errors,
                "candidate_identity",
                "INVALID_OR_DUPLICATE_DEDUPE_HASH",
                "candidate_questions.json",
                "Dedupe hashes must be unique SHA-256 values.",
            )
        return errors

    @classmethod
    def _validate_sources(
        cls,
        candidates: list[dict[str, Any]],
        verification: dict[str, Any],
        source_manifest: dict[str, Any],
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        registered = {
            row.get("source_key"): row
            for row in source_manifest.get("primary_sources", [])
            if isinstance(row, dict)
        }
        verification_rows = verification.get("sources")
        verified = {
            row.get("source_key"): row
            for row in verification_rows
            if isinstance(row, dict)
        } if isinstance(verification_rows, list) else {}
        if verification.get("verified") is not True or set(verified) != set(registered):
            cls._add(
                errors,
                "source_registry",
                "SOURCE_VERIFICATION_SET_MISMATCH",
                "source_hash_verification.json",
                "All three DATA-019 primary sources must be verified.",
            )
        for source_key, source in registered.items():
            lock = verified.get(source_key, {})
            if (
                lock.get("drive_file_id") != source.get("drive_file_id")
                or lock.get("expected_sha256") != source.get("sha256")
                or lock.get("actual_sha256") != source.get("sha256")
                or lock.get("status") != "MATCH"
                or not isinstance(lock.get("page_count"), int)
            ):
                cls._add(
                    errors,
                    "source_registry",
                    "SOURCE_LOCK_MISMATCH",
                    str(source_key),
                    "Source ID/SHA/status differs from DATA-019.",
                )

        def validate_reference(row: dict[str, Any], location: str) -> None:
            source_key = row.get("source_key")
            source = registered.get(source_key)
            lock = verified.get(source_key)
            if source is None or lock is None:
                cls._add(
                    errors,
                    "source_registry",
                    "UNKNOWN_SOURCE",
                    location,
                    repr(source_key),
                )
                return
            if (
                row.get("source_file_id") != source.get("drive_file_id")
                or row.get("source_sha256") != source.get("sha256")
                or row.get("source_code") != EXPECTED_SOURCE_CODES.get(source_key)
            ):
                cls._add(
                    errors,
                    "source_registry",
                    "SOURCE_REFERENCE_MISMATCH",
                    location,
                    "Source code, file ID or SHA does not match its source lock.",
                )
            page = row.get("source_page")
            if (
                not isinstance(page, int)
                or isinstance(page, bool)
                or not 1 <= page <= lock.get("page_count", 0)
            ):
                cls._add(
                    errors,
                    "source_registry",
                    "SOURCE_PAGE_OUT_OF_RANGE",
                    location,
                    repr(page),
                )

        for index, candidate in enumerate(candidates):
            validate_reference(candidate, f"candidate_questions.json[{index}]")
            occurrences = candidate.get("duplicate_occurrences")
            if not isinstance(occurrences, list) or not occurrences:
                cls._add(
                    errors,
                    "source_registry",
                    "MISSING_PROVENANCE_OCCURRENCES",
                    f"candidate_questions.json[{index}]",
                    "Each materialized candidate needs retained source occurrences.",
                )
                continue
            for occurrence_index, occurrence in enumerate(occurrences):
                location = (
                    f"candidate_questions.json[{index}]."
                    f"duplicate_occurrences[{occurrence_index}]"
                )
                if isinstance(occurrence, dict):
                    validate_reference(occurrence, location)
                else:
                    cls._add(
                        errors,
                        "source_registry",
                        "INVALID_PROVENANCE_OCCURRENCE",
                        location,
                        repr(occurrence),
                    )
        if any(row.get("source_key") == "OFFICIAL_EXAM_SOLUTIONS_2025" for row in candidates):
            cls._add(
                errors,
                "source_registry",
                "OFFICIAL_Q3_ONLY_SOURCE_MATERIALIZED",
                "candidate_questions.json",
                "Official 2025 Q3-only examples must materialize zero candidates.",
            )
        return errors

    @classmethod
    def _validate_taxonomy(
        cls,
        candidates: list[dict[str, Any]],
        problem_types: list[dict[str, Any]],
        concept_rows: list[dict[str, Any]],
        outcome_rows: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        problem_type_by_code = {
            row.get("code"): row for row in problem_types
        }
        concepts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        outcomes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in concept_rows:
            concepts[str(row.get("problem_type_code"))].append(row)
        for row in outcome_rows:
            outcomes[str(row.get("problem_type_code"))].append(row)
        if set(problem_type_by_code) != EXPECTED_PROBLEM_TYPE_CODES:
            cls._add(
                errors,
                "taxonomy_mappings",
                "PROBLEM_TYPE_REGISTRY_MISMATCH",
                "problem_types.json",
                "DATA-019 ProblemType registry changed.",
            )
        for index, candidate in enumerate(candidates):
            code = candidate.get("problem_type_code")
            taxonomy = problem_type_by_code.get(code)
            location = f"candidate_questions.json[{index}]"
            if taxonomy is None:
                cls._add(
                    errors,
                    "taxonomy_mappings",
                    "UNKNOWN_PROBLEM_TYPE",
                    location,
                    repr(code),
                )
                continue
            if (
                candidate.get("problem_type_name") != taxonomy.get("name")
                or candidate.get("concepts") != concepts.get(str(code), [])
                or candidate.get("learning_outcomes") != outcomes.get(str(code), [])
            ):
                cls._add(
                    errors,
                    "taxonomy_mappings",
                    "TAXONOMY_MAPPING_MISMATCH",
                    location,
                    str(candidate.get("candidate_id")),
                )
        return errors

    @classmethod
    def _validate_standalone(
        cls,
        candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        candidate_by_id = {
            row.get("candidate_id"): row for row in candidates
        }
        ids = [row.get("candidate_id") for row in standalone]
        if len(ids) != len(set(ids)):
            cls._add(
                errors,
                "standalone_projection",
                "DUPLICATE_STANDALONE_ID",
                "standalone_candidates.json",
                "Standalone IDs must be unique.",
            )
        for index, row in enumerate(standalone):
            candidate_id = row.get("candidate_id")
            if (
                row.get("question_type_detected") != "MULTIPLE_CHOICE"
                or row.get("requires_question_group_model") is not False
                or candidate_by_id.get(candidate_id) != row
            ):
                cls._add(
                    errors,
                    "standalone_projection",
                    "STANDALONE_NOT_EXACT_PROJECTION",
                    f"standalone_candidates.json[{index}]",
                    str(candidate_id),
                )
        expected_ids = {
            row.get("candidate_id")
            for row in candidates
            if row.get("requires_question_group_model") is False
        }
        if set(ids) != expected_ids:
            cls._add(
                errors,
                "standalone_projection",
                "STANDALONE_SET_MISMATCH",
                "standalone_candidates.json",
                "Standalone rows must be the exact non-group projection.",
            )
        return errors

    @classmethod
    def _validate_groups(
        cls,
        candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        candidate_by_id = {
            row.get("candidate_id"): row for row in candidates
        }
        standalone_ids = {row.get("candidate_id") for row in standalone}
        group_ids = [row.get("group_candidate_id") for row in groups]
        source_ids = [row.get("source_candidate_id") for row in groups]
        if (
            len(group_ids) != len(set(group_ids))
            or len(source_ids) != len(set(source_ids))
        ):
            cls._add(
                errors,
                "question_groups",
                "DUPLICATE_GROUP_OR_SOURCE_ID",
                "question_group_candidates.json",
                "Group IDs and source candidate IDs must be one-to-one.",
            )
        for index, group in enumerate(groups):
            location = f"question_group_candidates.json[{index}]"
            source = candidate_by_id.get(group.get("source_candidate_id"))
            if (
                source is None
                or source.get("question_type_detected") != "TRUE_FALSE_GROUP"
                or source.get("requires_question_group_model") is not True
                or source.get("mixed_scope") is not True
            ):
                cls._add(
                    errors,
                    "question_groups",
                    "INVALID_GROUP_SOURCE",
                    location,
                    repr(group.get("source_candidate_id")),
                )
                continue
            if group.get("source_candidate_id") in standalone_ids:
                cls._add(
                    errors,
                    "question_groups",
                    "GROUP_SOURCE_IN_STANDALONE",
                    location,
                    "TRUE_FALSE_FOUR children must never be split as standalone rows.",
                )
            items = group.get("items")
            structure_valid = (
                group.get("group_type") == "TRUE_FALSE_FOUR"
                and group.get("scoring_policy") == "MOET_2025_TRUE_FALSE"
                and group.get("mixed_scope") is True
                and group.get("status") == "STRUCTURAL_CANDIDATE"
                and group.get("academic_review_status") == "NOT_REVIEWED"
                and group.get("promotion_eligible") is False
                and isinstance(group.get("group_context"), str)
                and bool(group.get("group_context", "").strip())
                and isinstance(items, list)
                and len(items) == 4
            )
            if not structure_valid:
                cls._add(
                    errors,
                    "question_groups",
                    "INVALID_GROUP_STRUCTURE",
                    location,
                    str(group.get("group_candidate_id")),
                )
                continue
            assert isinstance(items, list)
            if (
                [item.get("label") for item in items if isinstance(item, dict)]
                != ["a", "b", "c", "d"]
                or [
                    item.get("order_index")
                    for item in items
                    if isinstance(item, dict)
                ]
                != [0, 1, 2, 3]
            ):
                cls._add(
                    errors,
                    "question_groups",
                    "INVALID_GROUP_ITEM_ORDER",
                    location,
                    "Expected labels a,b,c,d at indexes 0,1,2,3.",
                )
            for child_index, item in enumerate(items):
                if (
                    not isinstance(item, dict)
                    or item.get("correct_answer") is not None
                    or item.get("answer_status") != "UNREVIEWED"
                    or item.get("taxonomy_status") != "NOT_REVIEWED"
                    or not isinstance(item.get("content"), str)
                    or not item.get("content", "").strip()
                ):
                    cls._add(
                        errors,
                        "question_groups",
                        "INVALID_UNREVIEWED_CHILD",
                        f"{location}.items[{child_index}]",
                        "TF children must remain unreviewed and have null answers.",
                    )
            if source.get("tf_items") != items or source.get("answer_detected") is not None:
                cls._add(
                    errors,
                    "question_groups",
                    "GROUP_SOURCE_PROJECTION_MISMATCH",
                    location,
                    str(group.get("source_candidate_id")),
                )
        expected_source_ids = {
            row.get("candidate_id")
            for row in candidates
            if row.get("requires_question_group_model") is True
        }
        if set(source_ids) != expected_source_ids:
            cls._add(
                errors,
                "question_groups",
                "GROUP_SOURCE_SET_MISMATCH",
                "question_group_candidates.json",
                "Every TF source candidate must materialize exactly once as a group.",
            )
        return errors

    @classmethod
    def _validate_coverage(
        cls,
        candidates: list[dict[str, Any]],
        coverage: list[dict[str, Any]],
        problem_types: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        problem_type_by_code = {
            row.get("code"): row for row in problem_types
        }
        coverage_by_code = {
            row.get("problem_type_code"): row for row in coverage
        }
        if (
            len(coverage) != 12
            or set(coverage_by_code) != set(problem_type_by_code)
        ):
            cls._add(
                errors,
                "coverage",
                "COVERAGE_PROBLEM_TYPE_SET_MISMATCH",
                "coverage_report.json",
                "Coverage must contain all 12 DATA-019 ProblemTypes.",
            )
            return errors
        actual_counts = Counter(
            row.get("problem_type_code") for row in candidates
        )
        for code, taxonomy in problem_type_by_code.items():
            count = actual_counts.get(code, 0)
            expected_row = {
                "problem_type_code": code,
                "problem_type_name": taxonomy.get("name"),
                "candidate_count": count,
                "coverage_status": (
                    "HAS_STRUCTURAL_CANDIDATES" if count else "GAP"
                ),
            }
            if coverage_by_code.get(code) != expected_row:
                cls._add(
                    errors,
                    "coverage",
                    "COVERAGE_ROW_MISMATCH",
                    code,
                    f"Expected {expected_row!r}.",
                )
        if {
            code: actual_counts.get(code, 0)
            for code in EXPECTED_PROBLEM_TYPE_COVERAGE
        } != EXPECTED_PROBLEM_TYPE_COVERAGE:
            cls._add(
                errors,
                "coverage",
                "PROBLEM_TYPE_COVERAGE_MISMATCH",
                "candidate_questions.json",
                repr(dict(actual_counts)),
            )
        gaps = tuple(
            row.get("problem_type_code")
            for row in coverage
            if row.get("coverage_status") == "GAP"
        )
        if gaps != EXPECTED_PROBLEM_TYPE_GAPS:
            cls._add(
                errors,
                "coverage",
                "PROBLEM_TYPE_GAPS_MISMATCH",
                "coverage_report.json",
                repr(gaps),
            )
        return errors

    @classmethod
    def _validate_review_queue(
        cls,
        candidates: list[dict[str, Any]],
        rows: list[dict[str, str]],
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        candidate_by_id = {
            str(row.get("candidate_id")): row for row in candidates
        }
        ids = [row.get("candidate_id") for row in rows]
        if (
            len(rows) != 41
            or len(ids) != len(set(ids))
            or set(ids) != set(candidate_by_id)
        ):
            cls._add(
                errors,
                "review_queue",
                "REVIEW_QUEUE_SET_MISMATCH",
                "review_queue.csv",
                "Review queue must contain all 41 candidate IDs exactly once.",
            )
        for index, row in enumerate(rows):
            candidate = candidate_by_id.get(str(row.get("candidate_id")))
            if candidate is None:
                continue
            expected = {
                "source_key": str(candidate.get("source_key")),
                "source_page": str(candidate.get("source_page")),
                "question_number": str(candidate.get("question_number")),
                "question_type": str(candidate.get("question_type_detected")),
                "problem_type_code": str(candidate.get("problem_type_code")),
                "visual_required": str(candidate.get("visual_required")).lower(),
                "mixed_scope": str(candidate.get("mixed_scope")).lower(),
                "answer_detected": (
                    "" if candidate.get("answer_detected") is None else str(candidate.get("answer_detected"))
                ),
                "review_status": "NOT_REVIEWED",
            }
            if any(row.get(field) != value for field, value in expected.items()):
                cls._add(
                    errors,
                    "review_queue",
                    "REVIEW_QUEUE_ROW_MISMATCH",
                    f"review_queue.csv[{index}]",
                    str(row.get("candidate_id")),
                )
        return errors

    @classmethod
    def _validate_review_boundary(
        cls,
        candidates: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        answers = policy.get("answers")
        if (
            policy.get("status") != "STRUCTURAL_REVIEW_REQUIRED"
            or policy.get("database_import_allowed") is not False
            or policy.get("canonical_snapshot_allowed") is not False
            or policy.get("production_release_eligible") is not False
            or not isinstance(answers, dict)
            or answers.get("detected_answers_are_authority") is not False
            or answers.get("true_false_children_remain_unreviewed") is not True
        ):
            cls._add(
                errors,
                "review_boundary",
                "INVALID_REVIEW_POLICY",
                "materialization_policy.json",
                "Academic verification, promotion and import must remain disabled.",
            )
        for index, row in enumerate(candidates):
            if (
                row.get("status") != "STRUCTURAL_CANDIDATE"
                or row.get("academic_review_status") != "NOT_REVIEWED"
                or row.get("promotion_eligible") is not False
                or row.get("classification_method")
                != "RULE_BASED_INITIAL_FROM_SOURCE_TEXT"
                or "correct_answer" in row
                or "verified_answer" in row
            ):
                cls._add(
                    errors,
                    "review_boundary",
                    "CANDIDATE_REVIEW_BOUNDARY_VIOLATION",
                    f"candidate_questions.json[{index}]",
                    str(row.get("candidate_id")),
                )
        if any(
            row.get("status") != "STRUCTURAL_CANDIDATE"
            or row.get("academic_review_status") != "NOT_REVIEWED"
            or row.get("promotion_eligible") is not False
            for row in groups
        ):
            cls._add(
                errors,
                "review_boundary",
                "GROUP_REVIEW_BOUNDARY_VIOLATION",
                "question_group_candidates.json",
                "QuestionGroups must remain structural and non-promotable.",
            )
        return errors

    @classmethod
    def _validate_visual_rights(
        cls,
        path: Path,
        candidates: list[dict[str, Any]],
        policy: dict[str, Any],
        source_manifest: dict[str, Any],
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        valid = (
            policy.get("rights_status") == "REVIEW_REQUIRED"
            and source_manifest.get("rights_status") == "REVIEW_REQUIRED"
            and sum(row.get("visual_required") is True for row in candidates) == 40
        )
        if not valid:
            cls._add(
                errors,
                "visual_rights_boundary",
                "VISUAL_OR_RIGHTS_BOUNDARY_MISMATCH",
                "materialization_policy.json",
                "Rights must remain REVIEW_REQUIRED and 40 candidates need visuals.",
            )
        if any(file.suffix.lower() == ".pdf" for file in path.rglob("*")):
            cls._add(
                errors,
                "visual_rights_boundary",
                "SOURCE_PDF_PRESENT",
                path.as_posix(),
                "Source PDF binaries are forbidden.",
            )
        return errors

    @classmethod
    def _validate_grade11_boundary(
        cls,
        candidates: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> list[GroupedDataDispersionMaterializationIssue]:
        errors: list[GroupedDataDispersionMaterializationIssue] = []
        scope = policy.get("scope")
        group_policy = policy.get("groups")
        valid_policy = (
            isinstance(scope, dict)
            and scope.get("include") == "Grade-12 grouped-data dispersion only"
            and scope.get("exclude_standalone")
            == [
                "grouped mean only",
                "median only",
                "mode only",
                "Q1/Q2/Q3 only",
                "median-group only",
                "probability-only",
            ]
            and scope.get("prerequisite_note")
            == "Mean/quartile interpolation may remain inside a dispersion solution."
            and isinstance(group_policy, dict)
            and group_policy.get("TRUE_FALSE_FOUR_atomic") is True
            and group_policy.get("mixed_scope_allowed") is True
            and group_policy.get("split_children_forbidden") is True
            and policy.get("no_synthetic_gap_fill") is True
        )
        if not valid_policy:
            cls._add(
                errors,
                "grade11_scope_boundary",
                "GRADE11_SCOPE_POLICY_MISMATCH",
                "materialization_policy.json",
                "Grade-11 standalone exclusions or atomic group policy changed.",
            )
        used_codes = {row.get("problem_type_code") for row in candidates}
        if used_codes != set(EXPECTED_PROBLEM_TYPE_COVERAGE):
            cls._add(
                errors,
                "grade11_scope_boundary",
                "NON_DISPERSION_PROBLEM_TYPE_MATERIALIZED",
                "candidate_questions.json",
                repr(used_codes),
            )
        mixed_candidate_ids = {
            row.get("candidate_id")
            for row in candidates
            if row.get("mixed_scope") is True
        }
        mixed_group_source_ids = {
            row.get("source_candidate_id")
            for row in groups
            if row.get("mixed_scope") is True
        }
        if (
            mixed_candidate_ids != mixed_group_source_ids
            or len(mixed_group_source_ids) != 2
        ):
            cls._add(
                errors,
                "grade11_scope_boundary",
                "MIXED_SCOPE_GROUP_SET_MISMATCH",
                "question_group_candidates.json",
                "Exactly two mixed-scope candidates must remain atomic groups.",
            )
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
        ordered_problem_types = [row.get("code") for row in problem_types]
        return {
            "raw_dispersion_occurrences": sum(
                len(row.get("duplicate_occurrences", []))
                for row in candidates
                if isinstance(row.get("duplicate_occurrences"), list)
            ),
            "materialized_unique_candidates": len(candidates),
            "standalone_candidates": len(standalone),
            "true_false_four_groups": len(groups),
            "structural_holds": len(holds),
            "question_type_counts": dict(
                Counter(row.get("question_type_detected") for row in candidates)
            ),
            "selected_source_counts": dict(
                Counter(row.get("source_key") for row in candidates)
            ),
            "all_provenance_occurrence_counts": dict(
                Counter(
                    occurrence.get("source_key")
                    for row in candidates
                    for occurrence in row.get("duplicate_occurrences", [])
                    if isinstance(occurrence, dict)
                )
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
                code for code in ordered_problem_types if code not in covered
            ],
            "production_release_eligible": sum(
                row.get("promotion_eligible") is True for row in candidates
            ),
        }
