from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEPTH_CORRECTION_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "depth_correction_v0_1"
)
BASE_PROBABILITY_DATA_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "conditional_probability_v0_1"
    / "academic_review"
    / "v0_1"
)
BASE_DERIVATIVE_GROUPS_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "derivative_applications_v0_1"
    / "academic_review"
    / "v0_1"
    / "question_groups.json"
)
BASE_OXYZ_DATA_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "oxyz_v0_1"
    / "academic_review"
    / "v0_1"
)

EXPECTED_DEPTH_CORRECTION_AGGREGATE_SHA256 = (
    "171d43f0895e67c02813cc531d04d757cfb3e0ef7f62841392c5a8b4de0c8026"
)
EXPECTED_BASE_REPO_COMMIT = "aed14bf213ac9db65e820984f5a6c46ebabbe304"

SEMANTIC_FILES_ORDER = (
    "probability_hold_promotions.json",
    "derivative_coverage_correction.json",
    "vector_secondary_evidence.json",
    "coverage_effect.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "probability_hold_promotions.json": (
        "5470e020624cb7b9d11d4ac77bfdf86876e78c9d7c8bf75105c23f0d60831a50"
    ),
    "derivative_coverage_correction.json": (
        "c1e100dda7799f3edfd567981ab4037af27232d35681dbedf3957cb1a44e8022"
    ),
    "vector_secondary_evidence.json": (
        "09c8d8e92f37616cf83642fb2dc1f7ac935e176940f014fb4a91cc361d9866a1"
    ),
    "coverage_effect.json": (
        "918e529b8442d91c9a043b92ca1e95366df1fc2fe36a986e83814e4a7b23afe1"
    ),
}

EXPECTED_PROBABILITY_PROMOTIONS = {
    "M12_PROB_CAND_0058": [True, True, False, True],
    "M12_PROB_CAND_0060": [True, False, True, True],
    "M12_PROB_CAND_0061": [True, False, False, False],
    "M12_PROB_CAND_0073": [True, True, False, True],
}

EXPECTED_DERIVATIVE_ZERO_EV = (
    "PARAMETER_MONOTONICITY",
    "PARAMETER_EXTREMA_COUNT",
    "REAL_WORLD_MONOTONICITY_INTERPRETATION",
)

EXPECTED_VECTOR_ZERO_EV = ("VECTOR_COORDINATE_LINEAR_OPERATIONS_3D",)


@dataclass(frozen=True, slots=True, order=True)
class DepthCorrectionIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class DepthCorrectionReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, Any]
    base_repo_commit: str | None
    aggregate_semantic_sha256: str | None
    probability_promotions_count: int
    probability_verified_count_after: int
    derivative_zero_evidence_count: int
    vector_zero_evidence_count: int
    canonical_snapshot_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[DepthCorrectionIssue, ...]

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
            "probability_promotions_count": self.probability_promotions_count,
            "probability_verified_count_after": self.probability_verified_count_after,
            "derivative_zero_evidence_count": self.derivative_zero_evidence_count,
            "vector_zero_evidence_count": self.vector_zero_evidence_count,
            "canonical_snapshot_allowed": self.canonical_snapshot_allowed,
            "database_import_allowed": self.database_import_allowed,
            "production_release_allowed": self.production_release_allowed,
            "errors": [asdict(issue) for issue in self.errors],
        }


class DepthCorrectionOverlay:
    """In-memory overlay helper for applying DATA-039 corrections without mutating base files."""

    @classmethod
    def apply_probability_hold_promotions(
        cls,
        base_candidates: list[dict[str, Any]],
        promotions_path: Path = DEFAULT_DEPTH_CORRECTION_PATH / "probability_hold_promotions.json",
    ) -> list[dict[str, Any]]:
        promotions_data = json.loads(promotions_path.read_text(encoding="utf-8"))
        overlay_map = {r["candidate_id"]: r for r in promotions_data.get("records", [])}

        results = []
        for cand in base_candidates:
            cid = cand.get("candidate_id")
            if cid in overlay_map:
                overlay_info = overlay_map[cid]
                updated = copy.deepcopy(cand)
                updated["review_status"] = overlay_info["review_status_after_overlay"]
                updated["rights_status"] = overlay_info["rights_status"]
                updated["source_solution_checks"] = overlay_info.get("source_solution_checks")
                results.append(updated)
            else:
                results.append(copy.deepcopy(cand))
        return results


