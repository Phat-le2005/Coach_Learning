from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_PRODUCTION_GATE_PATH = (
    BACKEND_ROOT
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "production_gate_v0_1"
)
WORKFLOW_FILE_PATH = REPO_ROOT / ".github" / "workflows" / "backend-data-validation.yml"

EXPECTED_PRODUCTION_GATE_AGGREGATE_SHA256 = (
    "4222f9dd542c5d1e219725a62b14a59e6112d8a1332b3013449f9438fab550a2"
)
EXPECTED_BASE_REPO_COMMIT = "aed14bf213ac9db65e820984f5a6c46ebabbe304"

SEMANTIC_FILES_ORDER = (
    "ci_gate.json",
    "rights_review_queue.json",
    "production_gate.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "ci_gate.json": (
        "30fb29d8c6342f51e6469ed1658d1d5415950f8ae4ea05d137e1b61c88f5181b"
    ),
    "rights_review_queue.json": (
        "9a1941d0ec1ed8844f8365e8af222659132a7aa3d128c82231f8b17838d39a9d"
    ),
    "production_gate.json": (
        "6acde7d52d809c1e393aeab28645b2f249fb80b14c53416098280bfc77fe1d92"
    ),
}

EXPECTED_GATES = {
    "official_core_scope": "PASS",
    "schema_and_final_graph_preflight": "PASS",
    "canonical_snapshot_candidate_spec": "READY_AFTER_DATA038",
    "diagnostic_root_cause_layer": "READY_AS_STAGING_AFTER_DATA040",
    "academic_data_blockers": "PASS_ZERO",
    "diagnostic_problem_type_density": "FAIL",
    "source_diversity": "FAIL",
    "rights_review": "FAIL_PENDING_REVIEW",
    "ci_evidence": "FAIL_NO_WORKFLOW_RUNS",
    "canonical_activation": "BLOCKED",
    "postgres_import": "BLOCKED",
    "production_release": "BLOCKED",
}


@dataclass(frozen=True, slots=True, order=True)
class ProductionGateIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class ProductionGateReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    gates: dict[str, str]
    base_repo_commit: str | None
    aggregate_semantic_sha256: str | None
    workflow_exists: bool
    rights_status: str
    rights_auto_approval_allowed: bool
    production_ready: bool
    canonical_activation_blocked: bool
    postgres_import_blocked: bool
    production_release_blocked: bool
    errors: tuple[ProductionGateIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "gates": self.gates,
            "base_repo_commit": self.base_repo_commit,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "workflow_exists": self.workflow_exists,
            "rights_status": self.rights_status,
            "rights_auto_approval_allowed": self.rights_auto_approval_allowed,
            "production_ready": self.production_ready,
            "canonical_activation_blocked": self.canonical_activation_blocked,
            "postgres_import_blocked": self.postgres_import_blocked,
            "production_release_blocked": self.production_release_blocked,
            "errors": [asdict(issue) for issue in self.errors],
        }


