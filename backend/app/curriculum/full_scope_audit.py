from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CURRICULUM_ROOT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
)
DEFAULT_FULL_SCOPE_AUDIT_PATH = CURRICULUM_ROOT / "audit" / "v0_1"
EXPECTED_AUDIT_AGGREGATE_SHA256 = (
    "ea64fd6dd257d80f4d19477a7708f21229643d87ad7793b22504bb680c7a22e5"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256 = (
    "a14b4934afae52eb5f620985d1a7097dd43dc8da88cd6b9dade7b396023f46e1"
)
AUDITED_REPO_HEAD_COMMIT = "bc0b9c1c44be804450033d7d6d7371327e3b382c"
OFFICIAL_SCOPE_GIT_BLOB_SHA1 = "ac699ebee7ebab1758e0e4d047ca866a72c2bf11"

EXPECTED_CORE_SCOPES = (
    "M12_CORE_CALCULUS_DERIVATIVE_APPLICATIONS",
    "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL",
    "M12_CORE_GEOMETRY_COORDINATE_3D",
    "M12_CORE_STATISTICS_GROUPED_DATA",
    "M12_CORE_PROBABILITY_CONDITIONAL",
)
EXPECTED_CROSS_CUTTING = (
    "M12_CORE_SOFTWARE_PRACTICE",
    "M12_CORE_EXPERIENTIAL_ACTIVITIES",
)
EXPECTED_OPTIONAL_TOPICS = (
    "M12_SPECIAL_TOPIC_12_1",
    "M12_SPECIAL_TOPIC_12_2",
    "M12_SPECIAL_TOPIC_12_3",
)
EXPECTED_GROUPED_DERIVED_GAPS = (
    "IDENTIFY_MORE_STABLE_GROUPED_DATA",
    "INTERPRET_GROUPED_DISPERSION_MEASURE",
    "CONCLUDE_FROM_GROUPED_DISPERSION",
    "PARAMETER_FROM_GROUPED_VARIANCE_SD",
    "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS",
)
EXPECTED_GROUPED_INTERPRETATION_MAPPING = (
    "IDENTIFY_MORE_STABLE_GROUPED_DATA",
    "INTERPRET_GROUPED_DISPERSION_MEASURE",
    "CONCLUDE_FROM_GROUPED_DISPERSION",
)

SEMANTIC_FILES_ORDER = (
    "official_scope_snapshot.json",
    "core_coverage_audit.json",
    "probability_tree_source_leads.json",
    "cross_cutting_optional_audit.json",
    "curriculum_taxonomy_drift.json",
    "dataset_lineage.json",
    "remaining_work.json",
    "audit_stats.json",
    "release_readiness.json",
    "curriculum_alignment_candidate.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "official_scope_snapshot.json": (
        "99cd2099eb585e2ea1ed463e123591155f25a08fff0bcbb0b5fa1211c83f53ca"
    ),
    "core_coverage_audit.json": (
        "782543cf982c919c87a39a5789a2f09261c5cecccf105a125f6ecce37e8d97b3"
    ),
    "probability_tree_source_leads.json": (
        "45c023fe22fe149c1bc756c0563af5fbcc3cb544934b732c0ca62056dcbb7fe1"
    ),
    "cross_cutting_optional_audit.json": (
        "97ac954d863b4f5a52e63d06b260b665c29deb15f67c3a49f688b0863fe60a28"
    ),
    "curriculum_taxonomy_drift.json": (
        "a8893905fbe3c8e4e6c63c7a39ad4998ac87cfc533811b2f384080588e2113b7"
    ),
    "dataset_lineage.json": (
        "4d2aa8ecb1a9b411de46574a2baa674d6d430591f95c797833d4b2cebb1bfe13"
    ),
    "remaining_work.json": (
        "08240c3143f9c9e7766df5e435bb7e100ed8c46c97143710379f8dffffd5d184"
    ),
    "audit_stats.json": (
        "865b6e7d0a50755d06abd1377c9427bf0c5ee4c177e56b792335b8079818a6b8"
    ),
    "release_readiness.json": (
        "cee626c1ee9d9492c24b18feb3c4d99316d45c892c5e7100a161ff9f9468eb43"
    ),
    "curriculum_alignment_candidate.json": (
        "4eb047a5544c554530fbc0fbe775d7315b1bf420b99a38e74792d2350ecc5a69"
    ),
}