class DepthCorrectionOverlayValidator:
    """Validator for DATA-MATH12-039 depth corrections and overlays."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_DEPTH_CORRECTION_PATH,
        *,
        base_probability_path: Path = BASE_PROBABILITY_DATA_PATH,
        base_derivative_groups_path: Path = BASE_DERIVATIVE_GROUPS_PATH,
        base_oxyz_path: Path = BASE_OXYZ_DATA_PATH,
    ) -> DepthCorrectionReport:
        path = dataset_path.resolve()
        initial: list[DepthCorrectionIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        prob_promotions = self._load_object(path / "probability_hold_promotions.json", initial)
        deriv_corr = self._load_object(path / "derivative_coverage_correction.json", initial)
        vector_sec = self._load_object(path / "vector_secondary_evidence.json", initial)
        coverage_eff = self._load_object(path / "coverage_effect.json", initial)

        checks_to_errors: dict[str, list[DepthCorrectionIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "probability_overlay": self._validate_probability_overlay(
                prob_promotions, base_probability_path
            ),
            "derivative_correction": self._validate_derivative_correction(
                deriv_corr, base_derivative_groups_path
            ),
            "vector_secondary_evidence": self._validate_vector_secondary(
                vector_sec, base_oxyz_path
            ),
            "coverage_effect_consistency": self._validate_coverage_effect(
                coverage_eff, prob_promotions, deriv_corr, vector_sec
            ),
            "critical_boundaries": self._validate_critical_boundaries(
                contract, coverage_eff
            ),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[DepthCorrectionIssue] = []
        if aggregate != EXPECTED_DEPTH_CORRECTION_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_DEPTH_CORRECTION_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_DEPTH_CORRECTION_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-039 aggregate.",
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

        promoted_count = len(prob_promotions.get("records", []))
        prob_after_count = prob_promotions.get("verified_candidates_after_overlay", 0)
        deriv_zero_count = len(deriv_corr.get("zero_evidence_problem_types_after_secondary_mapping", []))
        vec_zero_count = len(vector_sec.get("remaining_zero_evidence_vector_problem_types_after_overlay", []))

        counts = {
            "probability_promoted_records": promoted_count,
            "probability_verified_after": prob_after_count,
            "derivative_zero_evidence_after": deriv_zero_count,
            "vector_zero_evidence_after": vec_zero_count,
        }

        return DepthCorrectionReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            aggregate_semantic_sha256=aggregate,
            probability_promotions_count=promoted_count,
            probability_verified_count_after=prob_after_count,
            derivative_zero_evidence_count=deriv_zero_count,
            vector_zero_evidence_count=vec_zero_count,
            canonical_snapshot_allowed=bool(
                coverage_eff.get("canonical_snapshot_allowed", True)
            ),
            database_import_allowed=bool(
                contract.get("database_import_allowed", True)
            ),
            production_release_allowed=bool(
                contract.get("production_release_allowed", True)
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[DepthCorrectionIssue]
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
    ) -> list[DepthCorrectionIssue]:
        issues: list[DepthCorrectionIssue] = []
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
    ) -> list[DepthCorrectionIssue]:
        issues: list[DepthCorrectionIssue] = []
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
    ) -> list[DepthCorrectionIssue]:
        issues: list[DepthCorrectionIssue] = []
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

    def _validate_probability_overlay(
        self, prob_data: dict[str, Any], base_prob_dir: Path
    ) -> list[DepthCorrectionIssue]:
        issues: list[DepthCorrectionIssue] = []
        records = prob_data.get("records", [])

        if len(records) != 4:
            issues.append(
                self._issue(
                    "probability_overlay",
                    "PROMOTION_COUNT_MISMATCH",
                    "probability_hold_promotions.json",
                    f"Expected exactly 4 promoted records, got {len(records)}.",
                )
            )

        promoted_ids = set()
        for rec in records:
            cid = rec.get("candidate_id")
            promoted_ids.add(cid)
            if cid not in EXPECTED_PROBABILITY_PROMOTIONS:
                issues.append(
                    self._issue(
                        "probability_overlay",
                        "UNEXPECTED_CANDIDATE_ID",
                        f"probability_hold_promotions.json[{cid}]",
                        f"Unexpected candidate ID {cid} in probability hold promotions.",
                    )
                )
                continue
            expected_ans = EXPECTED_PROBABILITY_PROMOTIONS[cid]
            if rec.get("correct_answer") != expected_ans:
                issues.append(
                    self._issue(
                        "probability_overlay",
                        "ANSWER_MISMATCH",
                        f"probability_hold_promotions.json[{cid}]",
                        f"Answer mismatch for {cid}: expected {expected_ans}, got {rec.get('correct_answer')}.",
                    )
                )
            if rec.get("review_status_after_overlay") != "VERIFIED_SOURCE_ANSWER":
                issues.append(
                    self._issue(
                        "probability_overlay",
                        "INVALID_REVIEW_STATUS",
                        f"probability_hold_promotions.json[{cid}]",
                        "review_status_after_overlay must be VERIFIED_SOURCE_ANSWER.",
                    )
                )
            if rec.get("rights_status") != "REVIEW_REQUIRED":
                issues.append(
                    self._issue(
                        "probability_overlay",
                        "INVALID_RIGHTS_STATUS",
                        f"probability_hold_promotions.json[{cid}]",
                        "rights_status must be REVIEW_REQUIRED.",
                    )
                )

        if promoted_ids != set(EXPECTED_PROBABILITY_PROMOTIONS.keys()):
            issues.append(
                self._issue(
                    "probability_overlay",
                    "PROMOTED_SET_MISMATCH",
                    "probability_hold_promotions.json",
                    f"Expected promoted IDs {set(EXPECTED_PROBABILITY_PROMOTIONS.keys())}, got {promoted_ids}.",
                )
            )

        # Verify against base dataset DATA-025 if present
        base_review_file = base_prob_dir / "candidate_reviews.json"
        if base_review_file.is_file():
            try:
                base_cands = json.loads(base_review_file.read_text(encoding="utf-8"))
                base_map = {c["candidate_id"]: c for c in base_cands if isinstance(c, dict)}
                for cid in EXPECTED_PROBABILITY_PROMOTIONS:
                    base_cand = base_map.get(cid)
                    if not base_cand:
                        issues.append(
                            self._issue(
                                "probability_overlay",
                                "BASE_CANDIDATE_NOT_FOUND",
                                cid,
                                f"Candidate {cid} not found in base DATA-025 dataset.",
                            )
                        )
                    elif base_cand.get("review_status") != "HOLD_CANONICAL_SOURCE_ANSWER_REQUIRED":
                        issues.append(
                            self._issue(
                                "probability_overlay",
                                "BASE_CANDIDATE_NOT_HOLD",
                                cid,
                                f"Candidate {cid} in base DATA-025 must have status HOLD_CANONICAL_SOURCE_ANSWER_REQUIRED, got {base_cand.get('review_status')}.",
                            )
                        )
            except Exception as e:
                issues.append(
                    self._issue(
                        "probability_overlay",
                        "BASE_PROBABILITY_READ_ERROR",
                        "candidate_reviews.json",
                        f"Error reading base probability reviews: {e}",
                    )
                )

        # Verify counts in probability_hold_promotions.json
        if prob_data.get("base_verified_candidates") != 17:
            issues.append(
                self._issue(
                    "probability_overlay",
                    "BASE_VERIFIED_COUNT_MISMATCH",
                    "probability_hold_promotions.json",
                    f"Expected base_verified_candidates 17, got {prob_data.get('base_verified_candidates')}.",
                )
            )
        if prob_data.get("verified_candidates_after_overlay") != 21:
            issues.append(
                self._issue(
                    "probability_overlay",
                    "AFTER_VERIFIED_COUNT_MISMATCH",
                    "probability_hold_promotions.json",
                    f"Expected verified_candidates_after_overlay 21, got {prob_data.get('verified_candidates_after_overlay')}.",
                )
            )
        pt_counts = prob_data.get("verified_problem_type_counts_after_overlay", {})
        expected_pt_counts = {
            "BAYES_POSTERIOR": 14,
            "CONDITIONAL_PROBABILITY_DIRECT": 5,
            "TREE_OR_TOTAL_PROBABILITY": 2,
        }
        if pt_counts != expected_pt_counts:
            issues.append(
                self._issue(
                    "probability_overlay",
                    "PT_COUNTS_MISMATCH",
                    "probability_hold_promotions.json",
                    f"Expected PT counts {expected_pt_counts}, got {pt_counts}.",
                )
            )

        return issues

    def _validate_derivative_correction(
        self, deriv_data: dict[str, Any], base_groups_path: Path
    ) -> list[DepthCorrectionIssue]:
        issues: list[DepthCorrectionIssue] = []

        # Stale gap entries now source backed
        stale_entries = deriv_data.get("stale_gap_entries_now_source_backed", [])
        expected_stale = {
            "GLOBAL_EXTREMA_SIMPLE_DOMAIN": 14,
            "COMPLETE_FUNCTION_ANALYSIS_LINEAR_FRACTION": 5,
            "COMPLETE_FUNCTION_ANALYSIS_QUADRATIC_OVER_LINEAR": 3,
        }
        actual_stale = {
            e.get("problem_type_code"): e.get("verified_evidence_units")
            for e in stale_entries
            if isinstance(e, dict)
        }
        if actual_stale != expected_stale:
            issues.append(
                self._issue(
                    "derivative_correction",
                    "STALE_GAP_ENTRIES_MISMATCH",
                    "derivative_coverage_correction.json",
                    f"Expected stale entries {expected_stale}, got {actual_stale}.",
                )
            )

        # Secondary group mapping
        sec_groups = deriv_data.get("secondary_group_level_evidence", [])
        if len(sec_groups) != 1:
            issues.append(
                self._issue(
                    "derivative_correction",
                    "SECONDARY_GROUPS_COUNT_MISMATCH",
                    "derivative_coverage_correction.json",
                    f"Expected 1 secondary group mapping, got {len(sec_groups)}.",
                )
            )
        else:
            sg = sec_groups[0]
            if sg.get("problem_type_code") != "COMPLETE_FUNCTION_ANALYSIS_CUBIC":
                issues.append(
                    self._issue(
                        "derivative_correction",
                        "SECONDARY_GROUP_PT_MISMATCH",
                        "derivative_coverage_correction.json",
                        f"Expected problem_type_code COMPLETE_FUNCTION_ANALYSIS_CUBIC, got {sg.get('problem_type_code')}.",
                    )
                )
            if sg.get("source_group_id") != "M12_DERIV_GROUP_0136":
                issues.append(
                    self._issue(
                        "derivative_correction",
                        "SECONDARY_GROUP_ID_MISMATCH",
                        "derivative_coverage_correction.json",
                        f"Expected source_group_id M12_DERIV_GROUP_0136, got {sg.get('source_group_id')}.",
                    )
                )

        # Check secondary group exists in base derivative question_groups.json
        if base_groups_path.is_file():
            try:
                groups_content = json.loads(base_groups_path.read_text(encoding="utf-8"))
                group_ids = {g.get("group_id") for g in groups_content if isinstance(g, dict)}
                if "M12_DERIV_GROUP_0136" not in group_ids:
                    issues.append(
                        self._issue(
                            "derivative_correction",
                            "GROUP_NOT_FOUND_IN_BASE",
                            "M12_DERIV_GROUP_0136",
                            "Group M12_DERIV_GROUP_0136 not found in base question_groups.json.",
                        )
                    )
            except Exception as e:
                issues.append(
                    self._issue(
                        "derivative_correction",
                        "BASE_GROUPS_READ_ERROR",
                        "question_groups.json",
                        f"Error reading base question groups: {e}",
                    )
                )

        # Zero evidence after secondary mapping
        zero_ev = tuple(deriv_data.get("zero_evidence_problem_types_after_secondary_mapping", []))
        if zero_ev != EXPECTED_DERIVATIVE_ZERO_EV:
            issues.append(
                self._issue(
                    "derivative_correction",
                    "ZERO_EVIDENCE_PT_MISMATCH",
                    "derivative_coverage_correction.json",
                    f"Expected zero evidence PTs {EXPECTED_DERIVATIVE_ZERO_EV}, got {zero_ev}.",
                )
            )

        return issues

    def _validate_vector_secondary(
        self, vector_data: dict[str, Any], base_oxyz_dir: Path
    ) -> list[DepthCorrectionIssue]:
        issues: list[DepthCorrectionIssue] = []
        records = vector_data.get("records", [])

        if len(records) != 3:
            issues.append(
                self._issue(
                    "vector_secondary_evidence",
                    "VECTOR_RECORDS_COUNT_MISMATCH",
                    "vector_secondary_evidence.json",
                    f"Expected 3 vector secondary evidence records, got {len(records)}.",
                )
            )

        expected_targets = {
            "POINT_COORDINATES_3D",
            "PARAMETER_VECTOR_COORDINATE_CONDITION_3D",
            "VECTOR_COORDINATE_ANGLE_3D",
        }
        actual_targets = {r.get("target_problem_type_code") for r in records if isinstance(r, dict)}
        if actual_targets != expected_targets:
            issues.append(
                self._issue(
                    "vector_secondary_evidence",
                    "TARGET_PT_MISMATCH",
                    "vector_secondary_evidence.json",
                    f"Expected target problem types {expected_targets}, got {actual_targets}.",
                )
            )

        remaining_zero = tuple(
            vector_data.get("remaining_zero_evidence_vector_problem_types_after_overlay", [])
        )
        if remaining_zero != EXPECTED_VECTOR_ZERO_EV:
            issues.append(
                self._issue(
                    "vector_secondary_evidence",
                    "REMAINING_ZERO_VECTOR_PT_MISMATCH",
                    "vector_secondary_evidence.json",
                    f"Expected remaining zero vector PTs {EXPECTED_VECTOR_ZERO_EV}, got {remaining_zero}.",
                )
            )

        return issues

    def _validate_coverage_effect(
        self,
        coverage_eff: dict[str, Any],
        prob_data: dict[str, Any],
        deriv_data: dict[str, Any],
        vector_data: dict[str, Any],
    ) -> list[DepthCorrectionIssue]:
        issues: list[DepthCorrectionIssue] = []

        prob_eff = coverage_eff.get("probability", {})
        if prob_eff.get("verified_practice_question_units_before") != 17:
            issues.append(
                self._issue(
                    "coverage_effect_consistency",
                    "PROB_BEFORE_MISMATCH",
                    "coverage_effect.json",
                    "probability verified_practice_question_units_before must be 17.",
                )
            )
        if prob_eff.get("verified_practice_question_units_after") != 21:
            issues.append(
                self._issue(
                    "coverage_effect_consistency",
                    "PROB_AFTER_MISMATCH",
                    "coverage_effect.json",
                    "probability verified_practice_question_units_after must be 21.",
                )
            )
        if prob_eff.get("conditional_direct_before") != 1:
            issues.append(
                self._issue(
                    "coverage_effect_consistency",
                    "PROB_DIRECT_BEFORE_MISMATCH",
                    "coverage_effect.json",
                    "conditional_direct_before must be 1.",
                )
            )
        if prob_eff.get("conditional_direct_after") != 5:
            issues.append(
                self._issue(
                    "coverage_effect_consistency",
                    "PROB_DIRECT_AFTER_MISMATCH",
                    "coverage_effect.json",
                    "conditional_direct_after must be 5.",
                )
            )
        if prob_eff.get("source_families_before") != 1:
            issues.append(
                self._issue(
                    "coverage_effect_consistency",
                    "PROB_FAMILIES_BEFORE_MISMATCH",
                    "coverage_effect.json",
                    "source_families_before must be 1.",
                )
            )
        if prob_eff.get("source_families_after") != 3:
            issues.append(
                self._issue(
                    "coverage_effect_consistency",
                    "PROB_FAMILIES_AFTER_MISMATCH",
                    "coverage_effect.json",
                    "source_families_after must be 3.",
                )
            )

        deriv_eff = coverage_eff.get("derivative", {})
        if tuple(deriv_eff.get("remaining", [])) != EXPECTED_DERIVATIVE_ZERO_EV:
            issues.append(
                self._issue(
                    "coverage_effect_consistency",
                    "DERIV_REMAINING_MISMATCH",
                    "coverage_effect.json",
                    f"derivative remaining must be {EXPECTED_DERIVATIVE_ZERO_EV}.",
                )
            )

        vec_eff = coverage_eff.get("vector_legacy_subscope", {})
        if tuple(vec_eff.get("remaining", [])) != EXPECTED_VECTOR_ZERO_EV:
            issues.append(
                self._issue(
                    "coverage_effect_consistency",
                    "VEC_REMAINING_MISMATCH",
                    "coverage_effect.json",
                    f"vector remaining must be {EXPECTED_VECTOR_ZERO_EV}.",
                )
            )

        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], coverage_eff: dict[str, Any]
    ) -> list[DepthCorrectionIssue]:
        issues: list[DepthCorrectionIssue] = []

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
        if coverage_eff.get("canonical_snapshot_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "CANONICAL_SNAPSHOT_NOT_BLOCKED",
                    "coverage_effect.json",
                    "canonical_snapshot_allowed must be false.",
                )
            )
        if coverage_eff.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "COVERAGE_DB_IMPORT_NOT_BLOCKED",
                    "coverage_effect.json",
                    "database_import_allowed must be false in coverage_effect.",
                )
            )
        if coverage_eff.get("rights_status") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "RIGHTS_STATUS_NOT_REVIEW_REQUIRED",
                    "coverage_effect.json",
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
        self, path: Path, issues: list[DepthCorrectionIssue]
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
    ) -> DepthCorrectionIssue:
        return DepthCorrectionIssue(
            check=check, code=code, location=location, message=message
        )
