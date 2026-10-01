from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEPTH_QUEUE_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "depth_queue_v0_2"
)

EXPECTED_DEPTH_QUEUE_AGGREGATE_SHA256 = (
    "f266ebb7fb2524dc108a37bfbeade13cfdab8886d0ee907c75531637f4111d7b"
)
EXPECTED_BASE_REPO_COMMIT = "30bb2625128fa38a71fbbc8481e8589672027632"
EXPECTED_BASE_QUALITY_AGGREGATE_SHA256 = (
    "3953cb4035ecd4080d2928b46c1108cff4290356d4017dd1c44f088865e17a71"
)

SEMANTIC_FILES_ORDER = (
    "remaining_ingestion_queue.json",
    "depth_targets.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "remaining_ingestion_queue.json": (
        "5dc6e5830665f1f30a557ebd83361ef02c130b97defb49788422111d1a3f174c"
    ),
    "depth_targets.json": (
        "3ef9c13e41de4e59f97e198609d94d83130dacd3b08535711752a4ffc8bee9ae"
    ),
}

EXPECTED_QUEUE_STATUS = "INGESTION_REQUIRED_BINARY_SHA256_UNPINNED"
EXPECTED_DERIVATIVE_ZERO = ("PARAMETER_MONOTONICITY",)
EXPECTED_VECTOR_ZERO: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, order=True)
class DepthQueueIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class DepthQueueReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, Any]
    base_repo_commit: str | None
    aggregate_semantic_sha256: str | None
    derivative_zero_evidence: tuple[str, ...]
    vector_zero_evidence: tuple[str, ...]
    queue_items_count: int
    rights_status: str
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[DepthQueueIssue, ...]

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
            "derivative_zero_evidence": list(self.derivative_zero_evidence),
            "vector_zero_evidence": list(self.vector_zero_evidence),
            "queue_items_count": self.queue_items_count,
            "rights_status": self.rights_status,
            "canonical_write_allowed": self.canonical_write_allowed,
            "database_import_allowed": self.database_import_allowed,
            "production_release_allowed": self.production_release_allowed,
            "errors": [asdict(issue) for issue in self.errors],
        }