EXPECTED_INVARIANTS = {
    "official_core_scopes": 5,
    "official_core_scopes_fully_evidenced": 3,
    "official_core_scopes_partially_evidenced": 2,
    "official_core_scopes_missing_entirely": 0,
    "official_normalized_requirements_total": 20,
    "official_normalized_requirements_covered": 18,
    "official_normalized_requirements_partial": 2,
    "cross_cutting_items_materialized": 0,
    "optional_special_topics_materialized_as_dedicated_datasets": 0,
    "production_release_ready_core_scopes": 0,
}


@dataclass(frozen=True, slots=True, order=True)
class FullScopeAuditIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class FullScopeAuditReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    repo_head_commit: str | None
    official_core_scopes_total: int
    fully_evidenced_core_scopes: tuple[str, ...]
    partially_evidenced_core_scopes: tuple[str, ...]
    missing_core_scopes: tuple[str, ...]
    normalized_requirements_total: int
    normalized_requirements_covered: int
    normalized_requirements_partial: int
    cross_cutting_materialized: int
    optional_topics_materialized: int
    aggregate_semantic_sha256: str | None
    production_release_ready: bool
    activation_allowed: bool
    errors: tuple[FullScopeAuditIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "repo_head_commit": self.repo_head_commit,
            "official_core_scopes_total": self.official_core_scopes_total,
            "fully_evidenced_core_scopes": list(self.fully_evidenced_core_scopes),
            "partially_evidenced_core_scopes": list(
                self.partially_evidenced_core_scopes
            ),
            "missing_core_scopes": list(self.missing_core_scopes),
            "normalized_requirements_total": self.normalized_requirements_total,
            "normalized_requirements_covered": (
                self.normalized_requirements_covered
            ),
            "normalized_requirements_partial": (
                self.normalized_requirements_partial
            ),
            "cross_cutting_materialized": self.cross_cutting_materialized,
            "optional_topics_materialized": self.optional_topics_materialized,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "production_release_ready": self.production_release_ready,
            "activation_allowed": self.activation_allowed,
            "errors": [asdict(error) for error in self.errors],
        }


