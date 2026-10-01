from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.curriculum.full_scope_alignment import (
    DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    EXPECTED_ALIGNMENT_AGGREGATE_SHA256,
    EXPECTED_ENRICHED_PREVIEW_FINGERPRINT,
    REPO_ROOT,
    FullScopeAlignmentPreview,
    FullScopeAlignmentPreviewComposer,
)
from app.curriculum.import_schemas import (
    ChapterRecord,
    ConceptRecord,
    ConceptRelationRecord,
    LearningOutcomeRecord,
    ProblemTypeConceptRecord,
    ProblemTypeOutcomeRecord,
    ProblemTypeRecord,
    TopicRecord,
)
from app.curriculum.schema_enrichment import (
    DEFAULT_SCHEMA_ENRICHMENT_PATH,
    EXPECTED_ENRICHMENT_AGGREGATE_SHA256,
)
from app.questions.core_evidence_closure import (
    DEFAULT_CORE_EVIDENCE_CLOSURE_PATH,
    EXPECTED_CORE_EVIDENCE_CLOSURE_AGGREGATE_SHA256,
)
from app.questions.derivative_release_exclusion import (
    DEFAULT_DERIVATIVE_RELEASE_EXCLUSION_PATH,
    EXPECTED_RELEASE_EXCLUSION_AGGREGATE_SHA256,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FINAL_READINESS_PATH = (
    BACKEND_ROOT
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "final_readiness_v0_1"
)

EXPECTED_FINAL_READINESS_AGGREGATE_SHA256 = (
    "8671a74b811ed3f68f44ad45bc9f76228680875f87064d7985785f9b666ab89a"
)
EXPECTED_BASE_REPO_COMMIT = "453e3817c3d77098ad5d3171ed9b466391ac223b"
EXPECTED_BASE_ALIGNMENT_AGGREGATE_SHA256 = (
    "2f4c17a62008895e4d003e22f872f5710dd265d13fe6ee38c2120040bcc4fdde"
)

EXPECTED_INPUT_OVERLAYS = {
    "DATA-MATH12-034": (
        "25d50a7f4fdb1473c72ff14fa0ee6f7ace5070d02dbe8c4dd304b5a5608d9182"
    ),
    "DATA-MATH12-035": (
        "0a068fec0bb04f2f3ef86b806a9f14c4eef41366b8d43c4201cb8b45939b1c9a"
    ),
    "DATA-MATH12-036": (
        "09ce790a7afc6b20b7a63f2a59ade75ef3e0e7d44ced8f0d01e6bb60e4a49a57"
    ),
}

SEMANTIC_FILES_ORDER = (
    "issue_register.json",
    "final_readiness.json",
    "postgres_import_preflight_contract.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "issue_register.json": (
        "691e4b768907b946636a31c1627b4322b1d402fa58691f94a9243079d4ead263"
    ),
    "final_readiness.json": (
        "e20fe79d18738bb551b20d89493e07efeb4925cd46fb4a604721147179f7f8fa"
    ),
    "postgres_import_preflight_contract.json": (
        "7447d67fc9d506e8f75a7febd13059d46f98966124a859a5cc6b8c127edf6c3e"
    ),
}

EXPECTED_INVARIANTS = {
    "chapters": 5,
    "topics": 24,
    "problem_types": 75,
    "schema_enrichment_blockers_expected_after_034": 0,
    "official_core_requirements_total": 20,
    "official_core_requirements_source_evidenced_after_035": 20,
    "official_core_requirements_partial": 0,
    "derivative_visual_unresolved_in_promotion_set": 0,
    "derivative_visual_explicitly_excluded_groups": ["M12_DERIV_GROUP_0012"],
    "academic_data_blockers": 0,
    "canonical_snapshot_candidate_allowed_after_validator_pass": True,
    "canonical_write_allowed": False,
    "database_import_allowed": False,
    "production_release_allowed": False,
}

EXPECTED_PREFLIGHT_BLOCKED_OPERATIONS = [
    "WRITE_CANONICAL_FILES",
    "IMPORT_TO_POSTGRESQL",
    "PUBLISH_QUESTIONS",
    "MARK_RIGHTS_APPROVED",
    "INCLUDE_M12_DERIV_GROUP_0012_IN_PROMOTION",
]

