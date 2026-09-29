from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.curriculum.grouped_data_dispersion_staging import (
    DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH,
)
from app.questions.grouped_data_dispersion_materialization import (
    DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256 as EXPECTED_INPUT_AGGREGATE_SHA256,
    GroupedDataDispersionMaterializationValidator,
)


DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH = (
    DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH.parents[1]
    / "academic_review"
    / "v0_1"
)
EXPECTED_BASE_COMMIT = "b436e3ee076fefb89dbf58adf64ac0542568479c"
EXPECTED_INPUT_CANDIDATE_SEMANTIC_SHA256 = (
    "bb88a02a3c982b55a11e250af05432ba999f455f1af54cfb347c5dd277f4c619"
)
CURATED_SEMANTIC_FILES = (
    "standalone_reviews.json",
    "group_reviews.json",
    "source_evidence.json",
    "duplicate_clusters.json",
    "review_stats.json",
    "review_manifest.json",
    "validation_contract.json",
    "coverage_after_review.json",
)
EXPECTED_CURATED_SEMANTIC_HASHES = {
    "standalone_reviews.json": (
        "3cb99ccf0c70124306fbb0878e6564d03882955606e104c890a92cdaae02004f"
    ),
    "group_reviews.json": (
        "5cbea4255948f131cf9452045d13d3ee1fd246f01210431da21e08afc69d1dd0"
    ),
    "source_evidence.json": (
        "cc26b9ecb4bf52ab2e825ca22f83b619c11de2e3a17c555787cfd1e646b97fd7"
    ),
    "duplicate_clusters.json": (
        "184afdb5d40244a5cca54b7ab0f1c8717428a09713b1bf17e28db4b1661a82cf"
    ),
    "review_stats.json": (
        "44f14bdc87672aa3224b9d63b7fa203fc88bd3b8d73f7eeb943d43fdcde4df25"
    ),
    "review_manifest.json": (
        "16fbb312aaa0d3de5b59c3ad7db64b9e741df54c4426d1343ec4ada04f0efe9c"
    ),
    "validation_contract.json": (
        "d69fe995a899fc06ff850f4e0858c0570e8ed75ea91c8b8dca5b4e8651a6377b"
    ),
    "coverage_after_review.json": (
        "cba2dad2a1094aa2cd7c00d2a61d752832c2da3f1b565d372e25416cf0ea7748"
    ),
}
EXPECTED_REVIEW_AGGREGATE_SHA256 = (
    "08aae72fa7f615f60e3f0b68845c29d630430321e1013a48cfa7966fb1c25a36"
)
EXPECTED_PROBLEM_TYPE_GAPS = (
    "IDENTIFY_MORE_STABLE_GROUPED_DATA",
    "INTERPRET_GROUPED_DISPERSION_MEASURE",
    "CONCLUDE_FROM_GROUPED_DISPERSION",
    "PARAMETER_FROM_GROUPED_VARIANCE_SD",
    "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS",
)
EXPECTED_VERIFIED_COVERAGE = {
    "CALCULATE_GROUPED_IQR": 11,
    "CALCULATE_GROUPED_RANGE": 6,
    "CALCULATE_GROUPED_STANDARD_DEVIATION": 13,
    "CALCULATE_GROUPED_VARIANCE": 5,
    "COMPARE_GROUPED_IQR": 1,
    "COMPARE_GROUPED_RANGE": 1,
    "COMPARE_GROUPED_VARIANCE_SD": 1,
}
EXPECTED_DUPLICATE_ID = "M12_DISP_CAND_0014"
EXPECTED_CANONICAL_ID = "M12_DISP_CAND_0015"
EXPECTED_GROUP_ANSWER_KEYS = {
    "M12_DISP_GROUP_0032": (True, False, False, True),
    "M12_DISP_GROUP_0035": (True, False, True, False),
}
EXPECTED_REVIEW_STATS: dict[str, Any] = {
    "review_code": "DATA-MATH12-021_GROUPED_DISPERSION_ACADEMIC_REVIEW_V0_2",
    "base_commit": EXPECTED_BASE_COMMIT,
    "input_dataset": "DATA-MATH12-020",
    "input_candidate_count": 41,
    "standalone_reviews": 39,
    "group_reviews": 2,
    "reviewed_units": 41,
    "review_status_counts": {
        "VERIFIED": 38,
        "REJECTED_DUPLICATE": 1,
        "HOLD_MIXED_SCOPE": 2,
    },
    "verified_standalone": 38,
    "rejected_duplicate": 1,
    "hold_mixed_scope_groups": 2,
    "true_false_groups_with_source_verified_answers": 2,
    "true_false_child_answers_verified": 8,
    "verified_visual_required": 37,
    "problem_types_total": 12,
    "problem_types_with_verified_evidence": 7,
    "problem_type_gaps": list(EXPECTED_PROBLEM_TYPE_GAPS),
    "academic_curation_complete": True,
    "production_release_eligible": 0,
    "promotion_ready": 0,
    "rights_status": "REVIEW_REQUIRED",
    "database_import_allowed": False,
    "canonical_snapshot_allowed": False,
}
EXPECTED_REQUIRED_INVARIANTS = {
    "input_candidate_count": 41,
    "standalone_reviews": 39,
    "group_reviews": 2,
    "verified_standalone": 38,
    "rejected_duplicate": 1,
    "hold_mixed_scope_groups": 2,
    "true_false_child_answers_verified": 8,
    "production_release_eligible": 0,
    "database_import_allowed": False,
    "canonical_snapshot_allowed": False,
}


