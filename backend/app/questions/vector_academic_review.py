from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.curriculum.vector_staging import DEFAULT_VECTOR_STAGING_PATH
from app.questions.vector_materialization import (
    DEFAULT_VECTOR_MATERIALIZATION_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256 as EXPECTED_INPUT_AGGREGATE_SHA256,
    VectorQuestionMaterializationValidator,
)


DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH = (
    DEFAULT_VECTOR_MATERIALIZATION_PATH.parents[1] / "academic_review" / "v0_1"
)
EXPECTED_BASE_COMMIT = "d2693571a6129b8bd4828f66bdea8105cc0dbfaf"
EXPECTED_RAW_CANDIDATE_SEMANTIC_SHA256 = (
    "1b364f145fcd6110ba99ee32dc91928a5d3909eac3347e315c40bd7e73fee1ab"
)
EXPECTED_REVIEW_AGGREGATE_SHA256 = (
    "603c3094daef4032d0d079e491e05d278778c32638fbba4b953f26133d330690"
)
REVIEW_SEMANTIC_FILES = (
    "standalone_reviews.json",
    "group_reviews.json",
    "source_evidence.json",
    "duplicate_clusters.json",
    "taxonomy_corrections.json",
    "content_and_scope_patches.json",
    "review_stats.json",
    "coverage_after_review.json",
    "validation_contract.json",
)
EXPECTED_PROBLEM_TYPE_GAPS = (
    "POINT_COORDINATES_3D",
    "VECTOR_COORDINATE_LINEAR_OPERATIONS_3D",
    "VECTOR_COORDINATE_ANGLE_3D",
    "PARAMETER_VECTOR_COORDINATE_CONDITION_3D",
)
EXPECTED_DUPLICATE_CLUSTERS = {
    "M12_VECTOR_CAND_0001": ("M12_VECTOR_CAND_0003",),
    "M12_VECTOR_CAND_0002": ("M12_VECTOR_CAND_0004",),
    "M12_VECTOR_CAND_0005": ("M12_VECTOR_CAND_0041",),
    "M12_VECTOR_CAND_0013": (
        "M12_VECTOR_CAND_0033",
        "M12_VECTOR_CAND_0038",
    ),
    "M12_VECTOR_CAND_0025": ("M12_VECTOR_CAND_0026",),
    "M12_VECTOR_CAND_0057": ("M12_VECTOR_CAND_0058",),
}
EXPECTED_VERIFIED_GROUP_IDS = ("M12_VECTOR_GROUP_0040",)
EXPECTED_HOLD_GROUP_IDS = (
    "M12_VECTOR_GROUP_0007",
    "M12_VECTOR_GROUP_0010",
    "M12_VECTOR_GROUP_0024",
    "M12_VECTOR_GROUP_0030",
)
EXPECTED_REJECTED_GROUP_IDS = (
    "M12_VECTOR_GROUP_0006",
    "M12_VECTOR_GROUP_0012",
    "M12_VECTOR_GROUP_0032",
    "M12_VECTOR_GROUP_0042",
    "M12_VECTOR_GROUP_0045",
    "M12_VECTOR_GROUP_0048",
    "M12_VECTOR_GROUP_0063",
    "M12_VECTOR_GROUP_0067",
    "M12_VECTOR_GROUP_0070",
)
EXPECTED_REVIEW_STATS: dict[str, Any] = {
    "review_code": "DATA-MATH12-017_VECTOR_ACADEMIC_REVIEW_V0_1",
    "base_commit": EXPECTED_BASE_COMMIT,
    "input_dataset": "DATA-MATH12-016",
    "input_effective_candidate_count": 68,
    "reviewed_candidates": 68,
    "review_status_counts": {
        "VERIFIED": 48,
        "REJECTED_DUPLICATE": 7,
        "REJECTED_OUT_OF_SCOPE_OXYZ": 9,
        "HOLD_MIXED_VECTOR_OXYZ": 4,
    },
    "verified": 48,
    "hold": 4,
    "rejected": 16,
    "rejected_duplicate": 7,
    "rejected_out_of_scope_oxyz": 9,
    "verified_standalone": 47,
    "verified_true_false_four_groups": 1,
    "true_false_four_groups_reviewed": 14,
    "true_false_child_answers_reviewed": 56,
    "standalone_answers_reviewed": 54,
    "taxonomy_corrections_standalone": 31,
    "verified_visual_required": 42,
    "problem_types_total": 15,
    "problem_types_with_verified_evidence": 11,
    "problem_type_gaps": list(EXPECTED_PROBLEM_TYPE_GAPS),
    "academic_review_complete": True,
    "production_release_eligible": 0,
    "promotion_ready": 0,
    "rights_status": "REVIEW_REQUIRED",
    "database_import_allowed": False,
    "canonical_snapshot_allowed": False,
}