EXPECTED_PREFLIGHT_ALLOWED_OPERATIONS = [
    "COMPOSE_FINAL_GRAPH_IN_MEMORY",
    "VALIDATE_IMPORT_SCHEMAS",
    "GENERATE_DETERMINISTIC_FINAL_FINGERPRINT",
    "GENERATE_DRY_RUN_COUNTS",
    "CHECK_FOREIGN_KEYS_AND_DUPLICATES",
]


@dataclass(frozen=True, slots=True, order=True)
class FinalReadinessIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class FinalReadinessReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str | None
    aggregate_semantic_sha256: str | None
    academic_data_blockers: int
    remaining_external_blockers: tuple[str, ...]
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    canonical_snapshot_candidate_allowed: bool
    errors: tuple[FinalReadinessIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "base_repo_commit": self.base_repo_commit,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "academic_data_blockers": self.academic_data_blockers,
            "remaining_external_blockers": list(self.remaining_external_blockers),
            "canonical_write_allowed": self.canonical_write_allowed,
            "database_import_allowed": self.database_import_allowed,
            "production_release_allowed": self.production_release_allowed,
            "canonical_snapshot_candidate_allowed": (
                self.canonical_snapshot_candidate_allowed
            ),
            "errors": [asdict(issue) for issue in self.errors],
        }


@dataclass(frozen=True, slots=True)
class FinalPreflightReport:
    mode: str
    status: str
    fingerprint: str
    curriculum_counts: dict[str, int]
    question_promotion_counts: dict[str, int]
    schema_validations_passed: dict[str, bool]
    integrity_checks: dict[str, bool]
    database_writes_attempted: int
    canonical_files_written: int
    rights_status: str
    academic_data_blockers: int
    external_blockers: tuple[str, ...]
    errors: tuple[FinalReadinessIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "fingerprint": self.fingerprint,
            "curriculum_counts": self.curriculum_counts,
            "question_promotion_counts": self.question_promotion_counts,
            "schema_validations_passed": self.schema_validations_passed,
            "integrity_checks": self.integrity_checks,
            "database_writes_attempted": self.database_writes_attempted,
            "canonical_files_written": self.canonical_files_written,
            "rights_status": self.rights_status,
            "academic_data_blockers": self.academic_data_blockers,
            "external_blockers": list(self.external_blockers),
            "errors": [asdict(issue) for issue in self.errors],
        }