@dataclass(frozen=True, slots=True, order=True)
class GroupedDataDispersionAcademicReviewIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class GroupedDataDispersionAcademicReviewReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, Any]
    duplicate_resolution: dict[str, str]
    group_answer_keys: dict[str, tuple[bool, ...]]
    problem_type_gaps: tuple[str, ...]
    review_aggregate_semantic_sha256: str | None
    production_release_eligible: int
    database_import_allowed: bool
    canonical_snapshot_allowed: bool
    errors: tuple[GroupedDataDispersionAcademicReviewIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "duplicate_resolution": self.duplicate_resolution,
            "group_answer_keys": {
                key: list(value) for key, value in self.group_answer_keys.items()
            },
            "problem_type_gaps": list(self.problem_type_gaps),
            "review_aggregate_semantic_sha256": (
                self.review_aggregate_semantic_sha256
            ),
            "production_release_eligible": self.production_release_eligible,
            "database_import_allowed": self.database_import_allowed,
            "canonical_snapshot_allowed": self.canonical_snapshot_allowed,
            "errors": [asdict(error) for error in self.errors],
        }


class GroupedDataDispersionAcademicReviewValidator:
    """Validate curated DATA-MATH12-021 without rewriting academic decisions."""

    def validate(
        self,
        review_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH,
        *,
        materialization_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH,
        curriculum_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH,
    ) -> GroupedDataDispersionAcademicReviewReport:
        path = review_path.resolve()
        materialization_path = materialization_path.resolve()
        curriculum_path = curriculum_path.resolve()
        initial: list[GroupedDataDispersionAcademicReviewIssue] = []
        self._check_required_files(path, initial)
        standalone = self._load_list(path / "standalone_reviews.json", initial)
        groups = self._load_list(path / "group_reviews.json", initial)
        evidence = self._load_list(path / "source_evidence.json", initial)
        clusters = self._load_list(path / "duplicate_clusters.json", initial)
        stats = self._load_object(path / "review_stats.json", initial)
        manifest = self._load_object(path / "review_manifest.json", initial)
        contract = self._load_object(path / "validation_contract.json", initial)
        coverage = self._load_list(path / "coverage_after_review.json", initial)

        raw_candidates = self._load_list(
            materialization_path / "candidate_questions.json",
            initial,
            check="input_identity",
        )
        raw_standalone = self._load_list(
            materialization_path / "standalone_candidates.json",
            initial,
            check="input_identity",
        )
        structural_groups = self._load_list(
            materialization_path / "question_group_candidates.json",
            initial,
            check="input_identity",
        )
        input_manifest = self._load_object(
            materialization_path / "materialization_manifest.json",
            initial,
            check="input_identity",
        )
        problem_types = self._load_list(
            curriculum_path / "problem_types.json", initial, check="taxonomy"
        )
        concept_rows = self._load_list(
            curriculum_path / "problem_type_concepts.json",
            initial,
            check="taxonomy",
        )
        outcome_rows = self._load_list(
            curriculum_path / "problem_type_learning_outcomes.json",
            initial,
            check="taxonomy",
        )

        checks_to_errors = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "curated_semantic_hashes": self._validate_curated_hashes(path),
            "input_identity": [
                *[issue for issue in initial if issue.check == "input_identity"],
                *self._validate_input_identity(
                    manifest,
                    input_manifest,
                    raw_candidates,
                    materialization_path,
                ),
            ],
            "review_contract": self._validate_contract(manifest, stats, contract),
            "review_id_partition": self._validate_partition(
                raw_standalone,
                structural_groups,
                standalone,
                groups,
            ),
            "standalone_reviews": self._validate_standalone_reviews(
                raw_candidates, standalone
            ),
            "duplicate_resolution": self._validate_duplicate_resolution(
                raw_candidates, standalone, clusters
            ),
            "group_reviews": self._validate_group_reviews(
                raw_candidates, structural_groups, groups
            ),
            "source_evidence": self._validate_source_evidence(
                standalone, groups, evidence
            ),
            "taxonomy": [
                *[issue for issue in initial if issue.check == "taxonomy"],
                *self._validate_taxonomy(
                    standalone,
                    groups,
                    problem_types,
                    concept_rows,
                    outcome_rows,
                ),
            ],
            "coverage": self._validate_coverage(
                standalone, coverage, problem_types
            ),
            "promotion_boundary": self._validate_promotion_boundary(
                manifest, stats, contract, standalone, groups
            ),
        }
        all_issues = list(initial)
        for name, errors in checks_to_errors.items():
            if name != "required_files":
                all_issues.extend(errors)
        checks = {name: not errors for name, errors in checks_to_errors.items()}
        try:
            aggregate = self.review_aggregate_semantic_sha256(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            aggregate = None
        actual_counts = self._derive_counts(standalone, groups)
        return GroupedDataDispersionAcademicReviewReport(
            dataset_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts=actual_counts,
            duplicate_resolution={EXPECTED_DUPLICATE_ID: EXPECTED_CANONICAL_ID},
            group_answer_keys=EXPECTED_GROUP_ANSWER_KEYS,
            problem_type_gaps=EXPECTED_PROBLEM_TYPE_GAPS,
            review_aggregate_semantic_sha256=aggregate,
            production_release_eligible=0,
            database_import_allowed=False,
            canonical_snapshot_allowed=False,
            errors=tuple(sorted(set(all_issues))),
        )

    @staticmethod
    def semantic_sha256(value: Any) -> str:
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @classmethod
    def review_aggregate_semantic_sha256(cls, path: Path) -> str:
        digest = hashlib.sha256()
        for name in CURATED_SEMANTIC_FILES:
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
        errors: list[GroupedDataDispersionAcademicReviewIssue],
        check: str,
        code: str,
        location: str,
        message: str,
    ) -> None:
        errors.append(
            GroupedDataDispersionAcademicReviewIssue(
                check, code, location, message
            )
        )

    @classmethod
    def _check_required_files(
        cls,
        path: Path,
        errors: list[GroupedDataDispersionAcademicReviewIssue],
    ) -> None:
        for name in (*CURATED_SEMANTIC_FILES, "README.md"):
            if not (path / name).is_file():
                cls._add(
                    errors,
                    "required_files",
                    "REQUIRED_CURATED_FILE_MISSING",
                    name,
                    "Required DATA-MATH12-021 artifact is missing.",
                )

    @classmethod
    def _load_json(
        cls,
        path: Path,
        errors: list[GroupedDataDispersionAcademicReviewIssue],
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
        errors: list[GroupedDataDispersionAcademicReviewIssue],
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
        errors: list[GroupedDataDispersionAcademicReviewIssue],
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
    def _validate_curated_hashes(
        cls, path: Path
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        for name, expected in EXPECTED_CURATED_SEMANTIC_HASHES.items():
            try:
                value = json.loads((path / name).read_text(encoding="utf-8"))
                actual = cls.semantic_sha256(value)
            except (OSError, json.JSONDecodeError) as error:
                cls._add(
                    errors,
                    "curated_semantic_hashes",
                    "CURATED_FILE_UNREADABLE",
                    name,
                    str(error),
                )
                continue
            if actual != expected:
                cls._add(
                    errors,
                    "curated_semantic_hashes",
                    "CURATED_SEMANTIC_SHA256_MISMATCH",
                    name,
                    f"Expected {expected}; found {actual}.",
                )
        try:
            aggregate = cls.review_aggregate_semantic_sha256(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            cls._add(
                errors,
                "curated_semantic_hashes",
                "CURATED_AGGREGATE_INPUT_INVALID",
                "curated review files",
                str(error),
            )
        else:
            if aggregate != EXPECTED_REVIEW_AGGREGATE_SHA256:
                cls._add(
                    errors,
                    "curated_semantic_hashes",
                    "CURATED_AGGREGATE_SHA256_MISMATCH",
                    "curated review files",
                    (
                        f"Expected {EXPECTED_REVIEW_AGGREGATE_SHA256}; "
                        f"found {aggregate}."
                    ),
                )
        return errors

    @classmethod
    def _validate_input_identity(
        cls,
        manifest: dict[str, Any],
        input_manifest: dict[str, Any],
        raw_candidates: list[dict[str, Any]],
        materialization_path: Path,
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        materialization = GroupedDataDispersionMaterializationValidator().validate(
            materialization_path
        )
        if not materialization.is_valid:
            cls._add(
                errors,
                "input_identity",
                "INPUT_MATERIALIZATION_INVALID",
                materialization_path.as_posix(),
                "DATA-MATH12-020 validator must pass before academic review.",
            )
        actual_candidate_hash = cls.semantic_sha256(raw_candidates)
        valid = (
            len(raw_candidates) == 41
            and actual_candidate_hash == EXPECTED_INPUT_CANDIDATE_SEMANTIC_SHA256
            and input_manifest.get("semantic_file_hashes", {}).get(
                "candidate_questions.json"
            )
            == EXPECTED_INPUT_CANDIDATE_SEMANTIC_SHA256
            and input_manifest.get("aggregate_semantic_sha256")
            == EXPECTED_INPUT_AGGREGATE_SHA256
            and manifest.get("input_materialization_dataset") == "DATA-MATH12-020"
            and manifest.get("input_candidate_semantic_sha256")
            == EXPECTED_INPUT_CANDIDATE_SEMANTIC_SHA256
            and manifest.get("input_materialization_aggregate_sha256")
            == EXPECTED_INPUT_AGGREGATE_SHA256
        )
        if not valid:
            cls._add(
                errors,
                "input_identity",
                "INPUT_IDENTITY_MISMATCH",
                "review_manifest.json",
                "DATA-MATH12-020 candidate or aggregate identity changed.",
            )
        return errors

    @classmethod
    def _validate_contract(
        cls,
        manifest: dict[str, Any],
        stats: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        expected_manifest = {
            "dataset_code": "DATA-MATH12-021",
            "dataset_name": "MATH12_GROUPED_DISPERSION_ACADEMIC_REVIEW_V0_2",
            "base_commit": EXPECTED_BASE_COMMIT,
            "status": "ACADEMIC_CURATION_COMPLETE_WITH_MIXED_SCOPE_HOLDS",
            "subject_code": "MATH_G12",
            "chapter_code": "GROUPED_DATA_DISPERSION",
            "database_import_allowed": False,
            "canonical_snapshot_allowed": False,
            "production_release_eligible": 0,
        }
        for field, expected in expected_manifest.items():
            if manifest.get(field) != expected:
                cls._add(
                    errors,
                    "review_contract",
                    "REVIEW_MANIFEST_VALUE_MISMATCH",
                    field,
                    f"Expected {expected!r}; found {manifest.get(field)!r}.",
                )
        if stats != EXPECTED_REVIEW_STATS or manifest.get("counts") != stats:
            cls._add(
                errors,
                "review_contract",
                "REVIEW_STATS_MISMATCH",
                "review_stats.json",
                "Review stats must match the locked DATA-MATH12-021 totals.",
            )
        valid_contract = (
            contract.get("contract_code") == "DATA_MATH12_021_DATA_CONTRACT_V0_2"
            and contract.get("required_invariants") == EXPECTED_REQUIRED_INVARIANTS
            and contract.get("duplicate_resolution")
            == {EXPECTED_DUPLICATE_ID: EXPECTED_CANONICAL_ID}
            and contract.get("group_answer_keys")
            == {
                key: list(value)
                for key, value in EXPECTED_GROUP_ANSWER_KEYS.items()
            }
            and contract.get("implementation_note")
            == "Application code may adapt to this dataset contract; curated academic fields are not implementation-owned."
        )
        if not valid_contract:
            cls._add(
                errors,
                "review_contract",
                "VALIDATION_CONTRACT_MISMATCH",
                "validation_contract.json",
                "Locked review totals, duplicate mapping or answer keys changed.",
            )
        expected_boundary = {
            "data_content_locked": True,
            "codex_may_edit": [
                "validators",
                "schemas",
                "tests",
                "importers",
                "integration code",
            ],
            "codex_must_not_edit": [
                "answers",
                "review_status",
                "duplicate decisions",
                "taxonomy decisions",
                "source evidence",
                "coverage gaps",
            ],
        }
        if manifest.get("codex_boundary") != expected_boundary:
            cls._add(
                errors,
                "review_contract",
                "CODEX_BOUNDARY_MISMATCH",
                "review_manifest.json.codex_boundary",
                "The curated-data ownership boundary changed.",
            )
        return errors

    @classmethod
    def _validate_partition(
        cls,
        raw_standalone: list[dict[str, Any]],
        structural_groups: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        standalone_ids = [row.get("candidate_id") for row in standalone]
        group_ids = [row.get("group_candidate_id") for row in groups]
        group_source_ids = [row.get("source_candidate_id") for row in groups]
        valid = (
            len(standalone_ids) == len(set(standalone_ids)) == 39
            and set(standalone_ids)
            == {row.get("candidate_id") for row in raw_standalone}
            and len(group_ids) == len(set(group_ids)) == 2
            and len(group_source_ids) == len(set(group_source_ids)) == 2
            and set(group_ids)
            == {row.get("group_candidate_id") for row in structural_groups}
            and set(group_source_ids)
            == {row.get("source_candidate_id") for row in structural_groups}
            and set(standalone_ids).isdisjoint(group_source_ids)
        )
        if not valid:
            cls._add(
                errors,
                "review_id_partition",
                "REVIEW_ID_PARTITION_MISMATCH",
                "academic review",
                "39 standalone and 2 group source IDs must partition DATA-020.",
            )
        return errors

    @classmethod
    def _validate_standalone_reviews(
        cls,
        raw_candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        raw_by_id = {row.get("candidate_id"): row for row in raw_candidates}
        for index, review in enumerate(standalone):
            location = f"standalone_reviews.json[{index}]"
            raw = raw_by_id.get(review.get("candidate_id"))
            if raw is None:
                cls._add(
                    errors,
                    "standalone_reviews",
                    "UNKNOWN_STANDALONE_CANDIDATE",
                    location,
                    repr(review.get("candidate_id")),
                )
                continue
            lineage_fields = {
                "source_code": "source_code",
                "source_key": "source_key",
                "source_file_id": "source_file_id",
                "source_sha256": "source_sha256",
                "candidate_source_page": "source_page",
                "question_number": "question_number",
                "question_type": "question_type_detected",
                "structural_problem_type_code": "problem_type_code",
            }
            if any(
                review.get(review_field) != raw.get(raw_field)
                for review_field, raw_field in lineage_fields.items()
            ):
                cls._add(
                    errors,
                    "standalone_reviews",
                    "STANDALONE_SOURCE_LINEAGE_MISMATCH",
                    location,
                    str(review.get("candidate_id")),
                )
            if (
                review.get("content_review") != "CONFIRMED_FROM_SOURCE"
                or review.get("taxonomy_review") != "CONFIRMED"
                or review.get("promotion_ready") is not False
            ):
                cls._add(
                    errors,
                    "standalone_reviews",
                    "INVALID_STANDALONE_REVIEW_BOUNDARY",
                    location,
                    str(review.get("candidate_id")),
                )
            status = review.get("review_status")
            if status == "VERIFIED":
                if (
                    review.get("duplicate_of") is not None
                    or review.get("correct_answer") not in {"A", "B", "C", "D"}
                    or review.get("answer_verification")
                    != "SOURCE_BACKED_AND_REVIEW_CONSISTENT"
                    or set(review.get("promotion_blockers", []))
                    != {
                        "RIGHTS_REVIEW_REQUIRED",
                        "VISUAL_ASSET_REVIEW_REQUIRED",
                    }
                ):
                    cls._add(
                        errors,
                        "standalone_reviews",
                        "INVALID_VERIFIED_STANDALONE",
                        location,
                        str(review.get("candidate_id")),
                    )
            elif status != "REJECTED_DUPLICATE":
                cls._add(
                    errors,
                    "standalone_reviews",
                    "UNKNOWN_STANDALONE_REVIEW_STATUS",
                    location,
                    repr(status),
                )
        statuses = Counter(row.get("review_status") for row in standalone)
        if statuses != Counter({"VERIFIED": 38, "REJECTED_DUPLICATE": 1}):
            cls._add(
                errors,
                "standalone_reviews",
                "STANDALONE_STATUS_COUNTS_MISMATCH",
                "standalone_reviews.json",
                repr(dict(statuses)),
            )
        return errors

    @staticmethod
    def _normalized_question_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        normalized = re.sub(r"^câu\s*\d+[.:]?\s*", "", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    @classmethod
    def _validate_duplicate_resolution(
        cls,
        raw_candidates: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        clusters: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        reviews = {row.get("candidate_id"): row for row in standalone}
        raw = {row.get("candidate_id"): row for row in raw_candidates}
        duplicate = reviews.get(EXPECTED_DUPLICATE_ID, {})
        canonical = reviews.get(EXPECTED_CANONICAL_ID, {})
        expected_cluster = {
            "cluster_id": "DISP_DUP_0001",
            "canonical_candidate_id": EXPECTED_CANONICAL_ID,
            "duplicate_candidate_ids": [EXPECTED_DUPLICATE_ID],
            "reason": "EXACT_NORMALIZED_QUESTION_TEXT_MATCH",
            "academic_resolution": "KEEP_0015_REJECT_0014",
            "canonical_answer": "B",
            "canonical_answer_basis": (
                "SOURCE_SOLUTION_OCCURRENCE_ON_CANONICAL_CANDIDATE"
            ),
        }
        texts_match = (
            EXPECTED_DUPLICATE_ID in raw
            and EXPECTED_CANONICAL_ID in raw
            and cls._normalized_question_text(
                str(raw[EXPECTED_DUPLICATE_ID].get("raw_question_text", ""))
            )
            == cls._normalized_question_text(
                str(raw[EXPECTED_CANONICAL_ID].get("raw_question_text", ""))
            )
        )
        valid = (
            clusters == [expected_cluster]
            and duplicate.get("review_status") == "REJECTED_DUPLICATE"
            and duplicate.get("duplicate_of") == EXPECTED_CANONICAL_ID
            and duplicate.get("correct_answer") is None
            and duplicate.get("promotion_ready") is False
            and duplicate.get("promotion_blockers") == ["REJECTED_DUPLICATE"]
            and canonical.get("review_status") == "VERIFIED"
            and canonical.get("duplicate_of") is None
            and canonical.get("correct_answer") == "B"
            and texts_match
        )
        if not valid:
            cls._add(
                errors,
                "duplicate_resolution",
                "LOCKED_DUPLICATE_RESOLUTION_MISMATCH",
                "duplicate_clusters.json",
                "0014 must be the exact-text duplicate of canonical 0015 (answer B).",
            )
        return errors

    @classmethod
    def _validate_group_reviews(
        cls,
        raw_candidates: list[dict[str, Any]],
        structural_groups: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        raw_by_id = {row.get("candidate_id"): row for row in raw_candidates}
        structural_by_id = {
            row.get("group_candidate_id"): row for row in structural_groups
        }
        if {row.get("group_candidate_id") for row in groups} != set(
            EXPECTED_GROUP_ANSWER_KEYS
        ):
            cls._add(
                errors,
                "group_reviews",
                "GROUP_REVIEW_ID_SET_MISMATCH",
                "group_reviews.json",
                "Expected exactly groups 0032 and 0035.",
            )
        for index, review in enumerate(groups):
            location = f"group_reviews.json[{index}]"
            group_id = review.get("group_candidate_id")
            structural = structural_by_id.get(group_id)
            raw = raw_by_id.get(review.get("source_candidate_id"))
            if structural is None or raw is None:
                cls._add(
                    errors,
                    "group_reviews",
                    "UNKNOWN_GROUP_OR_SOURCE_CANDIDATE",
                    location,
                    str(group_id),
                )
                continue
            lineage_valid = (
                review.get("source_candidate_id")
                == structural.get("source_candidate_id")
                and review.get("group_type") == structural.get("group_type")
                and review.get("source_code") == raw.get("source_code")
                and review.get("source_key") == raw.get("source_key")
                and review.get("source_file_id") == raw.get("source_file_id")
                and review.get("source_sha256") == raw.get("source_sha256")
                and review.get("candidate_source_page") == raw.get("source_page")
                and review.get("question_number") == raw.get("question_number")
            )
            items = review.get("items")
            expected_key = EXPECTED_GROUP_ANSWER_KEYS.get(str(group_id))
            structure_valid = (
                lineage_valid
                and review.get("review_status") == "HOLD_MIXED_SCOPE"
                and review.get("content_review") == "CONFIRMED_FROM_SOURCE"
                and review.get("answer_verification")
                == "SOURCE_SOLUTION_CONFIRMED_FOR_ALL_CHILDREN"
                and review.get("mixed_scope") is True
                and review.get("promotion_ready") is False
                and set(review.get("promotion_blockers", []))
                == {
                    "MIXED_SCOPE_GROUP_NOT_CANONICAL_FOR_DISPERSION_ONLY_DATASET",
                    "RIGHTS_REVIEW_REQUIRED",
                    "VISUAL_ASSET_REVIEW_REQUIRED",
                }
                and isinstance(items, list)
                and len(items) == 4
                and [item.get("label") for item in items if isinstance(item, dict)]
                == ["a", "b", "c", "d"]
                and [
                    item.get("order_index")
                    for item in items
                    if isinstance(item, dict)
                ]
                == [0, 1, 2, 3]
                and tuple(
                    item.get("correct_answer")
                    for item in items
                    if isinstance(item, dict)
                )
                == expected_key
                and all(
                    isinstance(item, dict)
                    and item.get("answer_status") == "SOURCE_BACKED_VERIFIED"
                    for item in items
                )
                and [
                    item.get("content") for item in items if isinstance(item, dict)
                ]
                == [
                    item.get("content")
                    for item in structural.get("items", [])
                    if isinstance(item, dict)
                ]
            )
            if not structure_valid:
                cls._add(
                    errors,
                    "group_reviews",
                    "LOCKED_GROUP_REVIEW_MISMATCH",
                    location,
                    str(group_id),
                )
                continue
            assert isinstance(items, list)
            in_scope = [
                item
                for item in items
                if isinstance(item, dict)
                and item.get("taxonomy_status") == "IN_SCOPE"
            ]
            out_of_scope = [
                item
                for item in items
                if isinstance(item, dict)
                and item.get("taxonomy_status")
                == "OUT_OF_SCOPE_FOR_DISPERSION_DATASET"
            ]
            if (
                len(in_scope) != 1
                or len(out_of_scope) != 3
                or in_scope[0].get("problem_type_code")
                != "CALCULATE_GROUPED_RANGE"
                or any(item.get("problem_type_code") is not None for item in out_of_scope)
            ):
                cls._add(
                    errors,
                    "group_reviews",
                    "GROUP_CHILD_SCOPE_DECISION_MISMATCH",
                    location,
                    str(group_id),
                )
        return errors

    @classmethod
    def _validate_source_evidence(
        cls,
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        evidence_ids = [row.get("evidence_id") for row in evidence]
        evidence_by_candidate = {
            row.get("candidate_id"): row for row in evidence
        }
        expected_ids = {row.get("candidate_id") for row in standalone} | {
            row.get("group_candidate_id") for row in groups
        }
        if (
            len(evidence) != 41
            or len(evidence_ids) != len(set(evidence_ids))
            or len(evidence_by_candidate) != 41
            or set(evidence_by_candidate) != expected_ids
        ):
            cls._add(
                errors,
                "source_evidence",
                "SOURCE_EVIDENCE_SET_MISMATCH",
                "source_evidence.json",
                "Each of 39 standalone and 2 group reviews needs one evidence row.",
            )
        for review in standalone:
            candidate_id = review.get("candidate_id")
            row = evidence_by_candidate.get(candidate_id)
            if row is None:
                continue
            lineage_fields = (
                "source_code",
                "source_key",
                "source_file_id",
                "source_sha256",
                "candidate_source_page",
                "question_number",
            )
            valid = (
                row.get("question_unit_type") == "STANDALONE"
                and all(row.get(field) == review.get(field) for field in lineage_fields)
                and review.get("candidate_source_page")
                in row.get("question_pages", [])
            )
            if review.get("review_status") == "VERIFIED":
                valid = (
                    valid
                    and row.get("source_claimed_answer")
                    == review.get("correct_answer")
                    and row.get("evidence_type")
                    == "SOURCE_QUESTION_AND_SOLUTION_OCCURRENCE"
                    and row.get("review_consistency") == "CONFIRMED"
                    and bool(row.get("solution_pages"))
                )
            else:
                valid = (
                    valid
                    and candidate_id == EXPECTED_DUPLICATE_ID
                    and row.get("source_claimed_answer") is None
                    and row.get("evidence_type") == "DUPLICATE_MATCH"
                    and row.get("review_consistency")
                    == "DUPLICATE_OF_M12_DISP_CAND_0015"
                )
            if not valid:
                cls._add(
                    errors,
                    "source_evidence",
                    "STANDALONE_SOURCE_EVIDENCE_MISMATCH",
                    str(candidate_id),
                    "Evidence lineage or source-backed answer changed.",
                )
        for review in groups:
            group_id = review.get("group_candidate_id")
            row = evidence_by_candidate.get(group_id)
            answer_key = [
                item.get("correct_answer")
                for item in review.get("items", [])
                if isinstance(item, dict)
            ]
            valid = (
                row is not None
                and row.get("source_candidate_id")
                == review.get("source_candidate_id")
                and row.get("question_unit_type") == "TRUE_FALSE_GROUP"
                and all(
                    row.get(field) == review.get(field)
                    for field in (
                        "source_code",
                        "source_key",
                        "source_file_id",
                        "source_sha256",
                        "candidate_source_page",
                        "question_number",
                    )
                )
                and row.get("source_claimed_answer") == answer_key
                and row.get("evidence_type")
                == "SOURCE_GROUP_QUESTION_AND_DETAILED_SOLUTION"
                and row.get("review_consistency") == "CONFIRMED"
                and bool(row.get("solution_pages"))
            )
            if not valid:
                cls._add(
                    errors,
                    "source_evidence",
                    "GROUP_SOURCE_EVIDENCE_MISMATCH",
                    str(group_id),
                    "Group answer key must remain source-backed.",
                )
        return errors

    @classmethod
    def _validate_taxonomy(
        cls,
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        problem_types: list[dict[str, Any]],
        concept_rows: list[dict[str, Any]],
        outcome_rows: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        problem_type_codes = {row.get("code") for row in problem_types}
        concepts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        outcomes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in concept_rows:
            concepts[str(row.get("problem_type_code"))].append(
                {
                    "code": row.get("concept_code"),
                    "weight": row.get("weight"),
                    "is_primary": row.get("is_primary"),
                }
            )
        for row in outcome_rows:
            outcomes[str(row.get("problem_type_code"))].append(
                {
                    "code": row.get("learning_outcome_code"),
                    "weight": row.get("weight"),
                }
            )
        for index, review in enumerate(standalone):
            code = review.get("reviewed_problem_type_code")
            expected_taxonomy = {
                "status": "CONFIRMED",
                "basis": "DATA_MATH12_019_TAXONOMY",
                "problem_types": [
                    {"code": code, "weight": 1, "is_primary": True}
                ],
                "concepts": concepts.get(str(code), []),
                "learning_outcomes": outcomes.get(str(code), []),
            }
            if code not in problem_type_codes or review.get("taxonomy") != expected_taxonomy:
                cls._add(
                    errors,
                    "taxonomy",
                    "STANDALONE_TAXONOMY_MISMATCH",
                    f"standalone_reviews.json[{index}]",
                    str(review.get("candidate_id")),
                )
        for group in groups:
            for item in group.get("items", []):
                if (
                    isinstance(item, dict)
                    and item.get("taxonomy_status") == "IN_SCOPE"
                    and item.get("problem_type_code") not in problem_type_codes
                ):
                    cls._add(
                        errors,
                        "taxonomy",
                        "UNKNOWN_GROUP_CHILD_PROBLEM_TYPE",
                        str(group.get("group_candidate_id")),
                        repr(item.get("problem_type_code")),
                    )
        return errors

    @classmethod
    def _validate_coverage(
        cls,
        standalone: list[dict[str, Any]],
        coverage: list[dict[str, Any]],
        problem_types: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        codes = {row.get("code") for row in problem_types}
        coverage_by_code = {
            row.get("problem_type_code"): row for row in coverage
        }
        if len(coverage) != 12 or set(coverage_by_code) != codes:
            cls._add(
                errors,
                "coverage",
                "COVERAGE_PROBLEM_TYPE_SET_MISMATCH",
                "coverage_after_review.json",
                "Coverage must report all 12 DATA-019 ProblemTypes.",
            )
            return errors
        for code in codes:
            count = EXPECTED_VERIFIED_COVERAGE.get(str(code), 0)
            expected = {
                "problem_type_code": code,
                "verified_standalone_candidates": count,
                "status": "COVERED" if count else "GAP",
            }
            if coverage_by_code.get(code) != expected:
                cls._add(
                    errors,
                    "coverage",
                    "COVERAGE_ROW_MISMATCH",
                    str(code),
                    f"Expected {expected!r}.",
                )
        gaps = tuple(
            row.get("problem_type_code")
            for row in coverage
            if row.get("status") == "GAP"
        )
        if gaps != EXPECTED_PROBLEM_TYPE_GAPS:
            cls._add(
                errors,
                "coverage",
                "REAL_PROBLEM_TYPE_GAPS_MISMATCH",
                "coverage_after_review.json",
                repr(gaps),
            )
        return errors

    @classmethod
    def _validate_promotion_boundary(
        cls,
        manifest: dict[str, Any],
        stats: dict[str, Any],
        contract: dict[str, Any],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionAcademicReviewIssue]:
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        invariants = contract.get("required_invariants", {})
        blocked = (
            manifest.get("production_release_eligible") == 0
            and manifest.get("database_import_allowed") is False
            and manifest.get("canonical_snapshot_allowed") is False
            and stats.get("production_release_eligible") == 0
            and stats.get("promotion_ready") == 0
            and stats.get("rights_status") == "REVIEW_REQUIRED"
            and stats.get("database_import_allowed") is False
            and stats.get("canonical_snapshot_allowed") is False
            and invariants.get("production_release_eligible") == 0
            and invariants.get("database_import_allowed") is False
            and invariants.get("canonical_snapshot_allowed") is False
            and all(row.get("promotion_ready") is False for row in standalone)
            and all(row.get("promotion_ready") is False for row in groups)
            and all(
                "RIGHTS_REVIEW_REQUIRED" in row.get("promotion_blockers", [])
                for row in standalone
                if row.get("review_status") == "VERIFIED"
            )
            and all(
                "MIXED_SCOPE_GROUP_NOT_CANONICAL_FOR_DISPERSION_ONLY_DATASET"
                in row.get("promotion_blockers", [])
                for row in groups
            )
        )
        if not blocked:
            cls._add(
                errors,
                "promotion_boundary",
                "PROMOTION_OR_IMPORT_BOUNDARY_VIOLATION",
                "academic review",
                "Rights, mixed scope, canonical snapshot and DB import must stay blocked.",
            )
        return errors

    @staticmethod
    def _derive_counts(
        standalone: list[dict[str, Any]], groups: list[dict[str, Any]]
    ) -> dict[str, Any]:
        standalone_statuses = Counter(
            row.get("review_status") for row in standalone
        )
        group_statuses = Counter(row.get("review_status") for row in groups)
        return {
            "input_candidate_count": len(standalone) + len(groups),
            "standalone_reviews": len(standalone),
            "group_reviews": len(groups),
            "verified_standalone": standalone_statuses["VERIFIED"],
            "rejected_duplicate": standalone_statuses["REJECTED_DUPLICATE"],
            "hold_mixed_scope_groups": group_statuses["HOLD_MIXED_SCOPE"],
            "true_false_child_answers_verified": sum(
                item.get("answer_status") == "SOURCE_BACKED_VERIFIED"
                for group in groups
                for item in group.get("items", [])
                if isinstance(item, dict)
            ),
            "production_release_eligible": sum(
                row.get("promotion_ready") is True
                for row in [*standalone, *groups]
            ),
        }
