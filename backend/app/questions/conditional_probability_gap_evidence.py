from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.questions.conditional_probability_academic_review import (
    DEFAULT_CONDITIONAL_PROBABILITY_ACADEMIC_REVIEW_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256 as EXPECTED_BASE_AGGREGATE_SHA256,
    EXPECTED_GAP as EXPECTED_BASE_GAP,
    ConditionalProbabilityAcademicReviewValidator,
)


DEFAULT_CONDITIONAL_PROBABILITY_GAP_EVIDENCE_PATH = (
    DEFAULT_CONDITIONAL_PROBABILITY_ACADEMIC_REVIEW_PATH.parents[1]
    / "gap_supplement"
    / "v0_1"
)
EXPECTED_AGGREGATE_SEMANTIC_SHA256 = (
    "0d8c45073eb9a666447d5e93f53bcfa9858298e5760fb010dbf7aa8e4bbcc690"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256 = (
    "b675899f0e7e1140dd6f777bd28a9ec49dbee47577e486285020910adaf0d91e"
)
EXPECTED_RESOLVED_GAP = "TOTAL_PROBABILITY"
SEMANTIC_FILES = (
    "verified_gap_evidence.json",
    "source_evidence.json",
    "gap_resolution.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES, "data_contract.json", "README.md")
EXPECTED_SEMANTIC_HASHES = {
    "verified_gap_evidence.json": (
        "120f42641e6163a34f4b33eef87f0e96ec44b29064ad97cbbf8c003f151cbae5"
    ),
    "source_evidence.json": (
        "f409ee9f7f3bda9e804c5f28e7b00178a8ce528c45e2a943750c1ac33b99863e"
    ),
    "gap_resolution.json": (
        "ffd6b859fec46683ac639bda8a11a258d77a44bcd48602b5689dfcc9a7e6b868"
    ),
}
EXPECTED_COUNTS = {
    "verified_gap_evidence_units": 1,
    "source_evidence_count": 1,
    "resolved_gaps": 1,
    "remaining_base_gaps": 0,
    "production_release_eligible": 0,
}


@dataclass(frozen=True, slots=True, order=True)
class ConditionalProbabilityGapEvidenceIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class ConditionalProbabilityGapEvidenceReport:
    dataset_path: str
    base_dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    resolved_gap: str
    remaining_base_gaps: tuple[str, ...]
    effective_total_probability_evidence_units: int
    canonical_candidate_created: bool
    aggregate_semantic_sha256: str | None
    rights_status: str | None
    production_release_eligible: int
    database_import_allowed: bool
    canonical_snapshot_allowed: bool
    errors: tuple[ConditionalProbabilityGapEvidenceIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "base_dataset_path": self.base_dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "resolved_gap": self.resolved_gap,
            "remaining_base_gaps": list(self.remaining_base_gaps),
            "effective_total_probability_evidence_units": (
                self.effective_total_probability_evidence_units
            ),
            "canonical_candidate_created": self.canonical_candidate_created,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "rights_status": self.rights_status,
            "production_release_eligible": self.production_release_eligible,
            "database_import_allowed": self.database_import_allowed,
            "canonical_snapshot_allowed": self.canonical_snapshot_allowed,
            "errors": [asdict(error) for error in self.errors],
        }


class ConditionalProbabilityGapEvidenceValidator:
    """Validate DATA-MATH12-030 TOTAL_PROBABILITY gap evidence supplement."""

    def validate(
        self,
        evidence_path: Path = DEFAULT_CONDITIONAL_PROBABILITY_GAP_EVIDENCE_PATH,
        *,
        base_review_path: Path = DEFAULT_CONDITIONAL_PROBABILITY_ACADEMIC_REVIEW_PATH,
    ) -> ConditionalProbabilityGapEvidenceReport:
        path = evidence_path.resolve()
        base_path = base_review_path.resolve()
        initial: list[ConditionalProbabilityGapEvidenceIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        evidence_units = self._load_list(
            path / "verified_gap_evidence.json", initial
        )
        source_evidence = self._load_list(path / "source_evidence.json", initial)
        resolution = self._load_object(path / "gap_resolution.json", initial)

        checks_to_errors: dict[
            str, list[ConditionalProbabilityGapEvidenceIssue]
        ] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_academic_review_binding": self._validate_base_review_binding(
                base_path, contract, resolution
            ),
            "gap_evidence_integrity": self._validate_gap_evidence_units(
                evidence_units, base_path
            ),
            "source_evidence_integrity": self._validate_source_evidence(
                source_evidence, evidence_units
            ),
            "gap_resolution_contract": self._validate_gap_resolution(
                resolution, evidence_units, contract
            ),
            "release_boundary": self._validate_release_boundary(
                contract, evidence_units, resolution
            ),
        }
        for issue in initial:
            if issue.check != "required_files":
                checks_to_errors.setdefault(issue.check, []).append(issue)

        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[ConditionalProbabilityGapEvidenceIssue] = []
        expected_aggregate = contract.get("aggregate_semantic_sha256")
        if aggregate != EXPECTED_AGGREGATE_SEMANTIC_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_AGGREGATE_SEMANTIC_SHA256}, got {aggregate!r}.",
                )
            )
        if expected_aggregate != EXPECTED_AGGREGATE_SEMANTIC_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-030 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        errors = tuple(
            sorted(issue for issues in checks_to_errors.values() for issue in issues)
        )
        remaining = tuple(
            str(x)
            for x in resolution.get(
                "remaining_data_math12_025_gap_after_overlay", []
            )
            if isinstance(x, str)
        )
        resolved_gap = str(resolution.get("resolved_gap") or EXPECTED_RESOLVED_GAP)
        counts = {
            "verified_gap_evidence_units": len(evidence_units),
            "source_evidence_count": len(source_evidence),
            "resolved_gaps": (
                1 if resolution.get("resolved_gap") == EXPECTED_RESOLVED_GAP else 0
            ),
            "remaining_base_gaps": len(remaining),
            "production_release_eligible": self._int_value(
                resolution.get("production_release_eligible"), default=-1
            ),
        }
        if counts != EXPECTED_COUNTS:
            errors = tuple(
                sorted(
                    (
                        *errors,
                        self._issue(
                            "exact_counts",
                            "COUNT_MISMATCH",
                            "gap_resolution.json",
                            f"Expected {EXPECTED_COUNTS!r}, got {counts!r}.",
                        ),
                    )
                )
            )
        checks = {
            name: not issues for name, issues in checks_to_errors.items()
        }
        checks["exact_counts"] = counts == EXPECTED_COUNTS

        return ConditionalProbabilityGapEvidenceReport(
            dataset_path=str(path),
            base_dataset_path=str(base_path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            resolved_gap=resolved_gap,
            remaining_base_gaps=remaining,
            effective_total_probability_evidence_units=len(evidence_units),
            canonical_candidate_created=(
                resolution.get("canonical_candidate_created") is True
            ),
            aggregate_semantic_sha256=aggregate,
            rights_status=resolution.get("rights_status"),
            production_release_eligible=self._int_value(
                resolution.get("production_release_eligible"), default=-1
            ),
            database_import_allowed=resolution.get("database_import_allowed") is True,
            canonical_snapshot_allowed=(
                resolution.get("canonical_snapshot_allowed") is True
            ),
            errors=errors,
        )

    def _validate_curated_hash_contract(
        self, path: Path, contract: dict[str, Any]
    ) -> list[ConditionalProbabilityGapEvidenceIssue]:
        issues: list[ConditionalProbabilityGapEvidenceIssue] = []
        contract_path = path / "data_contract.json"
        if contract_path.is_file():
            actual_contract_hash = self._semantic_hash(contract_path)
            if actual_contract_hash != EXPECTED_CONTRACT_SEMANTIC_SHA256:
                issues.append(
                    self._issue(
                        "curated_hash_contract",
                        "CONTRACT_HASH_MISMATCH",
                        contract_path.name,
                        "The curated data_contract changed semantically.",
                    )
                )
        expected_hashes = contract.get("semantic_sha256")
        order = contract.get("semantic_files_order")
        if not isinstance(expected_hashes, dict) or not isinstance(order, list):
            return [
                *issues,
                self._issue(
                    "curated_hash_contract",
                    "INVALID_SEMANTIC_HASH_CONTRACT",
                    contract_path.name,
                    "semantic_sha256 and semantic_files_order are required.",
                ),
            ]
        if set(order) != set(expected_hashes) or tuple(order) != SEMANTIC_FILES:
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "SEMANTIC_FILE_SET_MISMATCH",
                    contract_path.name,
                    "Semantic file order does not match expected supplement files.",
                )
            )
        for name, expected in expected_hashes.items():
            file_path = path / str(name)
            actual = self._semantic_hash(file_path) if file_path.is_file() else None
            if actual != expected:
                issues.append(
                    self._issue(
                        "curated_hash_contract",
                        "SEMANTIC_HASH_MISMATCH",
                        str(name),
                        f"Expected {expected!r}, got {actual!r}.",
                    )
                )
        return issues

    def _validate_base_review_binding(
        self,
        base_path: Path,
        contract: dict[str, Any],
        resolution: dict[str, Any],
    ) -> list[ConditionalProbabilityGapEvidenceIssue]:
        issues: list[ConditionalProbabilityGapEvidenceIssue] = []
        base_report = ConditionalProbabilityAcademicReviewValidator().validate(
            base_path
        )
        if not base_report.is_valid:
            issues.append(
                self._issue(
                    "base_academic_review_binding",
                    "BASE_REVIEW_INVALID",
                    str(base_path),
                    "DATA-MATH12-025 validation did not pass.",
                )
            )
        if (
            base_report.aggregate_semantic_sha256
            != EXPECTED_BASE_AGGREGATE_SHA256
        ):
            issues.append(
                self._issue(
                    "base_academic_review_binding",
                    "BASE_AGGREGATE_MISMATCH",
                    str(base_path),
                    "DATA-MATH12-025 aggregate hash does not match locked state.",
                )
            )
        if contract.get("base_dataset") != "DATA-MATH12-025":
            issues.append(
                self._issue(
                    "base_academic_review_binding",
                    "BASE_DATASET_CODE_MISMATCH",
                    "data_contract.json",
                    "base_dataset must be DATA-MATH12-025.",
                )
            )
        if (
            contract.get("base_aggregate_semantic_sha256")
            != EXPECTED_BASE_AGGREGATE_SHA256
        ):
            issues.append(
                self._issue(
                    "base_academic_review_binding",
                    "CONTRACT_BASE_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "Contract base aggregate sha256 mismatch.",
                )
            )
        if resolution.get("base_dataset") != "DATA-MATH12-025":
            issues.append(
                self._issue(
                    "base_academic_review_binding",
                    "RESOLUTION_BASE_DATASET_MISMATCH",
                    "gap_resolution.json",
                    "base_dataset in resolution must be DATA-MATH12-025.",
                )
            )
        if (
            resolution.get("base_aggregate_semantic_sha256")
            != EXPECTED_BASE_AGGREGATE_SHA256
        ):
            issues.append(
                self._issue(
                    "base_academic_review_binding",
                    "RESOLUTION_BASE_AGGREGATE_MISMATCH",
                    "gap_resolution.json",
                    "Resolution base aggregate sha256 mismatch.",
                )
            )
        return issues

    def _validate_gap_evidence_units(
        self,
        evidence_units: list[dict[str, Any]],
        base_path: Path,
    ) -> list[ConditionalProbabilityGapEvidenceIssue]:
        issues: list[ConditionalProbabilityGapEvidenceIssue] = []
        if len(evidence_units) != 1:
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "GAP_EVIDENCE_COUNT_MISMATCH",
                    "verified_gap_evidence.json",
                    f"Expected 1 verified gap evidence unit, got {len(evidence_units)}.",
                )
            )
            return issues

        row = evidence_units[0]
        loc = "verified_gap_evidence.json[0]"
        if row.get("evidence_unit_id") != "M12_PROB_GAP_0001":
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "EVIDENCE_UNIT_ID_MISMATCH",
                    loc,
                    "Expected evidence_unit_id M12_PROB_GAP_0001.",
                )
            )
        if row.get("source_parent_candidate_id") != "M12_PROB_CAND_0012":
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "PARENT_CANDIDATE_ID_MISMATCH",
                    loc,
                    "Expected parent candidate M12_PROB_CAND_0012.",
                )
            )
        if row.get("source_child_label") != "c":
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "CHILD_LABEL_MISMATCH",
                    loc,
                    "Expected source_child_label 'c'.",
                )
            )
        if row.get("target_gap") != EXPECTED_RESOLVED_GAP:
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "TARGET_GAP_MISMATCH",
                    loc,
                    f"target_gap must be {EXPECTED_RESOLVED_GAP}.",
                )
            )
        if row.get("problem_type_code") != EXPECTED_RESOLVED_GAP:
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "PROBLEM_TYPE_MISMATCH",
                    loc,
                    f"problem_type_code must be {EXPECTED_RESOLVED_GAP}.",
                )
            )
        if row.get("evidence_unit_type") != "TRUE_FALSE_CHILD_SOURCE_EVIDENCE":
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "EVIDENCE_UNIT_TYPE_MISMATCH",
                    loc,
                    "evidence_unit_type must be TRUE_FALSE_CHILD_SOURCE_EVIDENCE.",
                )
            )
        if row.get("correct_answer") is not True:
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "ANSWER_MISMATCH",
                    loc,
                    "correct_answer must be true.",
                )
            )
        if row.get("answer_verification") != "SOURCE_SOLUTION_EXPLICIT":
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "ANSWER_VERIFICATION_MISMATCH",
                    loc,
                    "answer_verification must be SOURCE_SOLUTION_EXPLICIT.",
                )
            )
        if (
            row.get("question_start_page") != 159
            or row.get("solution_answer_page") != 169
        ):
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "PAGE_LINEAGE_MISMATCH",
                    loc,
                    "question_start_page must be 159 and solution_answer_page must be 169.",
                )
            )
        formula = row.get("source_solution_formula")
        if not isinstance(formula, str) or "0,014" not in formula:
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "FORMULA_MISMATCH",
                    loc,
                    "source_solution_formula must be non-empty and evaluate to 0,014.",
                )
            )
        if row.get("canonical_candidate_created") is not False:
            issues.append(
                self._issue(
                    "gap_evidence_integrity",
                    "CANONICAL_CANDIDATE_POLICY_VIOLATION",
                    loc,
                    "canonical_candidate_created must be false.",
                )
            )

        return issues

    def _validate_source_evidence(
        self,
        evidence: list[dict[str, Any]],
        units: list[dict[str, Any]],
    ) -> list[ConditionalProbabilityGapEvidenceIssue]:
        issues: list[ConditionalProbabilityGapEvidenceIssue] = []
        if len(evidence) != 1:
            issues.append(
                self._issue(
                    "source_evidence_integrity",
                    "EVIDENCE_COUNT_MISMATCH",
                    "source_evidence.json",
                    f"Expected 1 source evidence entry, got {len(evidence)}.",
                )
            )
            return issues

        ev = evidence[0]
        loc = "source_evidence.json[0]"
        u = units[0] if units else {}

        if ev.get("evidence_id") != "M12_PROB_GAP_EVID_0001":
            issues.append(
                self._issue(
                    "source_evidence_integrity",
                    "EVIDENCE_ID_MISMATCH",
                    loc,
                    "Expected evidence_id M12_PROB_GAP_EVID_0001.",
                )
            )
        if ev.get("evidence_unit_id") != u.get("evidence_unit_id"):
            issues.append(
                self._issue(
                    "source_evidence_integrity",
                    "EVIDENCE_UNIT_ID_MISMATCH",
                    loc,
                    "evidence_unit_id does not match verified evidence unit.",
                )
            )
        if ev.get("source_parent_candidate_id") != u.get(
            "source_parent_candidate_id"
        ):
            issues.append(
                self._issue(
                    "source_evidence_integrity",
                    "EVIDENCE_PARENT_ID_MISMATCH",
                    loc,
                    "source_parent_candidate_id does not match verified evidence unit.",
                )
            )
        if ev.get("source_child_label") != u.get("source_child_label"):
            issues.append(
                self._issue(
                    "source_evidence_integrity",
                    "EVIDENCE_CHILD_LABEL_MISMATCH",
                    loc,
                    "source_child_label does not match verified evidence unit.",
                )
            )
        if ev.get("question_page") != u.get("question_start_page"):
            issues.append(
                self._issue(
                    "source_evidence_integrity",
                    "EVIDENCE_PAGE_MISMATCH",
                    loc,
                    "question_page does not match question_start_page.",
                )
            )
        if ev.get("solution_answer_page") != u.get("solution_answer_page"):
            issues.append(
                self._issue(
                    "source_evidence_integrity",
                    "EVIDENCE_SOLUTION_PAGE_MISMATCH",
                    loc,
                    "solution_answer_page does not match verified evidence unit.",
                )
            )
        if ev.get("source_claimed_answer") != u.get("correct_answer"):
            issues.append(
                self._issue(
                    "source_evidence_integrity",
                    "CLAIMED_ANSWER_MISMATCH",
                    loc,
                    "source_claimed_answer does not match correct_answer.",
                )
            )
        if ev.get("source_solution_key_text") != "c) ĐÚNG":
            issues.append(
                self._issue(
                    "source_evidence_integrity",
                    "SOLUTION_KEY_TEXT_MISMATCH",
                    loc,
                    "source_solution_key_text mismatch; expected 'c) ĐÚNG'.",
                )
            )
        if ev.get("review_consistency") != "CONFIRMED":
            issues.append(
                self._issue(
                    "source_evidence_integrity",
                    "CONSISTENCY_NOT_CONFIRMED",
                    loc,
                    "review_consistency must be CONFIRMED.",
                )
            )

        return issues

    def _validate_gap_resolution(
        self,
        resolution: dict[str, Any],
        units: list[dict[str, Any]],
        contract: dict[str, Any],
    ) -> list[ConditionalProbabilityGapEvidenceIssue]:
        issues: list[ConditionalProbabilityGapEvidenceIssue] = []
        if resolution.get("dataset_code") != "DATA-MATH12-030":
            issues.append(
                self._issue(
                    "gap_resolution_contract",
                    "DATASET_CODE_MISMATCH",
                    "gap_resolution.json",
                    "dataset_code must be DATA-MATH12-030.",
                )
            )
        if resolution.get("resolved_gap") != EXPECTED_RESOLVED_GAP:
            issues.append(
                self._issue(
                    "gap_resolution_contract",
                    "RESOLVED_GAP_MISMATCH",
                    "gap_resolution.json",
                    f"resolved_gap must be {EXPECTED_RESOLVED_GAP}.",
                )
            )
        if resolution.get("verified_gap_evidence_units") != len(units):
            issues.append(
                self._issue(
                    "gap_resolution_contract",
                    "VERIFIED_UNIT_COUNT_MISMATCH",
                    "gap_resolution.json",
                    "verified_gap_evidence_units must match number of verified evidence units.",
                )
            )
        if (
            resolution.get("resolution_basis")
            != "SOURCE_BACKED_CHILD_EVIDENCE_FROM_TRUE_FALSE_GROUP"
        ):
            issues.append(
                self._issue(
                    "gap_resolution_contract",
                    "RESOLUTION_BASIS_MISMATCH",
                    "gap_resolution.json",
                    "resolution_basis must be SOURCE_BACKED_CHILD_EVIDENCE_FROM_TRUE_FALSE_GROUP.",
                )
            )
        if resolution.get("canonical_candidate_created") is not False:
            issues.append(
                self._issue(
                    "gap_resolution_contract",
                    "CANONICAL_CANDIDATE_POLICY_VIOLATION",
                    "gap_resolution.json",
                    "canonical_candidate_created must be false.",
                )
            )
        if resolution.get("remaining_data_math12_025_gap_after_overlay") != []:
            issues.append(
                self._issue(
                    "gap_resolution_contract",
                    "REMAINING_GAP_NONEMPTY",
                    "gap_resolution.json",
                    "remaining_data_math12_025_gap_after_overlay must be empty.",
                )
            )
        return issues

    def _validate_release_boundary(
        self,
        contract: dict[str, Any],
        units: list[dict[str, Any]],
        resolution: dict[str, Any],
    ) -> list[ConditionalProbabilityGapEvidenceIssue]:
        issues: list[ConditionalProbabilityGapEvidenceIssue] = []
        for idx, row in enumerate(units):
            loc = f"verified_gap_evidence.json[{idx}]"
            if row.get("rights_status") != "REVIEW_REQUIRED":
                issues.append(
                    self._issue(
                        "release_boundary",
                        "RIGHTS_NOT_REVIEW_REQUIRED",
                        loc,
                        "rights_status must be REVIEW_REQUIRED.",
                    )
                )
            if row.get("promotion_ready") is not False:
                issues.append(
                    self._issue(
                        "release_boundary",
                        "PROMOTION_NOT_BLOCKED",
                        loc,
                        "promotion_ready must be False.",
                    )
                )
            if (
                row.get("database_import_allowed") is not False
                or row.get("canonical_snapshot_allowed") is not False
            ):
                issues.append(
                    self._issue(
                        "release_boundary",
                        "UNAUTHORIZED_RELEASE",
                        loc,
                        "database_import_allowed and canonical_snapshot_allowed must be False.",
                    )
                )

        if resolution.get("rights_status") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "release_boundary",
                    "RIGHTS_NOT_REVIEW_REQUIRED",
                    "gap_resolution.json",
                    "rights_status must be REVIEW_REQUIRED.",
                )
            )
        if resolution.get("production_release_eligible") != 0:
            issues.append(
                self._issue(
                    "release_boundary",
                    "PRODUCTION_RELEASE_COUNT_NONZERO",
                    "gap_resolution.json",
                    "production_release_eligible must be 0.",
                )
            )
        if resolution.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "release_boundary",
                    "DB_IMPORT_NOT_BLOCKED",
                    "gap_resolution.json",
                    "database_import_allowed must be False.",
                )
            )
        if resolution.get("canonical_snapshot_allowed") is not False:
            issues.append(
                self._issue(
                    "release_boundary",
                    "CANONICAL_SNAPSHOT_NOT_BLOCKED",
                    "gap_resolution.json",
                    "canonical_snapshot_allowed must be False.",
                )
            )

        policy = contract.get("policy", {})
        if policy.get("overlay_only_do_not_rewrite_base_data") is not True:
            issues.append(
                self._issue(
                    "release_boundary",
                    "OVERLAY_POLICY_VIOLATION",
                    "data_contract.json",
                    "overlay_only_do_not_rewrite_base_data must be true.",
                )
            )
        if (
            policy.get("true_false_child_must_preserve_parent_lineage")
            is not True
        ):
            issues.append(
                self._issue(
                    "release_boundary",
                    "CHILD_LINEAGE_POLICY_VIOLATION",
                    "data_contract.json",
                    "true_false_child_must_preserve_parent_lineage must be true.",
                )
            )
        if policy.get("no_synthetic_gap_fill") is not True:
            issues.append(
                self._issue(
                    "release_boundary",
                    "SYNTHETIC_GAP_FILL_POLICY_VIOLATION",
                    "data_contract.json",
                    "no_synthetic_gap_fill must be true.",
                )
            )
        return issues

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[ConditionalProbabilityGapEvidenceIssue]:
        issues: list[ConditionalProbabilityGapEvidenceIssue] = []
        pdf_files = list(path.rglob("*.pdf"))
        if pdf_files:
            issues.append(
                self._issue(
                    "no_pdf_binaries",
                    "PDF_BINARY_PRESENT",
                    str(pdf_files[0]),
                    "Raw PDF binaries must not be present in gap supplement directory.",
                )
            )
        return issues

    def _aggregate_hash(
        self, path: Path, contract: dict[str, Any]
    ) -> str | None:
        order = contract.get("semantic_files_order")
        if not isinstance(order, list):
            return None
        digest = hashlib.sha256()
        try:
            for name in order:
                name = str(name)
                data = json.loads((path / name).read_text(encoding="utf-8"))
                canonical = json.dumps(
                    data,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                digest.update(name.encode("utf-8"))
                digest.update(b"\0")
                digest.update(canonical)
                digest.update(b"\0")
        except (OSError, json.JSONDecodeError, TypeError, UnicodeError):
            return None
        return digest.hexdigest()

    @staticmethod
    def _semantic_hash(path: Path) -> str | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return None
        return hashlib.sha256(
            json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _check_required_files(
        self, path: Path, issues: list[ConditionalProbabilityGapEvidenceIssue]
    ) -> None:
        for name in REQUIRED_FILES:
            if not (path / name).is_file():
                issues.append(
                    self._issue(
                        "required_files",
                        "MISSING_REQUIRED_FILE",
                        name,
                        f"Required file {name} is missing.",
                    )
                )

    def _load_list(
        self, path: Path, issues: list[ConditionalProbabilityGapEvidenceIssue]
    ) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list) and all(isinstance(row, dict) for row in payload):
                return payload
            issues.append(
                self._issue(
                    "required_files",
                    "INVALID_JSON_STRUCTURE",
                    path.name,
                    f"Expected list of objects in {path.name}.",
                )
            )
            return []
        except (OSError, json.JSONDecodeError) as e:
            issues.append(
                self._issue(
                    "required_files",
                    "JSON_LOAD_ERROR",
                    path.name,
                    f"Error reading {path.name}: {e}",
                )
            )
            return []

    def _load_object(
        self, path: Path, issues: list[ConditionalProbabilityGapEvidenceIssue]
    ) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
            issues.append(
                self._issue(
                    "required_files",
                    "INVALID_JSON_STRUCTURE",
                    path.name,
                    f"Expected JSON object in {path.name}.",
                )
            )
            return {}
        except (OSError, json.JSONDecodeError) as e:
            issues.append(
                self._issue(
                    "required_files",
                    "JSON_LOAD_ERROR",
                    path.name,
                    f"Error reading {path.name}: {e}",
                )
            )
            return {}

    @staticmethod
    def _int_value(val: Any, default: int = -1) -> int:
        if isinstance(val, int) and not isinstance(val, bool):
            return val
        return default

    @staticmethod
    def _issue(
        check: str, code: str, location: str, message: str
    ) -> ConditionalProbabilityGapEvidenceIssue:
        return ConditionalProbabilityGapEvidenceIssue(
            check=check, code=code, location=location, message=message
        )
