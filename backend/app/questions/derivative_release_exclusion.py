from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DERIVATIVE_RELEASE_EXCLUSION_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "derivative_applications_v0_1"
    / "release_exclusion"
    / "v0_1"
)

EXPECTED_RELEASE_EXCLUSION_AGGREGATE_SHA256 = (
    "09ce790a7afc6b20b7a63f2a59ade75ef3e0e7d44ced8f0d01e6bb60e4a49a57"
)
EXPECTED_BASE_REPO_COMMIT = "453e3817c3d77098ad5d3171ed9b466391ac223b"

SEMANTIC_FILES_ORDER = ("release_exclusion.json",)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "release_exclusion.json": (
        "30b888e4e4e775b08ec20a018582f0f1eb558f5d6f11cb2c8776b4a707ae213a"
    ),
}

EXPECTED_INVARIANTS = {
    "verified_groups_total": 39,
    "groups_in_candidate_promotion_set": 38,
    "children_in_candidate_promotion_set": 152,
    "excluded_visual_groups": ["M12_DERIV_GROUP_0012"],
    "production_release_eligible": 0,
    "database_import_allowed": False,
    "canonical_write_allowed": False,
    "production_release_allowed": False,
    "rights_status": "REVIEW_REQUIRED",
    "academic_review_status": "VERIFIED_RETAINED",
    "decision": "EXCLUDE_FROM_CANONICAL_PROMOTION_SET",
}


@dataclass(frozen=True, slots=True, order=True)
class DerivativeReleaseExclusionIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class DerivativeReleaseExclusionReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str | None
    aggregate_semantic_sha256: str | None
    group_candidate_id: str | None
    academic_review_status: str | None
    decision: str | None
    verified_groups_total: int
    groups_in_candidate_promotion_set: int
    children_in_candidate_promotion_set: int
    excluded_visual_groups: tuple[str, ...]
    rights_status: str | None
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_eligible: int
    errors: tuple[DerivativeReleaseExclusionIssue, ...]

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
            "group_candidate_id": self.group_candidate_id,
            "academic_review_status": self.academic_review_status,
            "decision": self.decision,
            "verified_groups_total": self.verified_groups_total,
            "groups_in_candidate_promotion_set": self.groups_in_candidate_promotion_set,
            "children_in_candidate_promotion_set": self.children_in_candidate_promotion_set,
            "excluded_visual_groups": list(self.excluded_visual_groups),
            "rights_status": self.rights_status,
            "canonical_write_allowed": self.canonical_write_allowed,
            "database_import_allowed": self.database_import_allowed,
            "production_release_eligible": self.production_release_eligible,
            "errors": [asdict(issue) for issue in self.errors],
        }