class FullScopeAuditValidator:
    """Validate DATA-MATH12-032 GDPT 2018 Grade 12 Math full-scope audit."""

    def validate(
        self,
        audit_path: Path = DEFAULT_FULL_SCOPE_AUDIT_PATH,
        *,
        curriculum_root: Path = CURRICULUM_ROOT,
    ) -> FullScopeAuditReport:
        path = audit_path.resolve()
        curriculum_root = curriculum_root.resolve()
        initial: list[FullScopeAuditIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        snapshot = self._load_object(
            path / "official_scope_snapshot.json", initial
        )
        core_coverage = self._load_list(
            path / "core_coverage_audit.json", initial
        )
        tree_leads = self._load_object(
            path / "probability_tree_source_leads.json", initial
        )
        cross_cutting = self._load_object(
            path / "cross_cutting_optional_audit.json", initial
        )
        drift = self._load_object(
            path / "curriculum_taxonomy_drift.json", initial
        )
        lineage = self._load_object(path / "dataset_lineage.json", initial)
        remaining_work = self._load_object(
            path / "remaining_work.json", initial
        )
        stats = self._load_object(path / "audit_stats.json", initial)
        readiness = self._load_object(path / "release_readiness.json", initial)
        alignment_candidate = self._load_object(
            path / "curriculum_alignment_candidate.json", initial
        )

        checks_to_errors: dict[str, list[FullScopeAuditIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "repo_head_binding": self._validate_repo_head_binding(
                contract, snapshot, drift, curriculum_root
            ),
            "official_scope_structure": self._validate_official_scope_structure(
                snapshot
            ),
            "core_coverage_status": self._validate_core_coverage_status(
                core_coverage, snapshot, stats
            ),
            "grouped_data_dispersion_gaps": self._validate_grouped_data_gaps(
                core_coverage
            ),
            "probability_tree_source_leads": self._validate_probability_tree_leads(
                tree_leads
            ),
            "cross_cutting_and_optional_boundary": (
                self._validate_cross_cutting_and_optional(
                    cross_cutting, stats, contract
                )
            ),
            "vector_legacy_non_double_counting": (
                self._validate_vector_legacy_non_double_counting(
                    core_coverage, lineage, drift, contract
                )
            ),
            "alignment_candidate_boundary": (
                self._validate_alignment_candidate_boundary(
                    alignment_candidate, drift, contract
                )
            ),
            "release_readiness_boundary": self._validate_release_readiness(
                readiness, stats, contract
            ),
        }
        for issue in initial:
            if issue.check != "required_files":
                checks_to_errors.setdefault(issue.check, []).append(issue)

        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[FullScopeAuditIssue] = []
        expected_aggregate = contract.get("aggregate_semantic_sha256")
        if aggregate != EXPECTED_AUDIT_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_AUDIT_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if expected_aggregate != EXPECTED_AUDIT_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-032 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        # Extract counts and statuses
        fully_evidenced: list[str] = []
        partially_evidenced: list[str] = []
        missing_scopes: list[str] = []
        covered_reqs = 0
        partial_reqs = 0

        for row in core_coverage:
            scope = str(row.get("official_scope_code"))
            status = row.get("status")
            if status == "FULLY_EVIDENCED_NOT_RELEASE_READY":
                fully_evidenced.append(scope)
            elif status in {
                "PARTIAL_EVIDENCE_CORE_GAP_REMAINS",
                "PARTIAL_EVIDENCE_TREE_REPRESENTATION_NOT_MATERIALIZED",
            }:
                partially_evidenced.append(scope)
            elif status == "MISSING_ENTIRELY":
                missing_scopes.append(scope)

            norm_map = row.get("normalized_coverage_status", {})
            if isinstance(norm_map, dict):
                for req_stat in norm_map.values():
                    if req_stat in {"COVERED", "COVERED_BY_SOURCE_BACKED_CHILD_EVIDENCE"}:
                        covered_reqs += 1
                    elif str(req_stat).startswith("PARTIAL"):
                        partial_reqs += 1

        invariants_check: list[FullScopeAuditIssue] = []
        counts = {
            "official_core_scopes": len(core_coverage),
            "official_core_scopes_fully_evidenced": len(fully_evidenced),
            "official_core_scopes_partially_evidenced": len(partially_evidenced),
            "official_core_scopes_missing_entirely": len(missing_scopes),
            "official_normalized_requirements_total": covered_reqs + partial_reqs,
            "official_normalized_requirements_covered": covered_reqs,
            "official_normalized_requirements_partial": partial_reqs,
            "cross_cutting_items_materialized": self._int_value(
                stats.get("cross_cutting_items_materialized"), default=-1
            ),
            "optional_special_topics_materialized_as_dedicated_datasets": (
                self._int_value(
                    stats.get(
                        "optional_special_topics_materialized_as_dedicated_datasets"
                    ),
                    default=-1,
                )
            ),
            "production_release_ready_core_scopes": self._int_value(
                stats.get("production_release_ready_core_scopes"), default=-1
            ),
        }
        if counts != EXPECTED_INVARIANTS:
            invariants_check.append(
                self._issue(
                    "exact_invariants",
                    "INVARIANT_COUNT_MISMATCH",
                    "audit_stats.json",
                    f"Expected {EXPECTED_INVARIANTS!r}, got {counts!r}.",
                )
            )
        checks_to_errors["exact_invariants"] = invariants_check

        errors = tuple(
            sorted(issue for issues in checks_to_errors.values() for issue in issues)
        )
        checks = {
            name: not issues for name, issues in checks_to_errors.items()
        }

        return FullScopeAuditReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            repo_head_commit=contract.get("repo_head_commit"),
            official_core_scopes_total=len(core_coverage),
            fully_evidenced_core_scopes=tuple(sorted(fully_evidenced)),
            partially_evidenced_core_scopes=tuple(sorted(partially_evidenced)),
            missing_core_scopes=tuple(sorted(missing_scopes)),
            normalized_requirements_total=covered_reqs + partial_reqs,
            normalized_requirements_covered=covered_reqs,
            normalized_requirements_partial=partial_reqs,
            cross_cutting_materialized=counts["cross_cutting_items_materialized"],
            optional_topics_materialized=counts[
                "optional_special_topics_materialized_as_dedicated_datasets"
            ],
            aggregate_semantic_sha256=aggregate,
            production_release_ready=(
                readiness.get("production_release_ready") is True
            ),
            activation_allowed=(
                alignment_candidate.get("activation_allowed") is True
            ),
            errors=errors,
        )

    def _validate_curated_hash_contract(
        self, path: Path, contract: dict[str, Any]
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
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
        if set(order) != set(expected_hashes) or tuple(order) != SEMANTIC_FILES_ORDER:
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "SEMANTIC_FILE_SET_MISMATCH",
                    contract_path.name,
                    "Semantic file order does not match expected audit files.",
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

    def _validate_repo_head_binding(
        self,
        contract: dict[str, Any],
        snapshot: dict[str, Any],
        drift: dict[str, Any],
        curriculum_root: Path,
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
        contract_head = contract.get("repo_head_commit")
        snapshot_head = snapshot.get("repo_head_commit")

        if contract_head != AUDITED_REPO_HEAD_COMMIT:
            issues.append(
                self._issue(
                    "repo_head_binding",
                    "REPO_HEAD_COMMIT_MISMATCH",
                    "data_contract.json",
                    f"Expected repo_head_commit {AUDITED_REPO_HEAD_COMMIT!r}, got {contract_head!r}.",
                )
            )
        if snapshot_head != AUDITED_REPO_HEAD_COMMIT:
            issues.append(
                self._issue(
                    "repo_head_binding",
                    "SNAPSHOT_REPO_HEAD_MISMATCH",
                    "official_scope_snapshot.json",
                    f"Expected repo_head_commit {AUDITED_REPO_HEAD_COMMIT!r}, got {snapshot_head!r}.",
                )
            )

        official_scope_file = curriculum_root / "official_scope.json"
        if not official_scope_file.is_file():
            issues.append(
                self._issue(
                    "repo_head_binding",
                    "OFFICIAL_SCOPE_FILE_MISSING",
                    str(official_scope_file),
                    "Repo official_scope.json is missing.",
                )
            )
        else:
            actual_blob = self._git_blob_sha1(official_scope_file)
            if actual_blob != OFFICIAL_SCOPE_GIT_BLOB_SHA1:
                issues.append(
                    self._issue(
                        "repo_head_binding",
                        "OFFICIAL_SCOPE_BLOB_MISMATCH",
                        "official_scope.json",
                        f"Expected blob {OFFICIAL_SCOPE_GIT_BLOB_SHA1!r}, got {actual_blob!r}.",
                    )
                )

        repo_bindings = drift.get("repo_bindings", {})
        if isinstance(repo_bindings, dict):
            for field, exp_blob in [
                ("manifest_git_blob_sha1", "manifest.json"),
                ("chapters_git_blob_sha1", "chapters.json"),
                ("topics_git_blob_sha1", "topics.json"),
                ("problem_types_git_blob_sha1", "problem_types.json"),
                ("concepts_git_blob_sha1", "concepts.json"),
                ("learning_outcomes_git_blob_sha1", "learning_outcomes.json"),
            ]:
                target = curriculum_root / exp_blob
                if target.is_file():
                    actual = self._git_blob_sha1(target)
                    recorded = repo_bindings.get(field)
                    if actual != recorded:
                        issues.append(
                            self._issue(
                                "repo_head_binding",
                                "CANONICAL_FILE_BLOB_MISMATCH",
                                exp_blob,
                                f"Recorded blob {recorded!r} != actual {actual!r}.",
                            )
                        )

        return issues

    def _validate_official_scope_structure(
        self, snapshot: dict[str, Any]
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
        core = snapshot.get("core_program", [])
        cross = snapshot.get("cross_cutting", [])
        opt = snapshot.get("optional_study_topics", [])

        if not isinstance(core, list) or len(core) != 5:
            issues.append(
                self._issue(
                    "official_scope_structure",
                    "CORE_SCOPE_COUNT_MISMATCH",
                    "official_scope_snapshot.json",
                    f"Expected exactly 5 official core scopes, got {len(core) if isinstance(core, list) else 0}.",
                )
            )
        else:
            core_codes = tuple(row.get("official_scope_code") for row in core)
            if core_codes != EXPECTED_CORE_SCOPES:
                issues.append(
                    self._issue(
                        "official_scope_structure",
                        "CORE_SCOPE_CODES_MISMATCH",
                        "official_scope_snapshot.json",
                        f"Expected core scopes {EXPECTED_CORE_SCOPES!r}, got {core_codes!r}.",
                    )
                )
            total_reqs = sum(
                len(row.get("normalized_coverage", [])) for row in core
            )
            if total_reqs != 20:
                issues.append(
                    self._issue(
                        "official_scope_structure",
                        "NORMALIZED_REQUIREMENTS_COUNT_MISMATCH",
                        "official_scope_snapshot.json",
                        f"Expected 20 normalized requirements across core scopes, got {total_reqs}.",
                    )
                )

        if not isinstance(cross, list) or len(cross) != 2:
            issues.append(
                self._issue(
                    "official_scope_structure",
                    "CROSS_CUTTING_COUNT_MISMATCH",
                    "official_scope_snapshot.json",
                    f"Expected 2 cross-cutting items, got {len(cross) if isinstance(cross, list) else 0}.",
                )
            )
        else:
            cross_codes = tuple(row.get("official_scope_code") for row in cross)
            if cross_codes != EXPECTED_CROSS_CUTTING:
                issues.append(
                    self._issue(
                        "official_scope_structure",
                        "CROSS_CUTTING_CODES_MISMATCH",
                        "official_scope_snapshot.json",
                        f"Expected {EXPECTED_CROSS_CUTTING!r}, got {cross_codes!r}.",
                    )
                )

        if not isinstance(opt, list) or len(opt) != 3:
            issues.append(
                self._issue(
                    "official_scope_structure",
                    "OPTIONAL_TOPICS_COUNT_MISMATCH",
                    "official_scope_snapshot.json",
                    f"Expected 3 optional study topics, got {len(opt) if isinstance(opt, list) else 0}.",
                )
            )
        else:
            opt_codes = tuple(row.get("official_scope_code") for row in opt)
            if opt_codes != EXPECTED_OPTIONAL_TOPICS:
                issues.append(
                    self._issue(
                        "official_scope_structure",
                        "OPTIONAL_TOPICS_CODES_MISMATCH",
                        "official_scope_snapshot.json",
                        f"Expected {EXPECTED_OPTIONAL_TOPICS!r}, got {opt_codes!r}.",
                    )
                )

        return issues

    def _validate_core_coverage_status(
        self,
        core_coverage: list[dict[str, Any]],
        snapshot: dict[str, Any],
        stats: dict[str, Any],
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
        if len(core_coverage) != 5:
            issues.append(
                self._issue(
                    "core_coverage_status",
                    "AUDIT_ROW_COUNT_MISMATCH",
                    "core_coverage_audit.json",
                    f"Expected 5 core coverage audit rows, got {len(core_coverage)}.",
                )
            )
            return issues

        statuses = {
            row.get("official_scope_code"): row.get("status")
            for row in core_coverage
        }

        expected_statuses = {
            "M12_CORE_CALCULUS_DERIVATIVE_APPLICATIONS": (
                "FULLY_EVIDENCED_NOT_RELEASE_READY"
            ),
            "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL": (
                "FULLY_EVIDENCED_NOT_RELEASE_READY"
            ),
            "M12_CORE_GEOMETRY_COORDINATE_3D": (
                "FULLY_EVIDENCED_NOT_RELEASE_READY"
            ),
            "M12_CORE_STATISTICS_GROUPED_DATA": (
                "PARTIAL_EVIDENCE_CORE_GAP_REMAINS"
            ),
            "M12_CORE_PROBABILITY_CONDITIONAL": (
                "PARTIAL_EVIDENCE_TREE_REPRESENTATION_NOT_MATERIALIZED"
            ),
        }

        for scope, expected in expected_statuses.items():
            actual = statuses.get(scope)
            if actual != expected:
                issues.append(
                    self._issue(
                        "core_coverage_status",
                        "CORE_SCOPE_STATUS_MISMATCH",
                        f"core_coverage_audit.json[{scope}]",
                        f"Expected status {expected!r}, got {actual!r}.",
                    )
                )

        for row in core_coverage:
            scope = row.get("official_scope_code")
            blockers = row.get("release_blockers", [])
            if "RIGHTS_REVIEW_REQUIRED" not in blockers:
                issues.append(
                    self._issue(
                        "core_coverage_status",
                        "RIGHTS_BLOCKER_MISSING",
                        f"core_coverage_audit.json[{scope}]",
                        "RIGHTS_REVIEW_REQUIRED must be listed as a release blocker.",
                    )
                )
            if "CURRICULUM_TAXONOMY_ALIGNMENT_NOT_FINAL" not in blockers:
                issues.append(
                    self._issue(
                        "core_coverage_status",
                        "ALIGNMENT_BLOCKER_MISSING",
                        f"core_coverage_audit.json[{scope}]",
                        "CURRICULUM_TAXONOMY_ALIGNMENT_NOT_FINAL must be listed as a release blocker.",
                    )
                )

        return issues

    def _validate_grouped_data_gaps(
        self, core_coverage: list[dict[str, Any]]
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
        disp = next(
            (
                r
                for r in core_coverage
                if r.get("official_scope_code")
                == "M12_CORE_STATISTICS_GROUPED_DATA"
            ),
            None,
        )
        if not disp:
            return issues

        data = disp.get("question_data", {})
        remaining_derived = tuple(data.get("remaining_derived_gaps", []))
        if remaining_derived != EXPECTED_GROUPED_DERIVED_GAPS:
            issues.append(
                self._issue(
                    "grouped_data_dispersion_gaps",
                    "GROUPED_REMAINING_GAPS_MISMATCH",
                    "core_coverage_audit.json[M12_CORE_STATISTICS_GROUPED_DATA]",
                    f"Expected 5 derived gaps {EXPECTED_GROUPED_DERIVED_GAPS!r}, got {remaining_derived!r}.",
                )
            )

        gap_mapping = tuple(disp.get("official_gap_mapping", []))
        if gap_mapping != EXPECTED_GROUPED_INTERPRETATION_MAPPING:
            issues.append(
                self._issue(
                    "grouped_data_dispersion_gaps",
                    "INTERPRETATION_GAP_MAPPING_MISMATCH",
                    "core_coverage_audit.json[M12_CORE_STATISTICS_GROUPED_DATA]",
                    f"Expected interpretation mapping {EXPECTED_GROUPED_INTERPRETATION_MAPPING!r}, got {gap_mapping!r}.",
                )
            )

        norm_status = disp.get("normalized_coverage_status", {})
        if norm_status.get("ý nghĩa và diễn giải các số đặc trưng trong thực tiễn") != "PARTIAL":
            issues.append(
                self._issue(
                    "grouped_data_dispersion_gaps",
                    "INTERPRETATION_REQUIREMENT_NOT_PARTIAL",
                    "core_coverage_audit.json[M12_CORE_STATISTICS_GROUPED_DATA]",
                    "Requirement 'ý nghĩa và diễn giải các số đặc trưng trong thực tiễn' must be PARTIAL.",
                )
            )

        return issues

    def _validate_probability_tree_leads(
        self, tree_leads: dict[str, Any]
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
        status = tree_leads.get("status")
        if status != "SOURCE_LEADS_NOT_CURATED_DATA":
            issues.append(
                self._issue(
                    "probability_tree_source_leads",
                    "TREE_LEADS_STATUS_MISMATCH",
                    "probability_tree_source_leads.json",
                    f"Expected status 'SOURCE_LEADS_NOT_CURATED_DATA', got {status!r}.",
                )
            )
        leads = tree_leads.get("leads", [])
        if not isinstance(leads, list) or len(leads) != 4:
            issues.append(
                self._issue(
                    "probability_tree_source_leads",
                    "TREE_LEADS_COUNT_MISMATCH",
                    "probability_tree_source_leads.json",
                    f"Expected 4 source tree leads, got {len(leads) if isinstance(leads, list) else 0}.",
                )
            )
        else:
            for idx, lead in enumerate(leads):
                loc = f"probability_tree_source_leads.json.leads[{idx}]"
                if lead.get("review_status") == "VERIFIED" or lead.get("verified") is True:
                    issues.append(
                        self._issue(
                            "probability_tree_source_leads",
                            "RAW_LEAD_MARKED_VERIFIED",
                            loc,
                            "Raw probability tree source lead must NOT be marked VERIFIED.",
                        )
                    )
        return issues

    def _validate_cross_cutting_and_optional(
        self,
        cross_cutting: dict[str, Any],
        stats: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
        if stats.get("cross_cutting_items_materialized") != 0:
            issues.append(
                self._issue(
                    "cross_cutting_and_optional_boundary",
                    "CROSS_CUTTING_MATERIALIZED_NONZERO",
                    "audit_stats.json",
                    "cross_cutting_items_materialized must be 0.",
                )
            )
        if (
            stats.get(
                "optional_special_topics_materialized_as_dedicated_datasets"
            )
            != 0
        ):
            issues.append(
                self._issue(
                    "cross_cutting_and_optional_boundary",
                    "OPTIONAL_TOPICS_MATERIALIZED_NONZERO",
                    "audit_stats.json",
                    "optional_special_topics_materialized_as_dedicated_datasets must be 0.",
                )
            )

        for row in cross_cutting.get("cross_cutting", []):
            loc = f"cross_cutting_optional_audit.json[{row.get('official_scope_code')}]"
            st = row.get("status")
            if st != "NOT_MATERIALIZED_AS_DEDICATED_LEARNING_DATA":
                issues.append(
                    self._issue(
                        "cross_cutting_and_optional_boundary",
                        "CROSS_CUTTING_INVALID_STATUS",
                        loc,
                        f"Expected NOT_MATERIALIZED_AS_DEDICATED_LEARNING_DATA, got {st!r}.",
                    )
                )

        for row in cross_cutting.get("optional_study_topics", []):
            loc = f"cross_cutting_optional_audit.json[{row.get('official_scope_code')}]"
            st = row.get("status")
            if st not in {"NOT_MATERIALIZED", "NO_DEDICATED_SPECIAL_TOPIC_DATASET"}:
                issues.append(
                    self._issue(
                        "cross_cutting_and_optional_boundary",
                        "OPTIONAL_TOPIC_INVALID_STATUS",
                        loc,
                        f"Optional study topic status must indicate non-materialized, got {st!r}.",
                    )
                )
        return issues

    def _validate_vector_legacy_non_double_counting(
        self,
        core_coverage: list[dict[str, Any]],
        lineage: dict[str, Any],
        drift: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
        oxyz = next(
            (
                r
                for r in core_coverage
                if r.get("official_scope_code")
                == "M12_CORE_GEOMETRY_COORDINATE_3D"
            ),
            None,
        )
        if oxyz:
            qdata = oxyz.get("question_data", {})
            legacy_count = qdata.get(
                "legacy_vector_verified_units_not_double_counted"
            )
            if legacy_count != 48:
                issues.append(
                    self._issue(
                        "vector_legacy_non_double_counting",
                        "LEGACY_VECTOR_COUNT_MISMATCH",
                        "core_coverage_audit.json[M12_CORE_GEOMETRY_COORDINATE_3D]",
                        f"Expected legacy_vector_verified_units_not_double_counted=48, got {legacy_count}.",
                    )
                )
            overlap_dec = oxyz.get("legacy_overlap", {}).get("decision")
            if (
                overlap_dec
                != "SUPPLEMENTARY_LEGACY_SUBSET_OF_OXYZ_DO_NOT_COUNT_AS_SEPARATE_OFFICIAL_CHAPTER"
            ):
                issues.append(
                    self._issue(
                        "vector_legacy_non_double_counting",
                        "LEGACY_OVERLAP_DECISION_MISMATCH",
                        "core_coverage_audit.json[M12_CORE_GEOMETRY_COORDINATE_3D]",
                        "Legacy overlap decision mismatch.",
                    )
                )

        double_count_policy = lineage.get("double_counting_policy", {})
        if (
            double_count_policy.get("vector_coordinates_v0_1")
            != "DO_NOT_DOUBLE_COUNT_AGAINST_OXYZ_CORE_COVERAGE"
        ):
            issues.append(
                self._issue(
                    "vector_legacy_non_double_counting",
                    "DOUBLE_COUNTING_POLICY_MISMATCH",
                    "dataset_lineage.json",
                    "vector_coordinates_v0_1 must have policy DO_NOT_DOUBLE_COUNT_AGAINST_OXYZ_CORE_COVERAGE.",
                )
            )

        if contract.get("policy", {}).get("legacy_vector_data_must_not_be_double_counted") is not True:
            issues.append(
                self._issue(
                    "vector_legacy_non_double_counting",
                    "CONTRACT_VECTOR_POLICY_MISMATCH",
                    "data_contract.json",
                    "legacy_vector_data_must_not_be_double_counted must be true.",
                )
            )

        return issues

    def _validate_alignment_candidate_boundary(
        self,
        candidate: dict[str, Any],
        drift: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
        if candidate.get("status") != "PROPOSAL_NOT_CANONICAL":
            issues.append(
                self._issue(
                    "alignment_candidate_boundary",
                    "CANDIDATE_STATUS_NOT_PROPOSAL",
                    "curriculum_alignment_candidate.json",
                    "status must be PROPOSAL_NOT_CANONICAL.",
                )
            )
        if candidate.get("activation_allowed") is not False:
            issues.append(
                self._issue(
                    "alignment_candidate_boundary",
                    "CANDIDATE_ACTIVATION_ALLOWED_VIOLATION",
                    "curriculum_alignment_candidate.json",
                    "activation_allowed must be false.",
                )
            )
        if drift.get("activation_allowed") is not False:
            issues.append(
                self._issue(
                    "alignment_candidate_boundary",
                    "DRIFT_ACTIVATION_ALLOWED_VIOLATION",
                    "curriculum_taxonomy_drift.json",
                    "activation_allowed must be false.",
                )
            )
        policy = contract.get("policy", {})
        if policy.get("audit_must_not_activate_curriculum") is not True:
            issues.append(
                self._issue(
                    "alignment_candidate_boundary",
                    "POLICY_AUDIT_NOT_ACTIVATE_CURRICULUM_VIOLATION",
                    "data_contract.json",
                    "audit_must_not_activate_curriculum must be true.",
                )
            )
        if policy.get("audit_must_not_enable_database_import") is not True:
            issues.append(
                self._issue(
                    "alignment_candidate_boundary",
                    "POLICY_AUDIT_NOT_ENABLE_IMPORT_VIOLATION",
                    "data_contract.json",
                    "audit_must_not_enable_database_import must be true.",
                )
            )

        return issues

    def _validate_release_readiness(
        self,
        readiness: dict[str, Any],
        stats: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
        if readiness.get("production_release_ready") is not False:
            issues.append(
                self._issue(
                    "release_readiness_boundary",
                    "PRODUCTION_RELEASE_READY_VIOLATION",
                    "release_readiness.json",
                    "production_release_ready must be false.",
                )
            )
        if readiness.get("coverage_is_not_release_readiness") is not True:
            issues.append(
                self._issue(
                    "release_readiness_boundary",
                    "COVERAGE_NOT_RELEASE_READINESS_VIOLATION",
                    "release_readiness.json",
                    "coverage_is_not_release_readiness must be true.",
                )
            )
        if stats.get("production_release_ready_core_scopes") != 0:
            issues.append(
                self._issue(
                    "release_readiness_boundary",
                    "PRODUCTION_CORE_SCOPES_NONZERO",
                    "audit_stats.json",
                    "production_release_ready_core_scopes must be 0.",
                )
            )
        if stats.get("production_readiness_status") != "BLOCKED":
            issues.append(
                self._issue(
                    "release_readiness_boundary",
                    "PRODUCTION_READINESS_NOT_BLOCKED",
                    "audit_stats.json",
                    "production_readiness_status must be BLOCKED.",
                )
            )
        if (
            readiness.get("database_import_recommendation")
            != "DO_NOT_IMPORT_NEW_GRADE12_CANONICAL_GRAPH_YET"
        ):
            issues.append(
                self._issue(
                    "release_readiness_boundary",
                    "DB_IMPORT_RECOMMENDATION_MISMATCH",
                    "release_readiness.json",
                    "database_import_recommendation must be DO_NOT_IMPORT_NEW_GRADE12_CANONICAL_GRAPH_YET.",
                )
            )

        return issues

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[FullScopeAuditIssue]:
        issues: list[FullScopeAuditIssue] = []
        pdf_files = list(path.rglob("*.pdf"))
        if pdf_files:
            issues.append(
                self._issue(
                    "no_pdf_binaries",
                    "PDF_BINARY_PRESENT",
                    str(pdf_files[0]),
                    "Raw PDF binaries must not be present in audit directory.",
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
                file_hash = self._semantic_hash(path / name)
                if not file_hash:
                    return None
                digest.update(name.encode("utf-8"))
                digest.update(b"\0")
                digest.update(file_hash.encode("ascii"))
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

    @staticmethod
    def _git_blob_sha1(path: Path) -> str:
        data = path.read_bytes()
        return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()

    def _check_required_files(
        self, path: Path, issues: list[FullScopeAuditIssue]
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
        self, path: Path, issues: list[FullScopeAuditIssue]
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
        self, path: Path, issues: list[FullScopeAuditIssue]
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
    ) -> FullScopeAuditIssue:
        return FullScopeAuditIssue(
            check=check, code=code, location=location, message=message
        )