class ProductionGateValidator:
    """Validator for DATA-MATH12-042 production, rights, and CI gates."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_PRODUCTION_GATE_PATH,
        *,
        workflow_path: Path = WORKFLOW_FILE_PATH,
    ) -> ProductionGateReport:
        path = dataset_path.resolve()
        initial: list[ProductionGateIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        ci_gate = self._load_object(path / "ci_gate.json", initial)
        rights_queue = self._load_object(path / "rights_review_queue.json", initial)
        prod_gate = self._load_object(path / "production_gate.json", initial)

        checks_to_errors: dict[str, list[ProductionGateIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract, ci_gate),
            "workflow_integration": self._validate_workflow(workflow_path, ci_gate),
            "rights_review_invariants": self._validate_rights_queue(rights_queue),
            "production_gate_invariants": self._validate_production_gate(prod_gate),
            "critical_boundaries": self._validate_critical_boundaries(contract, prod_gate),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[ProductionGateIssue] = []
        if aggregate != EXPECTED_PRODUCTION_GATE_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_PRODUCTION_GATE_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_PRODUCTION_GATE_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-042 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        errors = tuple(
            sorted(
                issue for issues in checks_to_errors.values() for issue in issues
            )
        )
        checks = {
            name: not issues for name, issues in checks_to_errors.items()
        }

        gates = prod_gate.get("gates", {})
        rights_status = rights_queue.get("status", "UNKNOWN")
        rights_auto = bool(rights_queue.get("rights_auto_approval_allowed", True))

        is_activation_blocked = gates.get("canonical_activation") == "BLOCKED"
        is_import_blocked = gates.get("postgres_import") == "BLOCKED"
        is_release_blocked = gates.get("production_release") == "BLOCKED"

        return ProductionGateReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            gates=gates,
            base_repo_commit=contract.get("base_repo_commit"),
            aggregate_semantic_sha256=aggregate,
            workflow_exists=workflow_path.is_file(),
            rights_status=rights_status,
            rights_auto_approval_allowed=rights_auto,
            production_ready=False,
            canonical_activation_blocked=is_activation_blocked,
            postgres_import_blocked=is_import_blocked,
            production_release_blocked=is_release_blocked,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[ProductionGateIssue]
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
    ) -> list[ProductionGateIssue]:
        issues: list[ProductionGateIssue] = []
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
    ) -> list[ProductionGateIssue]:
        issues: list[ProductionGateIssue] = []
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

    def _validate_base_repo_commit(
        self, contract: dict[str, Any], ci_gate: dict[str, Any]
    ) -> list[ProductionGateIssue]:
        issues: list[ProductionGateIssue] = []
        if contract.get("base_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_repo_commit",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "data_contract.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {contract.get('base_repo_commit')!r}.",
                )
            )
        if ci_gate.get("audited_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_repo_commit",
                    "AUDITED_REPO_COMMIT_MISMATCH",
                    "ci_gate.json",
                    f"Expected audited_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {ci_gate.get('audited_repo_commit')!r}.",
                )
            )
        return issues

    def _validate_workflow(
        self, workflow_path: Path, ci_gate: dict[str, Any]
    ) -> list[ProductionGateIssue]:
        issues: list[ProductionGateIssue] = []
        if not workflow_path.is_file():
            issues.append(
                self._issue(
                    "workflow_integration",
                    "WORKFLOW_FILE_MISSING",
                    str(workflow_path),
                    "GitHub Actions workflow file backend-data-validation.yml is missing.",
                )
            )
            return issues

        try:
            content = workflow_path.read_text(encoding="utf-8")
            if "python-version" not in content or "3.12" not in content:
                issues.append(
                    self._issue(
                        "workflow_integration",
                        "PYTHON_VERSION_MISMATCH",
                        workflow_path.name,
                        "Workflow must configure Python 3.12.",
                    )
                )
            if "pytest" not in content:
                issues.append(
                    self._issue(
                        "workflow_integration",
                        "PYTEST_COMMAND_MISSING",
                        workflow_path.name,
                        "Workflow must invoke pytest.",
                    )
                )
        except Exception as e:
            issues.append(
                self._issue(
                    "workflow_integration",
                    "WORKFLOW_READ_ERROR",
                    workflow_path.name,
                    f"Error reading workflow file: {e}",
                )
            )

        return issues

    def _validate_rights_queue(
        self, rights_queue: dict[str, Any]
    ) -> list[ProductionGateIssue]:
        issues: list[ProductionGateIssue] = []
        if rights_queue.get("status") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "rights_review_invariants",
                    "RIGHTS_STATUS_MISMATCH",
                    "rights_review_queue.json",
                    "rights_review_queue status must be REVIEW_REQUIRED.",
                )
            )
        if rights_queue.get("rights_auto_approval_allowed") is not False:
            issues.append(
                self._issue(
                    "rights_review_invariants",
                    "AUTO_APPROVAL_NOT_FALSE",
                    "rights_review_queue.json",
                    "rights_auto_approval_allowed must be false.",
                )
            )
        if rights_queue.get("legal_conclusion_made") is not False:
            issues.append(
                self._issue(
                    "rights_review_invariants",
                    "LEGAL_CONCLUSION_NOT_FALSE",
                    "rights_review_queue.json",
                    "legal_conclusion_made must be false.",
                )
            )
        families = rights_queue.get("source_families", [])
        if len(families) != 4:
            issues.append(
                self._issue(
                    "rights_review_invariants",
                    "SOURCE_FAMILIES_COUNT_MISMATCH",
                    "rights_review_queue.json",
                    f"Expected 4 source families in rights review queue, got {len(families)}.",
                )
            )
        return issues

    def _validate_production_gate(
        self, prod_gate: dict[str, Any]
    ) -> list[ProductionGateIssue]:
        issues: list[ProductionGateIssue] = []
        gates = prod_gate.get("gates", {})
        for gate_name, expected_val in EXPECTED_GATES.items():
            actual_val = gates.get(gate_name)
            if actual_val != expected_val:
                issues.append(
                    self._issue(
                        "production_gate_invariants",
                        f"{gate_name.upper()}_GATE_MISMATCH",
                        f"production_gate.json[gates.{gate_name}]",
                        f"Gate {gate_name} mismatch: expected {expected_val}, got {actual_val}.",
                    )
                )
        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], prod_gate: dict[str, Any]
    ) -> list[ProductionGateIssue]:
        issues: list[ProductionGateIssue] = []
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

        gates = prod_gate.get("gates", {})
        if gates.get("canonical_activation") != "BLOCKED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "CANONICAL_ACTIVATION_NOT_BLOCKED",
                    "production_gate.json",
                    "canonical_activation gate must be BLOCKED.",
                )
            )
        if gates.get("postgres_import") != "BLOCKED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "POSTGRES_IMPORT_NOT_BLOCKED",
                    "production_gate.json",
                    "postgres_import gate must be BLOCKED.",
                )
            )
        if gates.get("production_release") != "BLOCKED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "PRODUCTION_RELEASE_GATE_NOT_BLOCKED",
                    "production_gate.json",
                    "production_release gate must be BLOCKED.",
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
        self, path: Path, issues: list[ProductionGateIssue]
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
    ) -> ProductionGateIssue:
        return ProductionGateIssue(
            check=check, code=code, location=location, message=message
        )