class DepthQueueValidator:
    """Validator for DATA-MATH12-045 remaining depth queue."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_DEPTH_QUEUE_PATH,
    ) -> DepthQueueReport:
        path = dataset_path.resolve()
        initial: list[DepthQueueIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        queue_data = self._load_object(path / "remaining_ingestion_queue.json", initial)
        targets_data = self._load_object(path / "depth_targets.json", initial)

        checks_to_errors: dict[str, list[DepthQueueIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "zero_evidence_invariants": self._validate_zero_evidence(queue_data),
            "priority_ingestion_queue": self._validate_ingestion_queue(queue_data),
            "depth_targets_integrity": self._validate_depth_targets(targets_data),
            "critical_boundaries": self._validate_critical_boundaries(contract, queue_data),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[DepthQueueIssue] = []
        if aggregate != EXPECTED_DEPTH_QUEUE_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_DEPTH_QUEUE_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_DEPTH_QUEUE_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-045 aggregate.",
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

        zero_types = queue_data.get("zero_evidence_problem_types", {})
        deriv_zero = tuple(zero_types.get("DERIVATIVE_APPLICATIONS", []))
        vec_zero = tuple(zero_types.get("VECTOR_LEGACY_SUBSCOPE", []))
        queue_items = queue_data.get("priority_ingestion", [])

        counts = {
            "priority_queue_items": len(queue_items),
            "derivative_zero_evidence_count": len(deriv_zero),
            "vector_zero_evidence_count": len(vec_zero),
        }

        return DepthQueueReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            aggregate_semantic_sha256=aggregate,
            derivative_zero_evidence=deriv_zero,
            vector_zero_evidence=vec_zero,
            queue_items_count=len(queue_items),
            rights_status=contract.get("rights_status", "UNKNOWN"),
            canonical_write_allowed=bool(contract.get("canonical_write_allowed", True)),
            database_import_allowed=bool(contract.get("database_import_allowed", True)),
            production_release_allowed=bool(contract.get("production_release_allowed", True)),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[DepthQueueIssue]
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
    ) -> list[DepthQueueIssue]:
        issues: list[DepthQueueIssue] = []
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
    ) -> list[DepthQueueIssue]:
        issues: list[DepthQueueIssue] = []
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
        self, contract: dict[str, Any]
    ) -> list[DepthQueueIssue]:
        issues: list[DepthQueueIssue] = []
        if contract.get("base_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_repo_commit",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "data_contract.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {contract.get('base_repo_commit')!r}.",
                )
            )
        return issues

    def _validate_zero_evidence(
        self, queue_data: dict[str, Any]
    ) -> list[DepthQueueIssue]:
        issues: list[DepthQueueIssue] = []
        zero_types = queue_data.get("zero_evidence_problem_types", {})
        deriv_zero = tuple(zero_types.get("DERIVATIVE_APPLICATIONS", []))
        vec_zero = tuple(zero_types.get("VECTOR_LEGACY_SUBSCOPE", []))

        if deriv_zero != EXPECTED_DERIVATIVE_ZERO:
            issues.append(
                self._issue(
                    "zero_evidence_invariants",
                    "DERIVATIVE_ZERO_MISMATCH",
                    "remaining_ingestion_queue.json",
                    f"Derivative remaining zero evidence must be exactly {EXPECTED_DERIVATIVE_ZERO}, got {deriv_zero}.",
                )
            )
        if vec_zero != EXPECTED_VECTOR_ZERO:
            issues.append(
                self._issue(
                    "zero_evidence_invariants",
                    "VECTOR_ZERO_MISMATCH",
                    "remaining_ingestion_queue.json",
                    f"Vector remaining zero evidence must be exactly empty {EXPECTED_VECTOR_ZERO}, got {vec_zero}.",
                )
            )
        return issues

    def _validate_ingestion_queue(
        self, queue_data: dict[str, Any]
    ) -> list[DepthQueueIssue]:
        issues: list[DepthQueueIssue] = []
        items = queue_data.get("priority_ingestion", [])
        if len(items) != 3:
            issues.append(
                self._issue(
                    "priority_ingestion_queue",
                    "QUEUE_LENGTH_MISMATCH",
                    "remaining_ingestion_queue.json",
                    f"Expected 3 priority ingestion items, got {len(items)}.",
                )
            )

        for i, item in enumerate(items):
            status = item.get("status")
            if status != EXPECTED_QUEUE_STATUS:
                issues.append(
                    self._issue(
                        "priority_ingestion_queue",
                        "INVALID_QUEUE_STATUS",
                        f"remaining_ingestion_queue.json[{i}]",
                        f"Queue item must have status {EXPECTED_QUEUE_STATUS}, got {status!r}.",
                    )
                )
            if item.get("promotion_allowed") is not False:
                issues.append(
                    self._issue(
                        "priority_ingestion_queue",
                        "PROMOTION_NOT_BLOCKED",
                        f"remaining_ingestion_queue.json[{i}]",
                        "promotion_allowed must be false for external queue leads.",
                    )
                )
            if "source_pdf_sha256" in item:
                issues.append(
                    self._issue(
                        "priority_ingestion_queue",
                        "PREMATURE_SHA_PINNING",
                        f"remaining_ingestion_queue.json[{i}]",
                        "Unpinned leads must not have source_pdf_sha256 set.",
                    )
                )

        policy = queue_data.get("policy", {})
        if policy.get("unhashed_external_source_counts_as_verified") is not False:
            issues.append(
                self._issue(
                    "priority_ingestion_queue",
                    "UNHASHED_COUNTED_AS_VERIFIED",
                    "remaining_ingestion_queue.json",
                    "unhashed_external_source_counts_as_verified must be false.",
                )
            )
        if policy.get("synthetic_gap_fill") is not False:
            issues.append(
                self._issue(
                    "priority_ingestion_queue",
                    "SYNTHETIC_GAP_FILL_NOT_FALSE",
                    "remaining_ingestion_queue.json",
                    "synthetic_gap_fill must be false.",
                )
            )

        return issues

    def _validate_depth_targets(
        self, targets_data: dict[str, Any]
    ) -> list[DepthQueueIssue]:
        issues: list[DepthQueueIssue] = []
        qa_targets = targets_data.get("coach_learning_qa_targets", {})
        if qa_targets.get("minimum_verified_units_per_problem_type") != 5:
            issues.append(
                self._issue(
                    "depth_targets_integrity",
                    "MIN_UNITS_TARGET_MISMATCH",
                    "depth_targets.json",
                    "minimum_verified_units_per_problem_type must be 5.",
                )
            )
        if qa_targets.get("minimum_independent_source_families") != 3:
            issues.append(
                self._issue(
                    "depth_targets_integrity",
                    "MIN_FAMILIES_TARGET_MISMATCH",
                    "depth_targets.json",
                    "minimum_independent_source_families must be 3.",
                )
            )
        if qa_targets.get("maximum_dominant_source_share") != 0.7:
            issues.append(
                self._issue(
                    "depth_targets_integrity",
                    "MAX_SHARE_TARGET_MISMATCH",
                    "depth_targets.json",
                    "maximum_dominant_source_share must be 0.7.",
                )
            )
        if targets_data.get("production_quality_target_met") is not False:
            issues.append(
                self._issue(
                    "depth_targets_integrity",
                    "QUALITY_TARGET_NOT_FALSE",
                    "depth_targets.json",
                    "production_quality_target_met must be false.",
                )
            )
        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], queue_data: dict[str, Any]
    ) -> list[DepthQueueIssue]:
        issues: list[DepthQueueIssue] = []
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
        if contract.get("rights_status") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "RIGHTS_NOT_REVIEW_REQUIRED",
                    "data_contract.json",
                    "rights_status must be REVIEW_REQUIRED.",
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
        self, path: Path, issues: list[DepthQueueIssue]
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
    ) -> DepthQueueIssue:
        return DepthQueueIssue(
            check=check, code=code, location=location, message=message
        )