@dataclass(frozen=True, slots=True, order=True)
class VectorAcademicReviewIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class VectorAcademicReviewReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, Any]
    duplicate_candidates: tuple[str, ...]
    problem_type_gaps: tuple[str, ...]
    review_aggregate_semantic_sha256: str | None
    errors: tuple[VectorAcademicReviewIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "duplicate_candidates": list(self.duplicate_candidates),
            "problem_type_gaps": list(self.problem_type_gaps),
            "review_aggregate_semantic_sha256": (
                self.review_aggregate_semantic_sha256
            ),
            "errors": [asdict(error) for error in self.errors],
        }


class VectorAcademicReviewValidator:
    """Validate the DATA-MATH12-017 overlay without producing canonical data."""

    def validate(
        self,
        review_path: Path = DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH,
        *,
        materialization_path: Path = DEFAULT_VECTOR_MATERIALIZATION_PATH,
        vector_staging_path: Path = DEFAULT_VECTOR_STAGING_PATH,
    ) -> VectorAcademicReviewReport:
        path = review_path.resolve()
        materialization_path = materialization_path.resolve()
        vector_staging_path = vector_staging_path.resolve()
        initial: list[VectorAcademicReviewIssue] = []
        manifest = self._load_object(path / "review_manifest.json", initial)
        standalone = self._load_list(path / "standalone_reviews.json", initial)
        groups = self._load_list(path / "group_reviews.json", initial)
        evidence = self._load_list(path / "source_evidence.json", initial)
        clusters = self._load_list(path / "duplicate_clusters.json", initial)
        corrections = self._load_list(path / "taxonomy_corrections.json", initial)
        patches = self._load_list(path / "content_and_scope_patches.json", initial)
        stats = self._load_object(path / "review_stats.json", initial)
        coverage = self._load_list(path / "coverage_after_review.json", initial)
        contract = self._load_object(path / "validation_contract.json", initial)
        raw_candidates = self._load_list(
            materialization_path / "candidate_questions.json",
            initial,
            check="input_identity",
        )
        effective_candidates = self._load_list(
            materialization_path / "effective_candidates.json",
            initial,
            check="input_identity",
        )
        structural_groups = self._load_list(
            materialization_path / "question_group_candidates.json",
            initial,
            check="input_identity",
        )
        problem_types = self._load_list(
            vector_staging_path / "problem_types.json",
            initial,
            check="taxonomy",
        )
        concept_rows = self._load_list(
            vector_staging_path / "problem_type_concepts.json",
            initial,
            check="taxonomy",
        )
        outcome_rows = self._load_list(
            vector_staging_path / "problem_type_learning_outcomes.json",
            initial,
            check="taxonomy",
        )

        taxonomy = self._taxonomy_maps(problem_types, concept_rows, outcome_rows)
        checks_to_errors: dict[str, list[VectorAcademicReviewIssue]] = {
            "required_files": [i for i in initial if i.check == "required_files"],
            "input_identity": [
                *[i for i in initial if i.check == "input_identity"],
                *self._validate_input_identity(
                    manifest,
                    raw_candidates,
                    effective_candidates,
                    materialization_path,
                ),
            ],
            "review_contract": self._validate_contract(contract),
            "semantic_hashes": self._validate_semantic_hashes(path, manifest),
            "aggregate_integrity": self._validate_aggregate(path, manifest),
            "exact_totals": self._validate_totals(
                manifest, stats, standalone, groups
            ),
            "review_id_partition": self._validate_id_partition(
                effective_candidates, standalone, groups
            ),
            "source_evidence": self._validate_source_evidence(
                effective_candidates, structural_groups, standalone, groups, evidence
            ),
            "standalone_semantics": self._validate_standalone(
                effective_candidates, standalone
            ),
            "duplicate_clusters": self._validate_duplicates(
                standalone, clusters
            ),
            "taxonomy": [
                *[i for i in initial if i.check == "taxonomy"],
                *self._validate_taxonomy(standalone, groups, taxonomy),
            ],
            "taxonomy_corrections": self._validate_taxonomy_corrections(
                standalone, corrections
            ),
            "content_and_scope_patches": self._validate_patches(
                standalone, groups, patches
            ),
            "question_groups": self._validate_groups(
                structural_groups, groups
            ),
            "verified_group": self._validate_verified_group(groups, evidence),
            "coverage": self._validate_coverage(
                standalone, groups, coverage, problem_types
            ),
            "promotion_boundary": self._validate_promotion_boundary(
                manifest, stats, standalone, groups, path
            ),
        }
        errors = list(initial)
        for name, check_errors in checks_to_errors.items():
            if name != "required_files":
                errors.extend(check_errors)
        checks = {name: not value for name, value in checks_to_errors.items()}
        status_counts = Counter(
            [row.get("review_status") for row in standalone]
            + [row.get("review_status") for row in groups]
        )
        duplicate_ids = tuple(
            sorted(
                row.get("candidate_id")
                for row in standalone
                if row.get("review_status") == "REJECTED_DUPLICATE"
            )
        )
        try:
            aggregate = self.aggregate_semantic_sha256(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            aggregate = None
        return VectorAcademicReviewReport(
            dataset_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts={
                "target_candidates": len(effective_candidates),
                "reviewed_candidates": len(standalone) + len(groups),
                "standalone_reviews": len(standalone),
                "group_reviews": len(groups),
                "review_status_counts": dict(status_counts),
                "true_false_child_answers_reviewed": sum(
                    len(row.get("items", [])) for row in groups
                ),
                "taxonomy_corrections_standalone": len(corrections),
                "verified_visual_required": sum(
                    row.get("review_status") == "VERIFIED"
                    and row.get("visual_asset_required") is True
                    for row in [*standalone, *groups]
                ),
                "production_release_eligible": 0,
            },
            duplicate_candidates=duplicate_ids,
            problem_type_gaps=EXPECTED_PROBLEM_TYPE_GAPS,
            review_aggregate_semantic_sha256=aggregate,
            errors=tuple(sorted(set(errors))),
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
        for name in REVIEW_SEMANTIC_FILES:
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
        errors: list[VectorAcademicReviewIssue],
        check: str,
        code: str,
        location: str,
        message: str,
    ) -> None:
        errors.append(VectorAcademicReviewIssue(check, code, location, message))

    @classmethod
    def _load_json(
        cls,
        path: Path,
        errors: list[VectorAcademicReviewIssue],
        check: str = "required_files",
    ) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            cls._add(errors, check, "INVALID_OR_MISSING_JSON", path.as_posix(), str(error))
            return None

    @classmethod
    def _load_list(
        cls,
        path: Path,
        errors: list[VectorAcademicReviewIssue],
        check: str = "required_files",
    ) -> list[dict[str, Any]]:
        value = cls._load_json(path, errors, check)
        valid = isinstance(value, list) and all(isinstance(row, dict) for row in value)
        if value is not None and not valid:
            cls._add(errors, check, "INVALID_JSON_SHAPE", path.as_posix(), "Expected object array.")
        return value if valid else []

    @classmethod
    def _load_object(
        cls,
        path: Path,
        errors: list[VectorAcademicReviewIssue],
        check: str = "required_files",
    ) -> dict[str, Any]:
        value = cls._load_json(path, errors, check)
        if value is not None and not isinstance(value, dict):
            cls._add(errors, check, "INVALID_JSON_SHAPE", path.as_posix(), "Expected object.")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _taxonomy_maps(
        problem_types: list[dict[str, Any]],
        concept_rows: list[dict[str, Any]],
        outcome_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        concepts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        outcomes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in concept_rows:
            concepts[str(row.get("problem_type_code"))].append({
                "code": row.get("concept_code"),
                "weight": row.get("weight"),
                "is_primary": row.get("is_primary"),
            })
        for row in outcome_rows:
            outcomes[str(row.get("problem_type_code"))].append({
                "code": row.get("learning_outcome_code"),
                "weight": row.get("weight"),
            })
        return {
            "problem_types": {row.get("code") for row in problem_types},
            "names": {row.get("code"): row.get("name") for row in problem_types},
            "concepts": concepts,
            "outcomes": outcomes,
        }

    @classmethod
    def _validate_input_identity(
        cls,
        manifest: dict[str, Any],
        raw_candidates: list[dict[str, Any]],
        effective_candidates: list[dict[str, Any]],
        materialization_path: Path,
    ) -> list[VectorAcademicReviewIssue]:
        errors: list[VectorAcademicReviewIssue] = []
        materialization = VectorQuestionMaterializationValidator().validate(
            materialization_path
        )
        raw_sha = VectorQuestionMaterializationValidator.semantic_sha256(raw_candidates)
        expected = {
            "dataset_code": "DATA-MATH12-017",
            "dataset_name": "MATH12_VECTOR_ACADEMIC_REVIEW_V0_1",
            "base_commit": EXPECTED_BASE_COMMIT,
            "input_materialization_dataset": "DATA-MATH12-016",
            "input_materialization_aggregate_sha256": EXPECTED_INPUT_AGGREGATE_SHA256,
            "input_raw_candidate_semantic_sha256": EXPECTED_RAW_CANDIDATE_SEMANTIC_SHA256,
            "status": "ACADEMIC_REVIEW_COMPLETE",
            "subject_code": "MATH_G12",
            "chapter_code": "VECTORS_GEOMETRY",
        }
        if any(manifest.get(field) != value for field, value in expected.items()):
            cls._add(errors, "input_identity", "REVIEW_INPUT_IDENTITY_MISMATCH", "review_manifest.json", repr(expected))
        if (
            not materialization.is_valid
            or materialization.aggregate_semantic_sha256
            != EXPECTED_INPUT_AGGREGATE_SHA256
            or raw_sha != EXPECTED_RAW_CANDIDATE_SEMANTIC_SHA256
            or len(effective_candidates) != 68
        ):
            cls._add(errors, "input_identity", "DATA_016_INPUT_DRIFT", materialization_path.as_posix(), "DATA-016 raw/effective identity no longer matches the review gate.")
        return errors

    @classmethod
    def _validate_contract(
        cls, contract: dict[str, Any]
    ) -> list[VectorAcademicReviewIssue]:
        required = contract.get("required_invariants")
        valid = (
            contract.get("contract_code") == "DATA_MATH12_017_VALIDATION_V0_1"
            and isinstance(required, dict)
            and required.get("input_base_commit") == EXPECTED_BASE_COMMIT
            and required.get("input_materialization_aggregate_sha256")
            == EXPECTED_INPUT_AGGREGATE_SHA256
            and required.get("input_raw_candidate_semantic_sha256")
            == EXPECTED_RAW_CANDIDATE_SEMANTIC_SHA256
            and required.get("reviewed_candidates") == 68
            and required.get("verified") == 48
            and required.get("hold_mixed_vector_oxyz") == 4
            and required.get("rejected_duplicate") == 7
            and required.get("rejected_out_of_scope_oxyz") == 9
            and required.get("production_release_eligible") == 0
            and required.get("database_import_allowed") is False
            and required.get("canonical_snapshot_allowed") is False
        )
        if valid:
            return []
        return [VectorAcademicReviewIssue(
            "review_contract",
            "REVIEW_VALIDATION_CONTRACT_MISMATCH",
            "validation_contract.json",
            "Review identity, totals, or release boundaries changed.",
        )]

    @classmethod
    def _validate_semantic_hashes(
        cls, path: Path, manifest: dict[str, Any]
    ) -> list[VectorAcademicReviewIssue]:
        errors: list[VectorAcademicReviewIssue] = []
        declared_order = manifest.get("semantic_files_order")
        supplied = manifest.get("semantic_file_hashes")
        if declared_order != list(REVIEW_SEMANTIC_FILES) or not isinstance(supplied, dict) or list(supplied) != list(REVIEW_SEMANTIC_FILES):
            cls._add(errors, "semantic_hashes", "REVIEW_SEMANTIC_FILE_SET_MISMATCH", "review_manifest.json", "Semantic file order must match the locked review contract.")
            return errors
        for name in REVIEW_SEMANTIC_FILES:
            try:
                value = json.loads((path / name).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                cls._add(errors, "semantic_hashes", "REVIEW_SEMANTIC_FILE_INVALID", name, str(error))
                continue
            actual = cls.semantic_sha256(value)
            if supplied.get(name) != actual:
                cls._add(errors, "semantic_hashes", "REVIEW_SEMANTIC_SHA256_MISMATCH", name, f"Expected {supplied.get(name)}; found {actual}.")
        return errors

    @classmethod
    def _validate_aggregate(
        cls, path: Path, manifest: dict[str, Any]
    ) -> list[VectorAcademicReviewIssue]:
        errors: list[VectorAcademicReviewIssue] = []
        try:
            actual = cls.aggregate_semantic_sha256(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            cls._add(errors, "aggregate_integrity", "REVIEW_AGGREGATE_INPUT_INVALID", "semantic_files", str(error))
            return errors
        declared = manifest.get("review_aggregate_semantic_sha256")
        if actual != declared or actual != EXPECTED_REVIEW_AGGREGATE_SHA256:
            cls._add(
                errors,
                "aggregate_integrity",
                "REVIEW_AGGREGATE_SEMANTIC_SHA256_MISMATCH",
                "review_manifest.json.review_aggregate_semantic_sha256",
                f"Recomputed {actual}; manifest {declared}; expected {EXPECTED_REVIEW_AGGREGATE_SHA256}.",
            )
        return errors

    @classmethod
    def _validate_totals(
        cls,
        manifest: dict[str, Any],
        stats: dict[str, Any],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> list[VectorAcademicReviewIssue]:
        statuses = Counter(
            [row.get("review_status") for row in standalone]
            + [row.get("review_status") for row in groups]
        )
        valid = (
            manifest.get("counts") == EXPECTED_REVIEW_STATS
            and stats == EXPECTED_REVIEW_STATS
            and len(standalone) == 54
            and len(groups) == 14
            and statuses == Counter(EXPECTED_REVIEW_STATS["review_status_counts"])
            and sum(len(row.get("items", [])) for row in groups) == 56
        )
        if valid:
            return []
        return [VectorAcademicReviewIssue(
            "exact_totals", "REVIEW_TOTALS_MISMATCH", "review dataset",
            f"Found standalone={len(standalone)}, groups={len(groups)}, statuses={dict(statuses)}.",
        )]

    @classmethod
    def _validate_id_partition(
        cls,
        effective: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> list[VectorAcademicReviewIssue]:
        expected = [row.get("candidate_id") for row in effective]
        reviewed = [row.get("candidate_id") for row in standalone] + [
            row.get("source_candidate_id") for row in groups
        ]
        if len(reviewed) == len(set(reviewed)) == 68 and set(reviewed) == set(expected):
            return []
        return [VectorAcademicReviewIssue(
            "review_id_partition", "REVIEW_ID_PARTITION_MISMATCH", "review rows",
            "Every effective DATA-016 candidate must occur in exactly one review row.",
        )]

    @classmethod
    def _validate_source_evidence(
        cls,
        effective: list[dict[str, Any]],
        structural_groups: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> list[VectorAcademicReviewIssue]:
        errors: list[VectorAcademicReviewIssue] = []
        candidate_by_id = {row.get("candidate_id"): row for row in effective}
        structural_by_id = {row.get("group_candidate_id"): row for row in structural_groups}
        evidence_by_id = {row.get("evidence_id"): row for row in evidence}
        if len(evidence) != len(evidence_by_id) or len(evidence) != 68:
            cls._add(errors, "source_evidence", "SOURCE_EVIDENCE_SET_MISMATCH", "source_evidence.json", "Expected one unique evidence row per reviewed candidate.")
        for row in standalone:
            raw = candidate_by_id.get(row.get("candidate_id"), {})
            evidence_row = evidence_by_id.get(row.get("source_evidence_id"), {})
            if not cls._source_matches(row, raw, evidence_row):
                cls._add(errors, "source_evidence", "STANDALONE_SOURCE_LINEAGE_MISMATCH", str(row.get("candidate_id")), "Review/evidence source identity must match DATA-016.")
        for row in groups:
            structural = structural_by_id.get(row.get("group_candidate_id"), {})
            evidence_row = evidence_by_id.get(row.get("source_evidence_id"), {})
            if (
                row.get("source_candidate_id") != structural.get("source_candidate_id")
                or row.get("source_code") != structural.get("source_code")
                or row.get("source_file_id") != structural.get("source_file_id")
                or row.get("source_sha256") != structural.get("source_sha256")
                or row.get("candidate_source_page") != structural.get("source_page")
                or evidence_row.get("candidate_id") != row.get("source_candidate_id")
                or evidence_row.get("group_candidate_id") != row.get("group_candidate_id")
                or evidence_row.get("source_file_id") != row.get("source_file_id")
                or evidence_row.get("source_sha256") != row.get("source_sha256")
            ):
                cls._add(errors, "source_evidence", "GROUP_SOURCE_LINEAGE_MISMATCH", str(row.get("group_candidate_id")), "Group review/evidence source identity must match DATA-016.")
        return errors

    @staticmethod
    def _source_matches(
        review: dict[str, Any], raw: dict[str, Any], evidence: dict[str, Any]
    ) -> bool:
        return (
            review.get("source_code") == raw.get("source_code")
            and review.get("source_file_id") == raw.get("source_file_id")
            and review.get("source_sha256") == raw.get("source_sha256")
            and review.get("candidate_source_page") == raw.get("source_page")
            and review.get("question_number") == raw.get("question_number")
            and review.get("question_type") == raw.get("question_type_detected")
            and evidence.get("candidate_id") == review.get("candidate_id")
            and evidence.get("source_code") == review.get("source_code")
            and evidence.get("source_file_id") == review.get("source_file_id")
            and evidence.get("source_sha256") == review.get("source_sha256")
            and evidence.get("candidate_source_page")
            == review.get("candidate_source_page")
        )

    @classmethod
    def _validate_standalone(
        cls,
        effective: list[dict[str, Any]],
        standalone: list[dict[str, Any]],
    ) -> list[VectorAcademicReviewIssue]:
        errors: list[VectorAcademicReviewIssue] = []
        effective_by_id = {row.get("candidate_id"): row for row in effective}
        for index, row in enumerate(standalone):
            location = f"standalone_reviews.json[{index}]"
            raw = effective_by_id.get(row.get("candidate_id"), {})
            if (
                row.get("review_status") not in {"VERIFIED", "REJECTED_DUPLICATE"}
                or row.get("correct_answer") is None
                or not str(row.get("answer_verification", "")).startswith("SOURCE_BACKED")
                or row.get("promotion_ready") is not False
                or row.get("visual_asset_required") != raw.get("visual_required")
            ):
                cls._add(errors, "standalone_semantics", "INVALID_STANDALONE_REVIEW", location, str(row.get("candidate_id")))
            if row.get("review_status") == "VERIFIED" and "RIGHTS_REVIEW_REQUIRED" not in row.get("promotion_blockers", []):
                cls._add(errors, "standalone_semantics", "VERIFIED_RIGHTS_BLOCKER_MISSING", location, str(row.get("candidate_id")))
            if row.get("visual_asset_required") is True and row.get("review_status") == "VERIFIED" and "VISUAL_ASSET_REVIEW_REQUIRED" not in row.get("promotion_blockers", []):
                cls._add(errors, "standalone_semantics", "VERIFIED_VISUAL_BLOCKER_MISSING", location, str(row.get("candidate_id")))
        return errors

    @classmethod
    def _validate_duplicates(
        cls,
        standalone: list[dict[str, Any]],
        clusters: list[dict[str, Any]],
    ) -> list[VectorAcademicReviewIssue]:
        errors: list[VectorAcademicReviewIssue] = []
        review_by_id = {row.get("candidate_id"): row for row in standalone}
        actual_clusters = {
            row.get("canonical_candidate_id"): tuple(row.get("duplicate_candidate_ids", []))
            for row in clusters
        }
        rejected = {
            row.get("candidate_id"): row.get("duplicate_of")
            for row in standalone
            if row.get("review_status") == "REJECTED_DUPLICATE"
        }
        expected_rejected = {
            duplicate: canonical
            for canonical, duplicates in EXPECTED_DUPLICATE_CLUSTERS.items()
            for duplicate in duplicates
        }
        if actual_clusters != EXPECTED_DUPLICATE_CLUSTERS or rejected != expected_rejected or len(clusters) != 6:
            cls._add(errors, "duplicate_clusters", "DUPLICATE_CLUSTER_MISMATCH", "duplicate_clusters.json", f"Clusters={actual_clusters}; rejected={rejected}.")
        for canonical in EXPECTED_DUPLICATE_CLUSTERS:
            if review_by_id.get(canonical, {}).get("review_status") != "VERIFIED":
                cls._add(errors, "duplicate_clusters", "DUPLICATE_CANONICAL_NOT_VERIFIED", canonical, "Duplicate target must be a VERIFIED canonical candidate.")
        return errors

    @classmethod
    def _validate_taxonomy(
        cls,
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        taxonomy: dict[str, Any],
    ) -> list[VectorAcademicReviewIssue]:
        errors: list[VectorAcademicReviewIssue] = []
        for index, row in enumerate(standalone):
            cls._validate_vector_taxonomy(
                row.get("reviewed_problem_type_code"),
                row.get("taxonomy"),
                taxonomy,
                errors,
                f"standalone_reviews.json[{index}].taxonomy",
                "taxonomy",
            )
        for group_index, group in enumerate(groups):
            for item_index, item in enumerate(group.get("items", [])):
                location = f"group_reviews.json[{group_index}].items[{item_index}].taxonomy"
                item_taxonomy = item.get("taxonomy")
                if item.get("scope_classification") == "OXYZ":
                    valid = (
                        item.get("taxonomy_status") == "DEFERRED_TO_OXYZ_CHAPTER"
                        and isinstance(item_taxonomy, dict)
                        and item_taxonomy.get("problem_types") == []
                        and item_taxonomy.get("concepts") == []
                        and item_taxonomy.get("learning_outcomes") == []
                    )
                    if not valid:
                        cls._add(errors, "taxonomy", "OXYZ_CHILD_HAS_VECTOR_TAXONOMY", location, "OXYZ children must defer taxonomy and carry no Vector codes.")
                elif item.get("scope_classification") == "VECTOR":
                    problem_type_rows = item_taxonomy.get("problem_types", []) if isinstance(item_taxonomy, dict) else []
                    problem_type = problem_type_rows[0].get("code") if len(problem_type_rows) == 1 and isinstance(problem_type_rows[0], dict) else None
                    cls._validate_vector_taxonomy(problem_type, item_taxonomy, taxonomy, errors, location, "taxonomy")
                elif item.get("scope_classification") == "HYBRID_VECTOR_OXYZ":
                    valid = (
                        item.get("taxonomy_status") == "HOLD_HYBRID_VECTOR_OXYZ"
                        and isinstance(item_taxonomy, dict)
                        and item_taxonomy.get("status") == "HOLD_HYBRID_VECTOR_OXYZ"
                        and item_taxonomy.get("basis")
                        == "COACH_LEARNING_DERIVED_PROVISIONAL_FOR_VECTOR_ASPECT"
                        and item_taxonomy.get("suggested_vector_problem_type_code")
                        in taxonomy["problem_types"]
                        and item_taxonomy.get("concepts") == []
                        and item_taxonomy.get("learning_outcomes") == []
                    )
                    if not valid:
                        cls._add(
                            errors,
                            "taxonomy",
                            "INVALID_HELD_HYBRID_TAXONOMY",
                            location,
                            "Hybrid taxonomy may only carry an untrusted Vector suggestion.",
                        )
                else:
                    cls._add(errors, "taxonomy", "UNKNOWN_CHILD_SCOPE", location, repr(item.get("scope_classification")))
        return errors

    @classmethod
    def _validate_vector_taxonomy(
        cls,
        problem_type: Any,
        value: Any,
        taxonomy: dict[str, Any],
        errors: list[VectorAcademicReviewIssue],
        location: str,
        check: str,
    ) -> None:
        valid = (
            isinstance(problem_type, str)
            and problem_type in taxonomy["problem_types"]
            and isinstance(value, dict)
            and value.get("basis") == "COACH_LEARNING_DERIVED"
            and value.get("problem_types")
            == [{"code": problem_type, "weight": 1.0, "is_primary": True}]
            and value.get("concepts") == taxonomy["concepts"].get(problem_type, [])
            and value.get("learning_outcomes") == taxonomy["outcomes"].get(problem_type, [])
        )
        if not valid:
            cls._add(errors, check, "VECTOR_TAXONOMY_MAPPING_MISMATCH", location, repr(problem_type))

    @classmethod
    def _validate_taxonomy_corrections(
        cls,
        standalone: list[dict[str, Any]],
        corrections: list[dict[str, Any]],
    ) -> list[VectorAcademicReviewIssue]:
        expected = {
            row.get("candidate_id"): (
                row.get("structural_problem_type_code"),
                row.get("reviewed_problem_type_code"),
                row.get("review_status"),
            )
            for row in standalone
            if row.get("structural_problem_type_code")
            != row.get("reviewed_problem_type_code")
        }
        actual = {
            row.get("candidate_id"): (
                row.get("structural_problem_type_code"),
                row.get("reviewed_problem_type_code"),
                row.get("review_status"),
            )
            for row in corrections
        }
        if len(corrections) == 31 and actual == expected:
            return []
        return [VectorAcademicReviewIssue(
            "taxonomy_corrections", "TAXONOMY_CORRECTION_SET_MISMATCH",
            "taxonomy_corrections.json", f"Expected 31 exact corrections; found {len(corrections)}.",
        )]

    @classmethod
    def _validate_patches(
        cls,
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        patches: list[dict[str, Any]],
    ) -> list[VectorAcademicReviewIssue]:
        errors: list[VectorAcademicReviewIssue] = []
        patch_by_id = {row.get("candidate_id"): row for row in patches}
        standalone_by_id = {row.get("candidate_id"): row for row in standalone}
        group_by_source = {row.get("source_candidate_id"): row for row in groups}
        if set(patch_by_id) != {
            "M12_VECTOR_CAND_0018", "M12_VECTOR_CAND_0044", "M12_VECTOR_CAND_0010"
        }:
            cls._add(errors, "content_and_scope_patches", "PATCH_SET_MISMATCH", "content_and_scope_patches.json", repr(set(patch_by_id)))
            return errors
        patch_18 = patch_by_id["M12_VECTOR_CAND_0018"]
        review_18 = standalone_by_id["M12_VECTOR_CAND_0018"]
        if (
            patch_18.get("source_question_pages") != [42]
            or patch_18.get("source_solution_pages") != [48]
            or "vector AB = vector CD" not in patch_18.get("reviewed_content", "")
            or "vector AB = vector DC" not in patch_18.get("reviewed_content", "")
            or review_18.get("correct_answer") != "A"
            or review_18.get("content_patch_required") is not True
        ):
            cls._add(errors, "content_and_scope_patches", "CANDIDATE_0018_PATCH_INVALID", "M12_VECTOR_CAND_0018", "Reviewed vector direction distinction or answer changed.")
        patch_44 = patch_by_id["M12_VECTOR_CAND_0044"]
        review_44 = standalone_by_id["M12_VECTOR_CAND_0044"]
        if (
            patch_44.get("source_question_pages") != [397, 398]
            or patch_44.get("source_solution_pages") != [404]
            or review_44.get("correct_answer") != "A"
            or review_44.get("content_patch_required") is not True
        ):
            cls._add(errors, "content_and_scope_patches", "CANDIDATE_0044_PATCH_INVALID", "M12_VECTOR_CAND_0044", "Page-spanning content/choices or answer changed.")
        patch_10 = patch_by_id["M12_VECTOR_CAND_0010"]
        group_10 = group_by_source["M12_VECTOR_CAND_0010"]
        if (
            patch_10.get("structural_mixed_scope") is not False
            or patch_10.get("reviewed_mixed_scope") is not True
            or group_10.get("structural_mixed_scope") is not False
            or group_10.get("reviewed_mixed_scope") is not True
        ):
            cls._add(errors, "content_and_scope_patches", "GROUP_0010_SCOPE_PATCH_INVALID", "M12_VECTOR_GROUP_0010", "Academic mixed-scope correction must remain overlay-only.")
        return errors

    @classmethod
    def _validate_groups(
        cls,
        structural_groups: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> list[VectorAcademicReviewIssue]:
        errors: list[VectorAcademicReviewIssue] = []
        structural_by_id = {row.get("group_candidate_id"): row for row in structural_groups}
        status_sets = {
            "VERIFIED": tuple(sorted(row.get("group_candidate_id") for row in groups if row.get("review_status") == "VERIFIED")),
            "HOLD_MIXED_VECTOR_OXYZ": tuple(sorted(row.get("group_candidate_id") for row in groups if row.get("review_status") == "HOLD_MIXED_VECTOR_OXYZ")),
            "REJECTED_OUT_OF_SCOPE_OXYZ": tuple(sorted(row.get("group_candidate_id") for row in groups if row.get("review_status") == "REJECTED_OUT_OF_SCOPE_OXYZ")),
        }
        if status_sets != {
            "VERIFIED": EXPECTED_VERIFIED_GROUP_IDS,
            "HOLD_MIXED_VECTOR_OXYZ": EXPECTED_HOLD_GROUP_IDS,
            "REJECTED_OUT_OF_SCOPE_OXYZ": EXPECTED_REJECTED_GROUP_IDS,
        }:
            cls._add(errors, "question_groups", "GROUP_STATUS_SET_MISMATCH", "group_reviews.json", repr(status_sets))
        for index, row in enumerate(groups):
            location = f"group_reviews.json[{index}]"
            structural = structural_by_id.get(row.get("group_candidate_id"), {})
            items = row.get("items")
            valid = (
                row.get("source_candidate_id") == structural.get("source_candidate_id")
                and row.get("structural_mixed_scope") == structural.get("mixed_scope")
                and row.get("promotion_ready") is False
                and isinstance(items, list)
                and len(items) == 4
                and [item.get("label") for item in items] == ["a", "b", "c", "d"]
                and [item.get("order_index") for item in items] == [0, 1, 2, 3]
                and all(item.get("correct_answer") in {"TRUE", "FALSE"} for item in items)
                and all(str(item.get("answer_status", "")).startswith("SOURCE_VERIFIED") for item in items)
            )
            if not valid:
                cls._add(errors, "question_groups", "INVALID_ATOMIC_GROUP_REVIEW", location, str(row.get("group_candidate_id")))
        return errors

    @classmethod
    def _validate_verified_group(
        cls,
        groups: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> list[VectorAcademicReviewIssue]:
        group = next((row for row in groups if row.get("group_candidate_id") == "M12_VECTOR_GROUP_0040"), {})
        evidence_row = next((row for row in evidence if row.get("group_candidate_id") == "M12_VECTOR_GROUP_0040"), {})
        valid = (
            group.get("review_status") == "VERIFIED"
            and group.get("visual_asset_required") is True
            and group.get("promotion_ready") is False
            and [item.get("correct_answer") for item in group.get("items", [])]
            == ["TRUE", "TRUE", "TRUE", "FALSE"]
            and [item.get("taxonomy", {}).get("problem_types", [{}])[0].get("code") for item in group.get("items", [])]
            == [
                "VECTOR_COORDINATES_FROM_POINTS_3D",
                "VECTOR_LENGTH_DISTANCE_3D",
                "MIDPOINT_CENTROID_COORDINATES_3D",
                "VECTOR_ANGLE_3D",
            ]
            and 368 in evidence_row.get("solution_pages", [])
        )
        if valid:
            return []
        return [VectorAcademicReviewIssue(
            "verified_group", "VERIFIED_GROUP_0040_MISMATCH",
            "M12_VECTOR_GROUP_0040", "Answer pattern, child taxonomy, evidence, or blockers changed.",
        )]

    @classmethod
    def _validate_coverage(
        cls,
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        coverage: list[dict[str, Any]],
        problem_types: list[dict[str, Any]],
    ) -> list[VectorAcademicReviewIssue]:
        errors: list[VectorAcademicReviewIssue] = []
        standalone_counts = Counter(
            row.get("reviewed_problem_type_code")
            for row in standalone
            if row.get("review_status") == "VERIFIED"
        )
        child_counts = Counter(
            item.get("taxonomy", {}).get("problem_types", [{}])[0].get("code")
            for group in groups
            if group.get("review_status") == "VERIFIED"
            for item in group.get("items", [])
        )
        coverage_by_code = {row.get("problem_type_code"): row for row in coverage}
        problem_type_by_code = {row.get("code"): row for row in problem_types}
        if len(coverage) != 15 or set(coverage_by_code) != set(problem_type_by_code):
            cls._add(errors, "coverage", "REVIEW_COVERAGE_SET_MISMATCH", "coverage_after_review.json", "Coverage must contain all 15 DATA-015 ProblemTypes.")
            return errors
        for code, problem_type in problem_type_by_code.items():
            expected = {
                "problem_type_code": code,
                "problem_type_name": problem_type.get("name"),
                "verified_standalone_count": standalone_counts[code],
                "verified_group_child_count": child_counts[code],
                "verified_evidence_units": standalone_counts[code] + child_counts[code],
                "coverage_status": "HAS_VERIFIED_EVIDENCE" if standalone_counts[code] + child_counts[code] else "GAP",
            }
            if coverage_by_code[code] != expected:
                cls._add(errors, "coverage", "REVIEW_COVERAGE_ROW_MISMATCH", code, repr(expected))
        gaps = tuple(row.get("problem_type_code") for row in coverage if row.get("coverage_status") == "GAP")
        if gaps != EXPECTED_PROBLEM_TYPE_GAPS:
            cls._add(errors, "coverage", "REVIEW_COVERAGE_GAPS_MISMATCH", "coverage_after_review.json", repr(gaps))
        return errors

    @classmethod
    def _validate_promotion_boundary(
        cls,
        manifest: dict[str, Any],
        stats: dict[str, Any],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        path: Path,
    ) -> list[VectorAcademicReviewIssue]:
        valid = (
            manifest.get("db_migration_required") is False
            and manifest.get("canonical_curriculum_modified") is False
            and manifest.get("database_import_allowed") is False
            and manifest.get("production_release_eligible") == 0
            and stats.get("production_release_eligible") == 0
            and stats.get("promotion_ready") == 0
            and stats.get("rights_status") == "REVIEW_REQUIRED"
            and stats.get("database_import_allowed") is False
            and stats.get("canonical_snapshot_allowed") is False
            and all(row.get("promotion_ready") is False for row in [*standalone, *groups])
            and not (path / "manifest.json").exists()
            and not any(file.suffix.lower() == ".pdf" for file in path.rglob("*"))
        )
        if valid:
            return []
        return [VectorAcademicReviewIssue(
            "promotion_boundary", "REVIEW_PROMOTION_BOUNDARY_VIOLATION",
            path.as_posix(), "Review data must remain non-importable, non-promotable, and rights-blocked.",
        )]