class DerivativeReleaseExclusionValidator:
    """Validate DATA-MATH12-036 GDPT 2018 Grade 12 Math derivative release exclusion candidate."""

    def validate(
        self,
        exclusion_path: Path = DEFAULT_DERIVATIVE_RELEASE_EXCLUSION_PATH,
    ) -> DerivativeReleaseExclusionReport:
        path = exclusion_path.resolve()
        initial: list[DerivativeReleaseExclusionIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        exclusion = self._load_object(path / "release_exclusion.json", initial)

        checks_to_errors: dict[str, list[DerivativeReleaseExclusionIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "exclusion_semantics": self._validate_exclusion_semantics(
                exclusion
            ),
            "critical_boundaries": self._validate_critical_boundaries(
                contract, exclusion
            ),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[DerivativeReleaseExclusionIssue] = []
        if aggregate != EXPECTED_RELEASE_EXCLUSION_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_RELEASE_EXCLUSION_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_RELEASE_EXCLUSION_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-036 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        # Check exact invariants
        invariants_errors: list[DerivativeReleaseExclusionIssue] = []
        promo = exclusion.get("promotion_effect", {})
        actual_invariants = {
            "verified_groups_total": promo.get("verified_groups_total"),
            "groups_in_candidate_promotion_set": promo.get(
                "groups_in_candidate_promotion_set"
            ),
            "children_in_candidate_promotion_set": promo.get(
                "children_in_candidate_promotion_set"
            ),
            "excluded_visual_groups": promo.get("excluded_visual_groups"),
            "production_release_eligible": exclusion.get(
                "production_release_eligible"
            ),
            "database_import_allowed": contract.get("database_import_allowed"),
            "canonical_write_allowed": contract.get("canonical_write_allowed"),
            "production_release_allowed": contract.get(
                "production_release_allowed"
            ),
            "rights_status": exclusion.get("rights_status"),
            "academic_review_status": exclusion.get("academic_review_status"),
            "decision": exclusion.get("decision"),
        }
        if actual_invariants != EXPECTED_INVARIANTS:
            invariants_errors.append(
                self._issue(
                    "exact_invariants",
                    "INVARIANT_COUNT_MISMATCH",
                    "release_exclusion.json",
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
            "verified_groups_total": promo.get("verified_groups_total", 0),
            "groups_in_candidate_promotion_set": promo.get(
                "groups_in_candidate_promotion_set", 0
            ),
            "children_in_candidate_promotion_set": promo.get(
                "children_in_candidate_promotion_set", 0
            ),
            "excluded_visual_groups_count": len(
                promo.get("excluded_visual_groups", [])
            ),
        }

        return DerivativeReleaseExclusionReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            aggregate_semantic_sha256=aggregate,
            group_candidate_id=exclusion.get("group_candidate_id"),
            academic_review_status=exclusion.get("academic_review_status"),
            decision=exclusion.get("decision"),
            verified_groups_total=promo.get("verified_groups_total", 0),
            groups_in_candidate_promotion_set=promo.get(
                "groups_in_candidate_promotion_set", 0
            ),
            children_in_candidate_promotion_set=promo.get(
                "children_in_candidate_promotion_set", 0
            ),
            excluded_visual_groups=tuple(promo.get("excluded_visual_groups", [])),
            rights_status=exclusion.get("rights_status"),
            canonical_write_allowed=bool(
                contract.get("canonical_write_allowed", True)
            ),
            database_import_allowed=bool(
                contract.get("database_import_allowed", True)
            ),
            production_release_eligible=int(
                exclusion.get("production_release_eligible", 1)
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[DerivativeReleaseExclusionIssue]
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
    ) -> list[DerivativeReleaseExclusionIssue]:
        issues: list[DerivativeReleaseExclusionIssue] = []
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
    ) -> list[DerivativeReleaseExclusionIssue]:
        issues: list[DerivativeReleaseExclusionIssue] = []
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
    ) -> list[DerivativeReleaseExclusionIssue]:
        issues: list[DerivativeReleaseExclusionIssue] = []
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

    def _validate_exclusion_semantics(
        self, exclusion: dict[str, Any]
    ) -> list[DerivativeReleaseExclusionIssue]:
        issues: list[DerivativeReleaseExclusionIssue] = []
        if exclusion.get("group_candidate_id") != "M12_DERIV_GROUP_0012":
            issues.append(
                self._issue(
                    "exclusion_semantics",
                    "INVALID_GROUP_CANDIDATE_ID",
                    "release_exclusion.json",
                    f"Expected group M12_DERIV_GROUP_0012, got {exclusion.get('group_candidate_id')!r}.",
                )
            )
        if exclusion.get("academic_review_status") != "VERIFIED_RETAINED":
            issues.append(
                self._issue(
                    "exclusion_semantics",
                    "INVALID_ACADEMIC_REVIEW_STATUS",
                    "release_exclusion.json",
                    f"Expected VERIFIED_RETAINED, got {exclusion.get('academic_review_status')!r}.",
                )
            )
        if exclusion.get("existing_visual_status") != "BLOCKED_SOURCE_VISUAL_MISSING":
            issues.append(
                self._issue(
                    "exclusion_semantics",
                    "INVALID_VISUAL_STATUS",
                    "release_exclusion.json",
                    f"Expected BLOCKED_SOURCE_VISUAL_MISSING, got {exclusion.get('existing_visual_status')!r}.",
                )
            )
        if exclusion.get("decision") != "EXCLUDE_FROM_CANONICAL_PROMOTION_SET":
            issues.append(
                self._issue(
                    "exclusion_semantics",
                    "INVALID_DECISION",
                    "release_exclusion.json",
                    f"Expected EXCLUDE_FROM_CANONICAL_PROMOTION_SET, got {exclusion.get('decision')!r}.",
                )
            )
        if exclusion.get("academic_data_mutated") is not False:
            issues.append(
                self._issue(
                    "exclusion_semantics",
                    "ACADEMIC_DATA_MUTATED_VIOLATION",
                    "release_exclusion.json",
                    "academic_data_mutated must be false.",
                )
            )
        if exclusion.get("answer_key_mutated") is not False:
            issues.append(
                self._issue(
                    "exclusion_semantics",
                    "ANSWER_KEY_MUTATED_VIOLATION",
                    "release_exclusion.json",
                    "answer_key_mutated must be false.",
                )
            )
        promo = exclusion.get("promotion_effect", {})
        if promo.get("verified_groups_total") != 39:
            issues.append(
                self._issue(
                    "exclusion_semantics",
                    "VERIFIED_GROUPS_TOTAL_MISMATCH",
                    "release_exclusion.json[promotion_effect]",
                    f"Expected 39 verified groups, got {promo.get('verified_groups_total')}.",
                )
            )
        if promo.get("groups_in_candidate_promotion_set") != 38:
            issues.append(
                self._issue(
                    "exclusion_semantics",
                    "PROMOTION_GROUPS_MISMATCH",
                    "release_exclusion.json[promotion_effect]",
                    f"Expected 38 promotion groups, got {promo.get('groups_in_candidate_promotion_set')}.",
                )
            )
        if promo.get("children_in_candidate_promotion_set") != 152:
            issues.append(
                self._issue(
                    "exclusion_semantics",
                    "PROMOTION_CHILDREN_MISMATCH",
                    "release_exclusion.json[promotion_effect]",
                    f"Expected 152 promotion children, got {promo.get('children_in_candidate_promotion_set')}.",
                )
            )
        if promo.get("excluded_visual_groups") != ["M12_DERIV_GROUP_0012"]:
            issues.append(
                self._issue(
                    "exclusion_semantics",
                    "EXCLUDED_GROUPS_MISMATCH",
                    "release_exclusion.json[promotion_effect]",
                    f"Expected ['M12_DERIV_GROUP_0012'], got {promo.get('excluded_visual_groups')}.",
                )
            )
        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], exclusion: dict[str, Any]
    ) -> list[DerivativeReleaseExclusionIssue]:
        issues: list[CoreEvidenceClosureIssue] = []
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
        if exclusion.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DATABASE_IMPORT_NOT_BLOCKED",
                    "release_exclusion.json",
                    "database_import_allowed must be false.",
                )
            )
        if exclusion.get("production_release_eligible") != 0:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "PRODUCTION_RELEASE_ELIGIBLE_VIOLATION",
                    "release_exclusion.json",
                    "production_release_eligible must be 0.",
                )
            )
        if exclusion.get("rights_status") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "RIGHTS_NOT_REVIEW_REQUIRED",
                    "release_exclusion.json",
                    f"rights_status must be REVIEW_REQUIRED, got {exclusion.get('rights_status')!r}.",
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
        self, path: Path, issues: list[DerivativeReleaseExclusionIssue]
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
    ) -> DerivativeReleaseExclusionIssue:
        return DerivativeReleaseExclusionIssue(
            check=check, code=code, location=location, message=message
        )
