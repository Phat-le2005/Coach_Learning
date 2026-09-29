from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.questions.integrals_academic_review import (
    DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256 as EXPECTED_BASE_AGGREGATE_SHA256,
    EXPECTED_GAP as EXPECTED_BASE_GAP,
    IntegralsAcademicReviewValidator,
)


DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH = (
    DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH.parents[1]
    / "gap_supplement"
    / "v0_1"
)
EXPECTED_AGGREGATE_SEMANTIC_SHA256 = (
    "56de89cf49bea7cfcb4ba1b3ec5b3b8daac6ca8d7da4a2397076f835f335cd5f"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256 = (
    "75542ec2f23a615513e5dfbf96e8800489afe2b972a489c903fa85ffa796e805"
)
EXPECTED_RESOLVED_GAP = "CALCULATE_DEFINITE_INTEGRAL"
EXPECTED_GROUPED_DISPERSION_GAPS = (
    "IDENTIFY_MORE_STABLE_GROUPED_DATA",
    "INTERPRET_GROUPED_DISPERSION_MEASURE",
    "CONCLUDE_FROM_GROUPED_DISPERSION",
    "PARAMETER_FROM_GROUPED_VARIANCE_SD",
    "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS",
)
SEMANTIC_FILES = (
    "verified_gap_questions.json",
    "source_evidence.json",
    "gap_resolution.json",
    "remaining_gap_scan.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES, "data_contract.json", "README.md")
EXPECTED_SEMANTIC_HASHES = {
    "verified_gap_questions.json": (
        "321b360edce8bc7aeafc7599d08a9f0dd2c79a431f7a1ff08eab4a4cd101371f"
    ),
    "source_evidence.json": (
        "61ed7d8a51c71a2c2b28a4d2bdf0dba6d1210f9478e872a39edf46efdf172680"
    ),
    "gap_resolution.json": (
        "49c251414489bebfbdc81e4d1de581b5f3d1ba656cccc62049dfc9df78ae9db9"
    ),
    "remaining_gap_scan.json": (
        "66641ac9f9fbd6fe3adb8ee883d38cad660431ad6a5fc1e8645a60f874015af4"
    ),
}
EXPECTED_COUNTS = {
    "verified_gap_candidates": 2,
    "source_evidence_count": 2,
    "resolved_gaps": 1,
    "remaining_base_gaps": 0,
    "grouped_dispersion_new_gap_candidates": 0,
    "grouped_dispersion_remaining_gaps": 5,
    "production_release_eligible": 0,
}


@dataclass(frozen=True, slots=True, order=True)
class IntegralsGapSupplementIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class IntegralsGapSupplementReport:
    dataset_path: str
    base_dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    resolved_gap: str
    remaining_base_gaps: tuple[str, ...]
    effective_definite_integral_coverage: int
    aggregate_semantic_sha256: str | None
    rights_status: str | None
    production_release_eligible: int
    database_import_allowed: bool
    canonical_snapshot_allowed: bool
    errors: tuple[IntegralsGapSupplementIssue, ...]

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
            "effective_definite_integral_coverage": self.effective_definite_integral_coverage,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "rights_status": self.rights_status,
            "production_release_eligible": self.production_release_eligible,
            "database_import_allowed": self.database_import_allowed,
            "canonical_snapshot_allowed": self.canonical_snapshot_allowed,
            "errors": [asdict(error) for error in self.errors],
        }


class IntegralsGapSupplementValidator:
    """Validate DATA-MATH12-026 as an immutable overlay on DATA-MATH12-023."""

    def validate(
        self,
        path: Path = DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH,
        base_path: Path = DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH,
    ) -> IntegralsGapSupplementReport:
        dataset_path = path.resolve()
        base_dataset_path = base_path.resolve()
        initial: list[IntegralsGapSupplementIssue] = []
        self._check_required_files(dataset_path, initial)

        contract = self._load_object(dataset_path / "data_contract.json", initial)
        gap_questions = self._load_list(
            dataset_path / "verified_gap_questions.json", initial
        )
        evidence = self._load_list(dataset_path / "source_evidence.json", initial)
        resolution = self._load_object(
            dataset_path / "gap_resolution.json", initial
        )
        remaining_scan = self._load_object(
            dataset_path / "remaining_gap_scan.json", initial
        )

        evidence_by_candidate = {
            row.get("candidate_id"): row
            for row in evidence
            if isinstance(row.get("candidate_id"), str)
        }

        # Validate base dataset DATA-MATH12-023
        base_report = IntegralsAcademicReviewValidator().validate(base_dataset_path)
        base_sources: dict[str, dict[str, Any]] = {}
        if base_report.is_valid:
            try:
                base_sources_list = json.loads(
                    (base_dataset_path / "source_registry.json").read_text(encoding="utf-8")
                )
                if isinstance(base_sources_list, list):
                    base_sources = {
                        row.get("source_code"): row
                        for row in base_sources_list
                        if isinstance(row, dict) and isinstance(row.get("source_code"), str)
                    }
            except Exception:
                pass

        check_errors: dict[str, list[IntegralsGapSupplementIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(dataset_path),
            "semantic_hash_contract": self._validate_semantic_hash_contract(
                dataset_path, contract
            ),
            "base_dataset_binding": self._validate_base_binding(
                contract, resolution, base_report
            ),
            "verified_gap_questions": self._validate_gap_questions(
                gap_questions, base_sources, evidence_by_candidate
            ),
            "source_evidence": self._validate_evidence(
                evidence, gap_questions, base_sources
            ),
            "gap_resolution": self._validate_resolution(resolution, gap_questions),
            "remaining_gap_scan": self._validate_remaining_scan(remaining_scan),
            "release_boundary": self._validate_release_boundary(
                gap_questions, resolution, contract
            ),
        }
        for issue in initial:
            if issue.check != "required_files":
                check_errors.setdefault(issue.check, []).append(issue)

        counts = {
            "verified_gap_candidates": len(gap_questions),
            "source_evidence_count": len(evidence),
            "resolved_gaps": 1 if resolution.get("resolved_gap") == EXPECTED_RESOLVED_GAP else 0,
            "remaining_base_gaps": len(resolution.get("remaining_data_math12_023_gap_after_overlay", [])),
            "grouped_dispersion_new_gap_candidates": self._int(
                remaining_scan.get("new_source_backed_verified_candidates_found"), default=-1
            ),
            "grouped_dispersion_remaining_gaps": len(
                remaining_scan.get("grouped_data_dispersion_original_gaps", [])
            ),
            "production_release_eligible": 0,
        }
        if counts != EXPECTED_COUNTS:
            check_errors["exact_counts"] = [
                self._issue(
                    "exact_counts",
                    "COUNT_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_COUNTS!r}, got {counts!r}.",
                )
            ]
        else:
            check_errors["exact_counts"] = []

        all_errors = tuple(
            sorted({issue for issues in check_errors.values() for issue in issues})
        )
        semantic_ok = not check_errors["semantic_hash_contract"]
        aggregate = EXPECTED_AGGREGATE_SEMANTIC_SHA256 if semantic_ok else None
        return IntegralsGapSupplementReport(
            dataset_path=str(dataset_path),
            base_dataset_path=str(base_dataset_path),
            status="PASS" if not all_errors else "FAIL",
            checks={name: not errors for name, errors in check_errors.items()},
            counts=counts,
            resolved_gap=EXPECTED_RESOLVED_GAP,
            remaining_base_gaps=(),
            effective_definite_integral_coverage=len(gap_questions),
            aggregate_semantic_sha256=aggregate,
            rights_status=(
                resolution.get("rights_status")
                if isinstance(resolution.get("rights_status"), str)
                else None
            ),
            production_release_eligible=0,
            database_import_allowed=resolution.get("database_import_allowed") is True,
            canonical_snapshot_allowed=(
                resolution.get("canonical_snapshot_allowed") is True
            ),
            errors=all_errors,
        )

    def _validate_semantic_hash_contract(
        self, path: Path, contract: dict[str, Any]
    ) -> list[IntegralsGapSupplementIssue]:
        issues: list[IntegralsGapSupplementIssue] = []
        contract_path = path / "data_contract.json"
        if self.semantic_sha256(contract) != EXPECTED_CONTRACT_SEMANTIC_SHA256:
            issues.append(
                self._issue(
                    "semantic_hash_contract",
                    "DATA_CONTRACT_HASH_MISMATCH",
                    contract_path.name,
                    "The curated DATA-MATH12-026 contract changed semantically.",
                )
            )
        if contract.get("semantic_files_order") != list(SEMANTIC_FILES):
            issues.append(
                self._issue(
                    "semantic_hash_contract",
                    "SEMANTIC_FILE_ORDER_MISMATCH",
                    contract_path.name,
                    "Semantic file order differs from the curated contract.",
                )
            )
        if contract.get("semantic_sha256") != EXPECTED_SEMANTIC_HASHES:
            issues.append(
                self._issue(
                    "semantic_hash_contract",
                    "SEMANTIC_HASH_MAP_MISMATCH",
                    contract_path.name,
                    "Semantic hash map differs from the locked review input.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_AGGREGATE_SEMANTIC_SHA256
        ):
            issues.append(
                self._issue(
                    "semantic_hash_contract",
                    "AGGREGATE_HASH_MISMATCH",
                    contract_path.name,
                    "Locked aggregate semantic SHA-256 does not match.",
                )
            )
        for name, expected in EXPECTED_SEMANTIC_HASHES.items():
            file_path = path / name
            actual = self._semantic_file_sha256(file_path)
            if actual != expected:
                issues.append(
                    self._issue(
                        "semantic_hash_contract",
                        "SEMANTIC_FILE_HASH_MISMATCH",
                        name,
                        f"Expected {expected}, got {actual!r}.",
                    )
                )
        return issues

    def _validate_base_binding(
        self,
        contract: dict[str, Any],
        resolution: dict[str, Any],
        base_report: Any,
    ) -> list[IntegralsGapSupplementIssue]:
        issues: list[IntegralsGapSupplementIssue] = []
        if contract.get("base_dataset") != "DATA-MATH12-023":
            issues.append(
                self._issue(
                    "base_dataset_binding",
                    "BASE_DATASET_CODE_MISMATCH",
                    "data_contract.json:base_dataset",
                    "Base dataset must be DATA-MATH12-023.",
                )
            )
        if resolution.get("base_dataset") != "DATA-MATH12-023":
            issues.append(
                self._issue(
                    "base_dataset_binding",
                    "BASE_DATASET_CODE_MISMATCH",
                    "gap_resolution.json:base_dataset",
                    "Base dataset in gap_resolution must be DATA-MATH12-023.",
                )
            )
        if not base_report.is_valid:
            issues.append(
                self._issue(
                    "base_dataset_binding",
                    "BASE_DATASET_INVALID",
                    "DATA-MATH12-023",
                    "Base dataset DATA-MATH12-023 validation failed.",
                )
            )
        elif base_report.aggregate_semantic_sha256 != EXPECTED_BASE_AGGREGATE_SHA256:
            issues.append(
                self._issue(
                    "base_dataset_binding",
                    "BASE_DATASET_MUTATED",
                    "DATA-MATH12-023",
                    "Base dataset DATA-MATH12-023 was mutated or changed.",
                )
            )
        elif base_report.problem_type_gaps != (EXPECTED_BASE_GAP,):
            issues.append(
                self._issue(
                    "base_dataset_binding",
                    "BASE_GAP_MISMATCH",
                    "DATA-MATH12-023",
                    f"Base dataset gaps expected to be ({EXPECTED_BASE_GAP!r},), got {base_report.problem_type_gaps!r}.",
                )
            )
        return issues

    def _validate_gap_questions(
        self,
        rows: list[dict[str, Any]],
        base_sources: dict[str, dict[str, Any]],
        evidence: dict[str, dict[str, Any]],
    ) -> list[IntegralsGapSupplementIssue]:
        issues: list[IntegralsGapSupplementIssue] = []
        if len(rows) != 2:
            issues.append(
                self._issue(
                    "verified_gap_questions",
                    "GAP_QUESTION_COUNT_MISMATCH",
                    "verified_gap_questions.json",
                    f"Expected exactly 2 verified gap questions, got {len(rows)}.",
                )
            )
        expected_ids = {"M12_INT_GAP_CAND_0001", "M12_INT_GAP_CAND_0002"}
        actual_ids = {row.get("candidate_id") for row in rows}
        if actual_ids != expected_ids:
            issues.append(
                self._issue(
                    "verified_gap_questions",
                    "GAP_QUESTION_IDS_MISMATCH",
                    "verified_gap_questions.json",
                    f"Expected candidate IDs {expected_ids!r}, got {actual_ids!r}.",
                )
            )
        for index, row in enumerate(rows):
            candidate_id = row.get("candidate_id")
            location = (
                f"verified_gap_questions.json[{index}]:{candidate_id}"
                if isinstance(candidate_id, str)
                else f"verified_gap_questions.json[{index}]"
            )
            answer = row.get("correct_answer")
            answer_valid = isinstance(answer, str) and bool(answer.strip())
            source = base_sources.get(str(row.get("source_code")))
            source_valid = (
                source is not None
                and row.get("source_file_id") == source.get("source_file_id")
                and row.get("source_pdf_sha256") == source.get("source_pdf_sha256")
            )
            evidence_row = evidence.get(str(candidate_id))
            page_lineage_valid = (
                self._int(row.get("question_start_page"), default=-1) > 0
                and self._int(row.get("solution_answer_page"), default=-1) > 0
            )
            evidence_valid = evidence_row is not None and all(
                (
                    evidence_row.get("source_code") == row.get("source_code"),
                    evidence_row.get("source_file_id") == row.get("source_file_id"),
                    evidence_row.get("source_pdf_sha256") == row.get("source_pdf_sha256"),
                    evidence_row.get("question_page") == row.get("question_start_page"),
                    evidence_row.get("solution_answer_page") == row.get("solution_answer_page"),
                    evidence_row.get("source_claimed_answer") == answer,
                )
            )
            expected_concepts = [
                {
                    "concept_code": "DEFINITE_INTEGRAL",
                    "weight": 1.0,
                    "is_primary": True,
                }
            ]
            expected_outcomes = [
                {
                    "learning_outcome_code": "LO_M12_DEFINITE_INTEGRAL",
                    "weight": 1.0,
                }
            ]
            structural_valid = all(
                (
                    row.get("base_dataset") == "DATA-MATH12-023",
                    row.get("target_gap") == EXPECTED_RESOLVED_GAP,
                    row.get("problem_type_code") == EXPECTED_RESOLVED_GAP,
                    row.get("subject_code") == "MATH_G12",
                    row.get("chapter_code") == "INTEGRALS",
                    row.get("topic_code") == "INTEGRAL_TOPIC",
                    row.get("official_scope_code") == "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL",
                    row.get("question_type") == "MULTIPLE_CHOICE",
                    row.get("review_status") == "VERIFIED_SOURCE_ANSWER",
                    row.get("answer_verification") == "SOURCE_SOLUTION_EXPLICIT",
                    self._raw_text_hash_valid(row),
                    answer_valid,
                    source_valid,
                    evidence_valid,
                    page_lineage_valid,
                    row.get("concepts") == expected_concepts,
                    row.get("learning_outcomes") == expected_outcomes,
                    row.get("rights_status") == "REVIEW_REQUIRED",
                    row.get("promotion_ready") is False,
                    row.get("database_import_allowed") is False,
                    row.get("canonical_snapshot_allowed") is False,
                    row.get("visual_asset_required") is False,
                )
            )
            if not structural_valid:
                issues.append(
                    self._issue(
                        "verified_gap_questions",
                        "INVALID_GAP_QUESTION_RECORD",
                        location,
                        "Verified gap question fields, answer, source lineage, or release boundary changed.",
                    )
                )
        return issues

    def _validate_evidence(
        self,
        rows: list[dict[str, Any]],
        questions: list[dict[str, Any]],
        base_sources: dict[str, dict[str, Any]],
    ) -> list[IntegralsGapSupplementIssue]:
        issues: list[IntegralsGapSupplementIssue] = []
        if len(rows) != 2:
            issues.append(
                self._issue(
                    "source_evidence",
                    "EVIDENCE_COUNT_MISMATCH",
                    "source_evidence.json",
                    f"Expected 2 evidence records, got {len(rows)}.",
                )
            )
        question_by_id = {
            row.get("candidate_id"): row
            for row in questions
            if isinstance(row.get("candidate_id"), str)
        }
        for index, row in enumerate(rows):
            candidate_id = row.get("candidate_id")
            candidate = question_by_id.get(str(candidate_id))
            source = base_sources.get(str(row.get("source_code")))
            valid = (
                candidate is not None
                and source is not None
                and row.get("evidence_type") == "SOURCE_QUESTION_AND_EXPLICIT_SOLUTION_ANSWER"
                and row.get("review_consistency") == "CONFIRMED"
                and row.get("source_claimed_answer") == candidate.get("correct_answer")
                and row.get("source_file_id") == source.get("source_file_id")
                and row.get("source_pdf_sha256") == source.get("source_pdf_sha256")
                and row.get("question_page") == candidate.get("question_start_page")
                and row.get("solution_answer_page") == candidate.get("solution_answer_page")
            )
            if not valid:
                issues.append(
                    self._issue(
                        "source_evidence",
                        "INVALID_SOURCE_EVIDENCE",
                        f"source_evidence.json[{index}]",
                        "Source evidence must resolve to gap question and base source registry.",
                    )
                )
        return issues

    def _validate_resolution(
        self,
        resolution: dict[str, Any],
        gap_questions: list[dict[str, Any]],
    ) -> list[IntegralsGapSupplementIssue]:
        issues: list[IntegralsGapSupplementIssue] = []
        valid = all(
            (
                resolution.get("dataset_code") == "DATA-MATH12-026",
                resolution.get("base_dataset") == "DATA-MATH12-023",
                resolution.get("resolved_gap") == EXPECTED_RESOLVED_GAP,
                resolution.get("verified_gap_candidates") == len(gap_questions),
                resolution.get("resolution_status") == "SOURCE_BACKED_EVIDENCE_FOUND",
                resolution.get("remaining_data_math12_023_gap_after_overlay") == [],
                resolution.get("rights_status") == "REVIEW_REQUIRED",
                resolution.get("database_import_allowed") is False,
                resolution.get("canonical_snapshot_allowed") is False,
            )
        )
        if not valid:
            issues.append(
                self._issue(
                    "gap_resolution",
                    "INVALID_GAP_RESOLUTION",
                    "gap_resolution.json",
                    "Gap resolution record does not match locked DATA-MATH12-026 contract.",
                )
            )
        return issues

    def _validate_remaining_scan(
        self,
        scan: dict[str, Any],
    ) -> list[IntegralsGapSupplementIssue]:
        issues: list[IntegralsGapSupplementIssue] = []
        valid = all(
            (
                scan.get("grouped_data_dispersion_original_gaps")
                == list(EXPECTED_GROUPED_DISPERSION_GAPS),
                scan.get("new_source_backed_verified_candidates_found") == 0,
                scan.get("decision") == "KEEP_EXISTING_GAPS_NO_SYNTHETIC_FILL",
            )
        )
        if not valid:
            issues.append(
                self._issue(
                    "remaining_gap_scan",
                    "INVALID_REMAINING_GAP_SCAN",
                    "remaining_gap_scan.json",
                    "Remaining gap scan for grouped dispersion must retain 5 gaps with 0 candidates.",
                )
            )
        return issues

    def _validate_release_boundary(
        self,
        questions: list[dict[str, Any]],
        resolution: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[IntegralsGapSupplementIssue]:
        issues: list[IntegralsGapSupplementIssue] = []
        if any(row.get("rights_status") != "REVIEW_REQUIRED" for row in questions):
            issues.append(
                self._issue(
                    "release_boundary",
                    "RIGHTS_BOUNDARY_VIOLATION",
                    "verified_gap_questions.json",
                    "All candidate records must have rights_status=REVIEW_REQUIRED.",
                )
            )
        if any(
            row.get("promotion_ready") is not False
            or row.get("database_import_allowed") is not False
            or row.get("canonical_snapshot_allowed") is not False
            for row in questions
        ):
            issues.append(
                self._issue(
                    "release_boundary",
                    "RELEASE_BOUNDARY_VIOLATION",
                    "verified_gap_questions.json",
                    "No candidate may have promotion, DB import, or snapshot enabled.",
                )
            )
        if (
            resolution.get("database_import_allowed") is not False
            or resolution.get("canonical_snapshot_allowed") is not False
            or resolution.get("rights_status") != "REVIEW_REQUIRED"
        ):
            issues.append(
                self._issue(
                    "release_boundary",
                    "RELEASE_STATS_BOUNDARY_VIOLATION",
                    "gap_resolution.json",
                    "Resolution record must keep import and snapshot disabled.",
                )
            )
        policy = contract.get("policy", {})
        if (
            policy.get("overlay_only_do_not_rewrite_base_data") is not True
            or policy.get("no_synthetic_gap_fill") is not True
            or policy.get("rights_review_required") is not True
        ):
            issues.append(
                self._issue(
                    "release_boundary",
                    "CONTRACT_POLICY_VIOLATION",
                    "data_contract.json:policy",
                    "Data contract policies must remain intact.",
                )
            )
        return issues

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[IntegralsGapSupplementIssue]:
        pdfs = sorted(str(p.relative_to(path)) for p in path.rglob("*.pdf"))
        if not pdfs:
            return []
        return [
            self._issue(
                "no_pdf_binaries",
                "SOURCE_PDF_BINARY_PRESENT",
                pdfs[0],
                "Source PDF binaries are forbidden in DATA-MATH12-026.",
            )
        ]

    @staticmethod
    def semantic_sha256(value: Any) -> str:
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @classmethod
    def _semantic_file_sha256(cls, path: Path) -> str | None:
        try:
            return cls.semantic_sha256(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _raw_text_hash_valid(row: dict[str, Any]) -> bool:
        text = row.get("raw_question_text")
        expected = row.get("raw_question_text_sha256")
        return (
            isinstance(text, str)
            and isinstance(expected, str)
            and hashlib.sha256(text.encode("utf-8")).hexdigest() == expected
        )

    @staticmethod
    def _check_required_files(
        path: Path, issues: list[IntegralsGapSupplementIssue]
    ) -> None:
        for name in REQUIRED_FILES:
            if not (path / name).is_file():
                issues.append(
                    IntegralsGapSupplementIssue(
                        check="required_files",
                        code="MISSING_REQUIRED_FILE",
                        location=name,
                        message=f"Required file {name} is missing from DATA-MATH12-026.",
                    )
                )

    @classmethod
    def _load_list(
        cls, path: Path, issues: list[IntegralsGapSupplementIssue]
    ) -> list[dict[str, Any]]:
        data = cls._load_json(path, issues)
        if isinstance(data, list) and all(isinstance(row, dict) for row in data):
            return data
        issues.append(
            cls._issue(
                "required_files",
                "INVALID_JSON_STRUCTURE",
                path.name,
                "Expected a JSON list of objects.",
            )
        )
        return []

    @classmethod
    def _load_object(
        cls, path: Path, issues: list[IntegralsGapSupplementIssue]
    ) -> dict[str, Any]:
        data = cls._load_json(path, issues)
        if isinstance(data, dict):
            return data
        issues.append(
            cls._issue(
                "required_files",
                "INVALID_JSON_STRUCTURE",
                path.name,
                "Expected a JSON object.",
            )
        )
        return {}

    @classmethod
    def _load_json(
        cls, path: Path, issues: list[IntegralsGapSupplementIssue]
    ) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            issues.append(
                cls._issue(
                    "required_files",
                    "MALFORMED_JSON_FILE",
                    path.name,
                    f"Failed to read/decode JSON: {error}",
                )
            )
            return None

    @staticmethod
    def _int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _issue(
        check: str, code: str, location: str, message: str
    ) -> IntegralsGapSupplementIssue:
        return IntegralsGapSupplementIssue(
            check=check, code=code, location=location, message=message
        )