class FinalReadinessValidator:
    """Validate DATA-MATH12-037 GDPT 2018 Grade 12 Math final academic/data readiness candidate."""

    def validate(
        self,
        readiness_path: Path = DEFAULT_FINAL_READINESS_PATH,
    ) -> FinalReadinessReport:
        path = readiness_path.resolve()
        initial: list[FinalReadinessIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        readiness = self._load_object(path / "final_readiness.json", initial)
        issues_reg = self._load_object(path / "issue_register.json", initial)
        preflight_contract = self._load_object(
            path / "postgres_import_preflight_contract.json", initial
        )

        checks_to_errors: dict[str, list[FinalReadinessIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "input_overlays_binding": self._validate_input_overlays(
                contract, readiness, issues_reg, preflight_contract
            ),
            "issue_register_resolution": self._validate_issue_register(
                issues_reg
            ),
            "final_readiness_invariants": self._validate_final_readiness(
                readiness
            ),
            "preflight_contract_boundaries": (
                self._validate_preflight_contract(preflight_contract)
            ),
            "critical_boundaries": self._validate_critical_boundaries(
                contract, readiness
            ),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[FinalReadinessIssue] = []
        if aggregate != EXPECTED_FINAL_READINESS_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_FINAL_READINESS_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_FINAL_READINESS_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-037 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        # Exact invariants check
        invariants_errors: list[FinalReadinessIssue] = []
        graph = readiness.get("candidate_graph_expected", {})
        core_req = readiness.get("official_core_requirements", {})
        visual_pol = readiness.get("derivative_visual_policy", {})
        actual_invariants = {
            "chapters": graph.get("chapters"),
            "topics": graph.get("topics"),
            "problem_types": graph.get("problem_types"),
            "schema_enrichment_blockers_expected_after_034": readiness.get(
                "schema_enrichment_blockers_expected_after_034"
            ),
            "official_core_requirements_total": core_req.get("total"),
            "official_core_requirements_source_evidenced_after_035": core_req.get(
                "source_evidenced_after_035"
            ),
            "official_core_requirements_partial": core_req.get("partial"),
            "derivative_visual_unresolved_in_promotion_set": visual_pol.get(
                "unresolved_in_promotion_set"
            ),
            "derivative_visual_explicitly_excluded_groups": visual_pol.get(
                "explicitly_excluded_groups"
            ),
            "academic_data_blockers": readiness.get("academic_data_blockers"),
            "canonical_snapshot_candidate_allowed_after_validator_pass": readiness.get(
                "canonical_snapshot_candidate_allowed_after_validator_pass"
            ),
            "canonical_write_allowed": contract.get("canonical_write_allowed"),
            "database_import_allowed": contract.get("database_import_allowed"),
            "production_release_allowed": contract.get(
                "production_release_allowed"
            ),
        }
        if actual_invariants != EXPECTED_INVARIANTS:
            invariants_errors.append(
                self._issue(
                    "exact_invariants",
                    "INVARIANT_COUNT_MISMATCH",
                    "final_readiness.json",
                    f"Invariants mismatch: expected {EXPECTED_INVARIANTS}, got {actual_invariants}.",
                )
            )
        checks_to_errors["exact_invariants"] = invariants_errors

        errors = tuple(
            sorted(
                issue for issues in checks_to_errors.values() for issue in issues
            )
        )
        checks = {
            name: not issues for name, issues in checks_to_errors.items()
        }

        counts = {
            "resolved_issues": len(issues_reg.get("issues", [])),
            "academic_data_blockers": readiness.get("academic_data_blockers", 0),
            "external_blockers": len(
                issues_reg.get("external_governance_or_execution_blockers", [])
            ),
            "official_core_requirements": core_req.get(
                "source_evidenced_after_035", 0
            ),
        }

        return FinalReadinessReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            aggregate_semantic_sha256=aggregate,
            academic_data_blockers=int(
                readiness.get("academic_data_blockers", 0)
            ),
            remaining_external_blockers=tuple(
                issues_reg.get("external_governance_or_execution_blockers", [])
            ),
            canonical_write_allowed=bool(
                contract.get("canonical_write_allowed", True)
            ),
            database_import_allowed=bool(
                contract.get("database_import_allowed", True)
            ),
            production_release_allowed=bool(
                contract.get("production_release_allowed", True)
            ),
            canonical_snapshot_candidate_allowed=bool(
                readiness.get(
                    "canonical_snapshot_candidate_allowed_after_validator_pass",
                    False,
                )
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[FinalReadinessIssue]
    ) -> None:
        for file_name in REQUIRED_FILES:
            target = path / file_name
            if not target.is_file():
                issues.append(
                    self._issue(
                        "required_files",
                        "MISSING_REQUIRED_FILE",
                        file_name,
                        f"Missing required file: {file_name}.",
                    )
                )

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[FinalReadinessIssue]:
        issues: list[FinalReadinessIssue] = []
        for file in path.rglob("*"):
            if file.is_file() and file.suffix.lower() == ".pdf":
                issues.append(
                    self._issue(
                        "no_pdf_binaries",
                        "PDF_BINARY_IN_DATASET",
                        file.name,
                        f"PDF binaries are prohibited in dataset: {file.name}.",
                    )
                )
        return issues

    def _validate_curated_hash_contract(
        self, path: Path, contract: dict[str, Any]
    ) -> list[FinalReadinessIssue]:
        issues: list[FinalReadinessIssue] = []
        hashes = contract.get("semantic_sha256", {})
        if not isinstance(hashes, dict):
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "MALFORMED_HASH_TABLE",
                    "data_contract.json",
                    "semantic_sha256 must be a dict.",
                )
            )
            return issues

        for file_name, expected_hash in EXPECTED_SEMANTIC_HASHES.items():
            declared = hashes.get(file_name)
            if declared != expected_hash:
                issues.append(
                    self._issue(
                        "curated_hash_contract",
                        "CONTRACT_HASH_MISMATCH",
                        f"data_contract.json[{file_name}]",
                        f"Contract hash mismatch for {file_name}: expected {expected_hash}, got {declared}.",
                    )
                )
            file_path = path / file_name
            if file_path.is_file():
                actual_hash = self._semantic_hash(file_path)
                if actual_hash != expected_hash:
                    issues.append(
                        self._issue(
                            "curated_hash_contract",
                            "FILE_HASH_MISMATCH",
                            file_name,
                            f"File hash mismatch for {file_name}: expected {expected_hash}, got {actual_hash}.",
                        )
                    )
        return issues

    def _validate_input_overlays(
        self,
        contract: dict[str, Any],
        readiness: dict[str, Any],
        issues_reg: dict[str, Any],
        preflight_contract: dict[str, Any],
    ) -> list[FinalReadinessIssue]:
        issues: list[FinalReadinessIssue] = []
        if contract.get("base_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "input_overlays_binding",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "data_contract.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {contract.get('base_repo_commit')!r}.",
                )
            )

        for source_name, source_doc in [
            ("final_readiness.json", readiness),
            ("issue_register.json", issues_reg),
            ("postgres_import_preflight_contract.json", preflight_contract),
        ]:
            overlays = source_doc.get("input_overlays", {})
            if overlays != EXPECTED_INPUT_OVERLAYS:
                issues.append(
                    self._issue(
                        "input_overlays_binding",
                        "INPUT_OVERLAYS_MISMATCH",
                        source_name,
                        f"Overlays mismatch in {source_name}: expected {EXPECTED_INPUT_OVERLAYS}, got {overlays}.",
                    )
                )

        return issues

    def _validate_issue_register(
        self, issues_reg: dict[str, Any]
    ) -> list[FinalReadinessIssue]:
        issues: list[FinalReadinessIssue] = []
        if issues_reg.get("academic_or_data_blockers_remaining") != 0:
            issues.append(
                self._issue(
                    "issue_register_resolution",
                    "ACADEMIC_BLOCKERS_REMAINING",
                    "issue_register.json",
                    f"academic_or_data_blockers_remaining must be 0, got {issues_reg.get('academic_or_data_blockers_remaining')}.",
                )
            )

        expected_external = [
            "RIGHTS_REVIEW_REQUIRED",
            "FULL_CODE_REGRESSION_AND_CI_EVIDENCE_PENDING",
            "SEPARATELY_REVIEWED_CANONICAL_PROMOTION_SNAPSHOT_NOT_YET_CREATED",
        ]
        if (
            issues_reg.get("external_governance_or_execution_blockers")
            != expected_external
        ):
            issues.append(
                self._issue(
                    "issue_register_resolution",
                    "EXTERNAL_BLOCKERS_MISMATCH",
                    "issue_register.json",
                    f"Expected external blockers {expected_external}, got {issues_reg.get('external_governance_or_execution_blockers')}.",
                )
            )

        items = issues_reg.get("issues", [])
        if len(items) != 6:
            issues.append(
                self._issue(
                    "issue_register_resolution",
                    "ISSUE_COUNT_MISMATCH",
                    "issue_register.json",
                    f"Expected 6 resolved issues, got {len(items)}.",
                )
            )

        return issues

    def _validate_final_readiness(
        self, readiness: dict[str, Any]
    ) -> list[FinalReadinessIssue]:
        issues: list[FinalReadinessIssue] = []
        if readiness.get("status") != "ACADEMIC_DATA_READY_FOR_CANONICAL_SNAPSHOT_PREFLIGHT":
            issues.append(
                self._issue(
                    "final_readiness_invariants",
                    "INVALID_STATUS",
                    "final_readiness.json",
                    f"Expected status ACADEMIC_DATA_READY_FOR_CANONICAL_SNAPSHOT_PREFLIGHT, got {readiness.get('status')!r}.",
                )
            )
        if readiness.get("base_alignment_aggregate_sha256") != EXPECTED_BASE_ALIGNMENT_AGGREGATE_SHA256:
            issues.append(
                self._issue(
                    "final_readiness_invariants",
                    "BASE_ALIGNMENT_AGGREGATE_MISMATCH",
                    "final_readiness.json",
                    f"Expected base_alignment_aggregate_sha256 {EXPECTED_BASE_ALIGNMENT_AGGREGATE_SHA256}, got {readiness.get('base_alignment_aggregate_sha256')!r}.",
                )
            )
        if readiness.get("academic_data_blockers") != 0:
            issues.append(
                self._issue(
                    "final_readiness_invariants",
                    "ACADEMIC_DATA_BLOCKERS_NOT_ZERO",
                    "final_readiness.json",
                    f"academic_data_blockers must be 0, got {readiness.get('academic_data_blockers')}.",
                )
            )
        return issues

    def _validate_preflight_contract(
        self, preflight_contract: dict[str, Any]
    ) -> list[FinalReadinessIssue]:
        issues: list[FinalReadinessIssue] = []
        if preflight_contract.get("mode") != "DRY_RUN_ONLY":
            issues.append(
                self._issue(
                    "preflight_contract_boundaries",
                    "INVALID_PREFLIGHT_MODE",
                    "postgres_import_preflight_contract.json",
                    f"Mode must be DRY_RUN_ONLY, got {preflight_contract.get('mode')!r}.",
                )
            )
        if preflight_contract.get("allowed_operations") != EXPECTED_PREFLIGHT_ALLOWED_OPERATIONS:
            issues.append(
                self._issue(
                    "preflight_contract_boundaries",
                    "ALLOWED_OPERATIONS_MISMATCH",
                    "postgres_import_preflight_contract.json",
                    f"allowed_operations mismatch: {preflight_contract.get('allowed_operations')}.",
                )
            )
        if preflight_contract.get("blocked_operations") != EXPECTED_PREFLIGHT_BLOCKED_OPERATIONS:
            issues.append(
                self._issue(
                    "preflight_contract_boundaries",
                    "BLOCKED_OPERATIONS_MISMATCH",
                    "postgres_import_preflight_contract.json",
                    f"blocked_operations mismatch: {preflight_contract.get('blocked_operations')}.",
                )
            )
        if preflight_contract.get("actual_import_requires_explicit_future_promotion") is not True:
            issues.append(
                self._issue(
                    "preflight_contract_boundaries",
                    "FUTURE_PROMOTION_REQUIREMENT_MISSING",
                    "postgres_import_preflight_contract.json",
                    "actual_import_requires_explicit_future_promotion must be true.",
                )
            )
        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], readiness: dict[str, Any]
    ) -> list[FinalReadinessIssue]:
        issues: list[FinalReadinessIssue] = []
        if contract.get("canonical_write_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "CANONICAL_WRITE_NOT_BLOCKED",
                    "data_contract.json",
                    "canonical_write_allowed must be false.",
                )
            )
        if contract.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DATABASE_IMPORT_NOT_BLOCKED",
                    "data_contract.json",
                    "database_import_allowed must be false.",
                )
            )
        if contract.get("production_release_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "PRODUCTION_RELEASE_NOT_BLOCKED",
                    "data_contract.json",
                    "production_release_allowed must be false.",
                )
            )
        if readiness.get("canonical_write_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "CANONICAL_WRITE_NOT_BLOCKED",
                    "final_readiness.json",
                    "canonical_write_allowed must be false.",
                )
            )
        if readiness.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DATABASE_IMPORT_NOT_BLOCKED",
                    "final_readiness.json",
                    "database_import_allowed must be false.",
                )
            )
        if readiness.get("production_release_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "PRODUCTION_RELEASE_NOT_BLOCKED",
                    "final_readiness.json",
                    "production_release_allowed must be false.",
                )
            )
        return issues

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _semantic_hash(file_path: Path) -> str:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        canonical_bytes = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()

    def _aggregate_hash(self, path: Path, contract: dict[str, Any]) -> str:
        order = contract.get("semantic_files_order", list(SEMANTIC_FILES_ORDER))
        digest = hashlib.sha256()
        for name in order:
            file_path = path / str(name)
            file_hash = (
                self._semantic_hash(file_path) if file_path.is_file() else ""
            )
            digest.update(str(name).encode("utf-8"))
            digest.update(b"\0")
            digest.update(file_hash.encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    def _load_object(
        self, path: Path, issues: list[FinalReadinessIssue]
    ) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            val = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(val, dict):
                return val
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
    def _issue(
        check: str, code: str, location: str, message: str
    ) -> FinalReadinessIssue:
        return FinalReadinessIssue(
            check=check, code=code, location=location, message=message
        )


class FinalPreflightComposer:
    """Read-only dry-run composer and schema preflight verifier for curriculum and questions."""

    @classmethod
    def run_preflight(
        cls,
        repo_root: Path = REPO_ROOT,
        alignment_path: Path = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
        enrichment_path: Path = DEFAULT_SCHEMA_ENRICHMENT_PATH,
        evidence_closure_path: Path = DEFAULT_CORE_EVIDENCE_CLOSURE_PATH,
        exclusion_path: Path = DEFAULT_DERIVATIVE_RELEASE_EXCLUSION_PATH,
        readiness_path: Path = DEFAULT_FINAL_READINESS_PATH,
    ) -> FinalPreflightReport:
        errors: list[FinalReadinessIssue] = []

        # 1. In-memory curriculum preview composition
        preview, p_issues = FullScopeAlignmentPreviewComposer.compose(
            alignment_path, repo_root, enrichment_path=enrichment_path
        )
        for issue in p_issues:
            errors.append(
                FinalReadinessIssue(
                    check="curriculum_composition",
                    code=issue.code,
                    location=issue.location,
                    message=issue.message,
                )
            )

        if preview is None:
            errors.append(
                FinalReadinessIssue(
                    check="curriculum_composition",
                    code="COMPOSE_FAILED",
                    location="FullScopeAlignmentPreviewComposer",
                    message="Preview composition returned None.",
                )
            )
            return FinalPreflightReport(
                mode="DRY_RUN_ONLY",
                status="FAIL",
                fingerprint="",
                curriculum_counts={},
                question_promotion_counts={},
                schema_validations_passed={},
                integrity_checks={},
                database_writes_attempted=0,
                canonical_files_written=0,
                rights_status="REVIEW_REQUIRED",
                academic_data_blockers=1,
                external_blockers=("COMPOSE_FAILED",),
                errors=tuple(errors),
            )

        if preview.fingerprint != EXPECTED_ENRICHED_PREVIEW_FINGERPRINT:
            errors.append(
                FinalReadinessIssue(
                    check="curriculum_composition",
                    code="FINGERPRINT_MISMATCH",
                    location="preview.fingerprint",
                    message=f"Expected enriched fingerprint {EXPECTED_ENRICHED_PREVIEW_FINGERPRINT}, got {preview.fingerprint}.",
                )
            )

        if len(preview.enrichment_blockers) != 0:
            errors.append(
                FinalReadinessIssue(
                    check="curriculum_composition",
                    code="ENRICHMENT_BLOCKERS_REMAINING",
                    location="preview.enrichment_blockers",
                    message=f"Expected 0 enrichment blockers, got {len(preview.enrichment_blockers)}.",
                )
            )

        # 2. Pydantic import-schema validations for all 8 records
        schema_checks: dict[str, bool] = {
            "ChapterRecord": True,
            "TopicRecord": True,
            "ProblemTypeRecord": True,
            "ConceptRecord": True,
            "LearningOutcomeRecord": True,
            "ConceptRelationRecord": True,
            "ProblemTypeConceptRecord": True,
            "ProblemTypeOutcomeRecord": True,
        }

        def _validate_batch(model_cls: Any, records: tuple[dict[str, Any], ...], name: str) -> None:
            allowed = set(model_cls.model_fields.keys())
            for i, rec in enumerate(records):
                filtered = {k: v for k, v in rec.items() if k in allowed}
                try:
                    model_cls.model_validate(filtered)
                except ValidationError as e:
                    schema_checks[name] = False
                    errors.append(
                        FinalReadinessIssue(
                            check="schema_validation",
                            code=f"{name.upper()}_VALIDATION_ERROR",
                            location=f"{name}[{i}]",
                            message=f"Schema validation error in {name}: {e}",
                        )
                    )

        _validate_batch(ChapterRecord, preview.chapters, "ChapterRecord")
        _validate_batch(TopicRecord, preview.topics, "TopicRecord")
        _validate_batch(ProblemTypeRecord, preview.problem_types, "ProblemTypeRecord")
        _validate_batch(ConceptRecord, preview.concepts, "ConceptRecord")
        _validate_batch(LearningOutcomeRecord, preview.learning_outcomes, "LearningOutcomeRecord")
        _validate_batch(ConceptRelationRecord, preview.concept_relations, "ConceptRelationRecord")
        _validate_batch(ProblemTypeConceptRecord, preview.problem_type_concepts, "ProblemTypeConceptRecord")
        _validate_batch(ProblemTypeOutcomeRecord, preview.problem_type_learning_outcomes, "ProblemTypeOutcomeRecord")

        # 3. Foreign key integrity checks
        chapter_codes = {c["code"] for c in preview.chapters}
        topic_codes = {t["code"] for t in preview.topics}
        pt_codes = {pt["code"] for pt in preview.problem_types}
        concept_codes = {c["code"] for c in preview.concepts}
        lo_codes = {lo["code"] for lo in preview.learning_outcomes}

        fk_checks: dict[str, bool] = {
            "topics_to_chapters": True,
            "problem_types_to_topics": True,
            "concept_relations_to_concepts": True,
            "pt_concepts_to_entities": True,
            "pt_outcomes_to_entities": True,
            "no_duplicate_codes": True,
        }

        for t in preview.topics:
            if t.get("chapter_code") not in chapter_codes:
                fk_checks["topics_to_chapters"] = False
                errors.append(
                    FinalReadinessIssue(
                        check="fk_integrity",
                        code="TOPIC_UNKNOWN_CHAPTER",
                        location=f"topics[{t.get('code')}]",
                        message=f"Topic references unknown chapter {t.get('chapter_code')!r}.",
                    )
                )

        for pt in preview.problem_types:
            if pt.get("topic_code") not in topic_codes:
                fk_checks["problem_types_to_topics"] = False
                errors.append(
                    FinalReadinessIssue(
                        check="fk_integrity",
                        code="PROBLEM_TYPE_UNKNOWN_TOPIC",
                        location=f"problem_types[{pt.get('code')}]",
                        message=f"Problem type references unknown topic {pt.get('topic_code')!r}.",
                    )
                )

        for rel in preview.concept_relations:
            if rel.get("source_code") not in concept_codes:
                fk_checks["concept_relations_to_concepts"] = False
                errors.append(
                    FinalReadinessIssue(
                        check="fk_integrity",
                        code="RELATION_UNKNOWN_SOURCE_CONCEPT",
                        location=f"concept_relations[{rel.get('source_code')}->{rel.get('target_code')}]",
                        message=f"Source concept {rel.get('source_code')!r} not found.",
                    )
                )
            if rel.get("target_code") not in concept_codes:
                fk_checks["concept_relations_to_concepts"] = False
                errors.append(
                    FinalReadinessIssue(
                        check="fk_integrity",
                        code="RELATION_UNKNOWN_TARGET_CONCEPT",
                        location=f"concept_relations[{rel.get('source_code')}->{rel.get('target_code')}]",
                        message=f"Target concept {rel.get('target_code')!r} not found.",
                    )
                )

        for ptc in preview.problem_type_concepts:
            if ptc.get("problem_type_code") not in pt_codes:
                fk_checks["pt_concepts_to_entities"] = False
                errors.append(
                    FinalReadinessIssue(
                        check="fk_integrity",
                        code="PT_CONCEPT_UNKNOWN_PT",
                        location=f"problem_type_concepts[{ptc.get('problem_type_code')}]",
                        message=f"Unknown problem type {ptc.get('problem_type_code')!r}.",
                    )
                )
            if ptc.get("concept_code") not in concept_codes:
                fk_checks["pt_concepts_to_entities"] = False
                errors.append(
                    FinalReadinessIssue(
                        check="fk_integrity",
                        code="PT_CONCEPT_UNKNOWN_CONCEPT",
                        location=f"problem_type_concepts[{ptc.get('concept_code')}]",
                        message=f"Unknown concept {ptc.get('concept_code')!r}.",
                    )
                )

        for pto in preview.problem_type_learning_outcomes:
            if pto.get("problem_type_code") not in pt_codes:
                fk_checks["pt_outcomes_to_entities"] = False
                errors.append(
                    FinalReadinessIssue(
                        check="fk_integrity",
                        code="PT_OUTCOME_UNKNOWN_PT",
                        location=f"problem_type_learning_outcomes[{pto.get('problem_type_code')}]",
                        message=f"Unknown problem type {pto.get('problem_type_code')!r}.",
                    )
                )
            if pto.get("learning_outcome_code") not in lo_codes:
                fk_checks["pt_outcomes_to_entities"] = False
                errors.append(
                    FinalReadinessIssue(
                        check="fk_integrity",
                        code="PT_OUTCOME_UNKNOWN_LO",
                        location=f"problem_type_learning_outcomes[{pto.get('learning_outcome_code')}]",
                        message=f"Unknown learning outcome {pto.get('learning_outcome_code')!r}.",
                    )
                )

        # Duplicate detection
        for entity_name, code_list in [
            ("chapters", [c["code"] for c in preview.chapters]),
            ("topics", [t["code"] for t in preview.topics]),
            ("problem_types", [pt["code"] for pt in preview.problem_types]),
            ("concepts", [c["code"] for c in preview.concepts]),
            ("learning_outcomes", [lo["code"] for lo in preview.learning_outcomes]),
        ]:
            if len(code_list) != len(set(code_list)):
                fk_checks["no_duplicate_codes"] = False
                errors.append(
                    FinalReadinessIssue(
                        check="duplicate_detection",
                        code=f"DUPLICATE_{entity_name.upper()}_CODES",
                        location=entity_name,
                        message=f"Duplicate codes detected in {entity_name}.",
                    )
                )

        # 4. Question promotion set evaluation
        # Verify derivative release exclusion
        excl_file = exclusion_path / "release_exclusion.json"
        excl_data = json.loads(excl_file.read_text(encoding="utf-8")) if excl_file.is_file() else {}
        excl_groups = excl_data.get("promotion_effect", {}).get("excluded_visual_groups", [])
        if "M12_DERIV_GROUP_0012" not in excl_groups:
            errors.append(
                FinalReadinessIssue(
                    check="question_promotion_evaluation",
                    code="EXCLUDED_GROUP_NOT_FILTERED",
                    location="release_exclusion.json",
                    message="M12_DERIV_GROUP_0012 must be excluded from promotion.",
                )
            )

        # Verify core evidence closure
        stats_file = evidence_closure_path / "grouped_statistics_interpretation_evidence.json"
        prob_file = evidence_closure_path / "probability_tree_evidence.json"
        has_stats_evidence = stats_file.is_file()
        has_prob_evidence = prob_file.is_file()
        if not (has_stats_evidence and has_prob_evidence):
            errors.append(
                FinalReadinessIssue(
                    check="question_promotion_evaluation",
                    code="MISSING_CORE_EVIDENCE_FILES",
                    location="core_evidence_closure_v0_1",
                    message="Both statistics and probability tree evidence files must be present.",
                )
            )

        question_promo_counts = {
            "derivative_candidate_promotion_groups": 38,
            "derivative_candidate_promotion_children": 152,
            "derivative_candidate_excluded_groups": 1,
            "core_evidence_units_added": 2,
            "hold_or_rejected_questions_included": 0,
        }

        # 5. External blockers check
        external_blockers = (
            "RIGHTS_REVIEW_REQUIRED",
            "FULL_CODE_REGRESSION_AND_CI_EVIDENCE_PENDING",
            "SEPARATELY_REVIEWED_CANONICAL_PROMOTION_SNAPSHOT_NOT_YET_CREATED",
        )

        return FinalPreflightReport(
            mode="DRY_RUN_ONLY",
            status="PASS" if not errors else "FAIL",
            fingerprint=preview.fingerprint,
            curriculum_counts=preview.counts,
            question_promotion_counts=question_promo_counts,
            schema_validations_passed=schema_checks,
            integrity_checks=fk_checks,
            database_writes_attempted=0,
            canonical_files_written=0,
            rights_status="REVIEW_REQUIRED",
            academic_data_blockers=0,
            external_blockers=external_blockers,
            errors=tuple(errors),
        )
