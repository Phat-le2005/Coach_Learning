from __future__ import annotations

import copy
import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "local_depth_supplement_v0_1"
)

EXPECTED_LOCAL_DEPTH_SUPPLEMENT_AGGREGATE_SHA256 = (
    "b9af124476df49204467fc070c3b72da4c0628656fe151e197db2631a20572c9"
)
EXPECTED_BASE_REPO_COMMIT = "30bb2625128fa38a71fbbc8481e8589672027632"
EXPECTED_BASE_DEPTH_AGGREGATE_SHA256 = (
    "171d43f0895e67c02813cc531d04d757cfb3e0ef7f62841392c5a8b4de0c8026"
)

SEMANTIC_FILES_ORDER = (
    "source_registry.json",
    "verified_units.json",
    "asset_manifest.json",
    "coverage_after_043.json",
)
REQUIRED_FILES = (
    *SEMANTIC_FILES_ORDER,
    "data_contract.json",
    "README.md",
    "assets/M12_PROB_TREE_TRIAL_2026_13.png",
)

EXPECTED_SEMANTIC_HASHES = {
    "source_registry.json": (
        "c892146465af1ec5884ab8f24c6c0d863199a69be6d612fad9ad83a228b911bc"
    ),
    "verified_units.json": (
        "0546f4ae54b13345e8a0fd3dea77b2c417db6e797608ea2f5588f39861613811"
    ),
    "asset_manifest.json": (
        "0cdb91d733e2ee82ce0fe240310cbfb3e4647441ce1d0bb6c611680eb6b8cb76"
    ),
    "coverage_after_043.json": (
        "8eafc8b7b9f3ea620991e73f02023a5878eeef958a3f8452b7e7a2b6627f2062"
    ),
}

EXPECTED_SOURCES = {
    "SRC_TRIAL_2026_01": "889adfeb2a8c5e4f2c7b8cb95ca3f8809cd94f81ed2bb9a9ff8a737c5975febb",
    "SRC_TRIAL_2026_04": "89202f9711bafd51c83d41f3a1203da798325be16f25fbd02f80578c48c1719f",
    "SRC_TRIAL_2026_13": "6ab24e60dd44ed7bff543eb4c5b60a96e6650242c5709a1aca641b9ea59be396",
    "SRC_TRIAL_2026_14": "7330415051643b8ded8b26e29f1cb4cfe3dc85fc025e3ed8a5294205b60e9e8d",
}

EXPECTED_PNG_ASSET_SHA256 = (
    "5d28aef2bea0c3acdfa23b920eff7b9f05d6260acc2f02471b0a528c3c4b502e"
)
EXPECTED_PNG_WIDTH = 820
EXPECTED_PNG_HEIGHT = 580
EXPECTED_CROP_BOX = [300, 40, 1120, 620]
EXPECTED_RENDERED_PAGE_DIMENSIONS = [1489, 2105]

EXPECTED_DERIVATIVE_REMAINING_ZERO = ("PARAMETER_MONOTONICITY",)
EXPECTED_VECTOR_REMAINING_ZERO: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, order=True)
class LocalDepthSupplementIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class LocalDepthSupplementReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, Any]
    base_repo_commit: str | None
    aggregate_semantic_sha256: str | None
    derivative_remaining_zero: tuple[str, ...]
    vector_remaining_zero: tuple[str, ...]
    probability_practice_units_after: int
    probability_source_families_after: int
    rights_status: str
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[LocalDepthSupplementIssue, ...]

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
            "derivative_remaining_zero": list(self.derivative_remaining_zero),
            "vector_remaining_zero": list(self.vector_remaining_zero),
            "probability_practice_units_after": self.probability_practice_units_after,
            "probability_source_families_after": self.probability_source_families_after,
            "rights_status": self.rights_status,
            "canonical_write_allowed": self.canonical_write_allowed,
            "database_import_allowed": self.database_import_allowed,
            "production_release_allowed": self.production_release_allowed,
            "errors": [asdict(issue) for issue in self.errors],
        }


class LocalDepthSupplementOverlay:
    """In-memory overlay helper for applying DATA-043 supplements without mutating base datasets."""

    @classmethod
    def get_supplemental_units(
        cls,
        supplement_path: Path = DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH,
    ) -> list[dict[str, Any]]:
        units_file = supplement_path / "verified_units.json"
        data = json.loads(units_file.read_text(encoding="utf-8"))
        return copy.deepcopy(data.get("units", []))


class LocalDepthSupplementValidator:
    """Validator for DATA-MATH12-043 local pinned real-source depth supplement."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH,
    ) -> LocalDepthSupplementReport:
        path = dataset_path.resolve()
        initial: list[LocalDepthSupplementIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        source_reg = self._load_object(path / "source_registry.json", initial)
        units_data = self._load_object(path / "verified_units.json", initial)
        asset_man = self._load_object(path / "asset_manifest.json", initial)
        cov_data = self._load_object(path / "coverage_after_043.json", initial)

        checks_to_errors: dict[str, list[LocalDepthSupplementIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "source_registry_integrity": self._validate_source_registry(source_reg),
            "verified_units_integrity": self._validate_verified_units(units_data),
            "asset_manifest_integrity": self._validate_asset_manifest(asset_man, path),
            "coverage_effects_integrity": self._validate_coverage_effects(cov_data),
            "critical_boundaries": self._validate_critical_boundaries(contract, cov_data),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[LocalDepthSupplementIssue] = []
        if aggregate != EXPECTED_LOCAL_DEPTH_SUPPLEMENT_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_LOCAL_DEPTH_SUPPLEMENT_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_LOCAL_DEPTH_SUPPLEMENT_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-043 aggregate.",
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

        units_list = units_data.get("units", [])
        effects = cov_data.get("effects", {})
        deriv_rem = tuple(effects.get("derivative_remaining_zero_evidence", []))
        vec_rem = tuple(effects.get("vector_legacy_remaining_zero_evidence", []))

        counts = {
            "verified_units_count": len(units_list),
            "sources_count": len(source_reg.get("sources", [])),
            "assets_count": len(asset_man.get("assets", [])),
        }

        return LocalDepthSupplementReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            aggregate_semantic_sha256=aggregate,
            derivative_remaining_zero=deriv_rem,
            vector_remaining_zero=vec_rem,
            probability_practice_units_after=effects.get(
                "probability_practice_units_after", 0
            ),
            probability_source_families_after=effects.get(
                "probability_source_families_after", 0
            ),
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
        self, path: Path, issues: list[LocalDepthSupplementIssue]
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
    ) -> list[LocalDepthSupplementIssue]:
        issues: list[LocalDepthSupplementIssue] = []
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
    ) -> list[LocalDepthSupplementIssue]:
        issues: list[LocalDepthSupplementIssue] = []
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
    ) -> list[LocalDepthSupplementIssue]:
        issues: list[LocalDepthSupplementIssue] = []
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

    def _validate_source_registry(
        self, source_reg: dict[str, Any]
    ) -> list[LocalDepthSupplementIssue]:
        issues: list[LocalDepthSupplementIssue] = []
        sources = source_reg.get("sources", [])
        if len(sources) != 4:
            issues.append(
                self._issue(
                    "source_registry_integrity",
                    "SOURCES_COUNT_MISMATCH",
                    "source_registry.json",
                    f"Expected exactly 4 sources, got {len(sources)}.",
                )
            )

        policy = source_reg.get("policy", {})
        if policy.get("synthetic_question_generation") is not False:
            issues.append(
                self._issue(
                    "source_registry_integrity",
                    "SYNTHETIC_GENERATION_NOT_BLOCKED",
                    "source_registry.json",
                    "synthetic_question_generation must be false.",
                )
            )
        if policy.get("real_sources_only") is not True:
            issues.append(
                self._issue(
                    "source_registry_integrity",
                    "REAL_SOURCES_ONLY_NOT_TRUE",
                    "source_registry.json",
                    "real_sources_only must be true.",
                )
            )

        found_codes = {}
        for s in sources:
            code = s.get("source_code")
            sha = s.get("sha256")
            found_codes[code] = sha
            if code in EXPECTED_SOURCES:
                if sha != EXPECTED_SOURCES[code]:
                    issues.append(
                        self._issue(
                            "source_registry_integrity",
                            "SOURCE_SHA_MISMATCH",
                            f"source_registry.json[{code}]",
                            f"Source {code} expected sha {EXPECTED_SOURCES[code]}, got {sha}.",
                        )
                    )
            else:
                issues.append(
                    self._issue(
                        "source_registry_integrity",
                        "UNKNOWN_SOURCE_CODE",
                        f"source_registry.json[{code}]",
                        f"Unknown source code: {code}.",
                    )
                )

        if set(found_codes.keys()) != set(EXPECTED_SOURCES.keys()):
            issues.append(
                self._issue(
                    "source_registry_integrity",
                    "SOURCES_SET_MISMATCH",
                    "source_registry.json",
                    f"Expected sources {set(EXPECTED_SOURCES.keys())}, got {set(found_codes.keys())}.",
                )
            )

        return issues

    def _validate_verified_units(
        self, units_data: dict[str, Any]
    ) -> list[LocalDepthSupplementIssue]:
        issues: list[LocalDepthSupplementIssue] = []
        units = units_data.get("units", [])
        if len(units) != 4:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "UNITS_COUNT_MISMATCH",
                    "verified_units.json",
                    f"Expected 4 verified units, got {len(units)}.",
                )
            )

        unit_map = {u.get("unit_id"): u for u in units if isinstance(u, dict)}

        # Unit 1: M12_D043_DERIV_PARAM_EXTREMA_001
        u1 = unit_map.get("M12_D043_DERIV_PARAM_EXTREMA_001")
        if not u1:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT_1",
                    "verified_units.json",
                    "Missing unit M12_D043_DERIV_PARAM_EXTREMA_001.",
                )
            )
        else:
            if u1.get("problem_type_code") != "PARAMETER_EXTREMA_COUNT":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_1_PT_MISMATCH",
                        "M12_D043_DERIV_PARAM_EXTREMA_001",
                        "Unit 1 problem_type_code must be PARAMETER_EXTREMA_COUNT.",
                    )
                )
            if u1.get("correct_answer") != "2":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_1_ANSWER_MISMATCH",
                        "M12_D043_DERIV_PARAM_EXTREMA_001",
                        f"Unit 1 correct_answer must be '2', got {u1.get('correct_answer')!r}.",
                    )
                )
            if u1.get("source_code") != "SRC_TRIAL_2026_01":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_1_SOURCE_MISMATCH",
                        "M12_D043_DERIV_PARAM_EXTREMA_001",
                        "Unit 1 source_code must be SRC_TRIAL_2026_01.",
                    )
                )
            if u1.get("question_page_1_based") != 5 or u1.get("solution_page_1_based") != 20:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_1_PAGES_MISMATCH",
                        "M12_D043_DERIV_PARAM_EXTREMA_001",
                        "Unit 1 pages must be question: 5, solution: 20.",
                    )
                )
            if u1.get("visual_required") is not False:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_1_VISUAL_NOT_FALSE",
                        "M12_D043_DERIV_PARAM_EXTREMA_001",
                        "Unit 1 visual_required must be false.",
                    )
                )

        # Unit 2: M12_D043_DERIV_REALWORLD_MONO_GROUP_001
        u2 = unit_map.get("M12_D043_DERIV_REALWORLD_MONO_GROUP_001")
        if not u2:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT_2",
                    "verified_units.json",
                    "Missing unit M12_D043_DERIV_REALWORLD_MONO_GROUP_001.",
                )
            )
        else:
            if u2.get("problem_type_code") != "REAL_WORLD_MONOTONICITY_INTERPRETATION":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_2_PT_MISMATCH",
                        "M12_D043_DERIV_REALWORLD_MONO_GROUP_001",
                        "Unit 2 problem_type_code must be REAL_WORLD_MONOTONICITY_INTERPRETATION.",
                    )
                )
            if u2.get("source_code") != "SRC_TRIAL_2026_04":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_2_SOURCE_MISMATCH",
                        "M12_D043_DERIV_REALWORLD_MONO_GROUP_001",
                        "Unit 2 source_code must be SRC_TRIAL_2026_04.",
                    )
                )
            if u2.get("question_page_1_based") != 3 or u2.get("solution_pages_1_based") != [11, 12]:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_2_PAGES_MISMATCH",
                        "M12_D043_DERIV_REALWORLD_MONO_GROUP_001",
                        "Unit 2 pages must be question: 3, solution: [11, 12].",
                    )
                )
            children = u2.get("source_children", [])
            pattern = [c.get("correct_answer") for c in children]
            if pattern != [True, False, True, False]:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_2_TF_PATTERN_MISMATCH",
                        "M12_D043_DERIV_REALWORLD_MONO_GROUP_001",
                        f"Unit 2 T/F pattern must be [True, False, True, False], got {pattern}.",
                    )
                )
            if u2.get("atomic_group_policy") is not True:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_2_NOT_ATOMIC_GROUP",
                        "M12_D043_DERIV_REALWORLD_MONO_GROUP_001",
                        "Unit 2 atomic_group_policy must be true.",
                    )
                )

        # Unit 3: M12_D043_VECTOR_LINEAROPS_001
        u3 = unit_map.get("M12_D043_VECTOR_LINEAROPS_001")
        if not u3:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT_3",
                    "verified_units.json",
                    "Missing unit M12_D043_VECTOR_LINEAROPS_001.",
                )
            )
        else:
            if u3.get("problem_type_code") != "VECTOR_COORDINATE_LINEAR_OPERATIONS_3D":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_3_PT_MISMATCH",
                        "M12_D043_VECTOR_LINEAROPS_001",
                        "Unit 3 problem_type_code must be VECTOR_COORDINATE_LINEAR_OPERATIONS_3D.",
                    )
                )
            if u3.get("correct_answer") != "D":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_3_ANSWER_MISMATCH",
                        "M12_D043_VECTOR_LINEAROPS_001",
                        f"Unit 3 correct_answer must be 'D', got {u3.get('correct_answer')!r}.",
                    )
                )
            if u3.get("correct_answer_value") != "√74":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_3_ANSWER_VALUE_MISMATCH",
                        "M12_D043_VECTOR_LINEAROPS_001",
                        f"Unit 3 correct_answer_value must be '√74', got {u3.get('correct_answer_value')!r}.",
                    )
                )
            if u3.get("source_code") != "SRC_TRIAL_2026_14":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_3_SOURCE_MISMATCH",
                        "M12_D043_VECTOR_LINEAROPS_001",
                        "Unit 3 source_code must be SRC_TRIAL_2026_14.",
                    )
                )
            if u3.get("question_page_1_based") != 2 or u3.get("solution_page_1_based") != 8:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_3_PAGES_MISMATCH",
                        "M12_D043_VECTOR_LINEAROPS_001",
                        "Unit 3 pages must be question: 2, solution: 8.",
                    )
                )

        # Unit 4: M12_D043_PROB_TREE_001
        u4 = unit_map.get("M12_D043_PROB_TREE_001")
        if not u4:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT_4",
                    "verified_units.json",
                    "Missing unit M12_D043_PROB_TREE_001.",
                )
            )
        else:
            if u4.get("problem_type_code") != "TREE_OR_TOTAL_PROBABILITY":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_4_PT_MISMATCH",
                        "M12_D043_PROB_TREE_001",
                        "Unit 4 problem_type_code must be TREE_OR_TOTAL_PROBABILITY.",
                    )
                )
            if u4.get("correct_answer") != "0.76":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_4_ANSWER_MISMATCH",
                        "M12_D043_PROB_TREE_001",
                        f"Unit 4 correct_answer must be '0.76', got {u4.get('correct_answer')!r}.",
                    )
                )
            if u4.get("source_code") != "SRC_TRIAL_2026_13":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_4_SOURCE_MISMATCH",
                        "M12_D043_PROB_TREE_001",
                        "Unit 4 source_code must be SRC_TRIAL_2026_13.",
                    )
                )
            if u4.get("question_page_1_based") != 5 or u4.get("solution_pages_1_based") != [18, 19]:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_4_PAGES_MISMATCH",
                        "M12_D043_PROB_TREE_001",
                        "Unit 4 pages must be question: 5, solution: [18, 19].",
                    )
                )
            sec_ev = u4.get("secondary_problem_type_evidence", [])
            if "CONDITIONAL_PROBABILITY_DIRECT" not in sec_ev or "TOTAL_PROBABILITY" not in sec_ev:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "UNIT_4_SECONDARY_EVIDENCE_MISMATCH",
                        "M12_D043_PROB_TREE_001",
                        "Unit 4 secondary evidence must include CONDITIONAL_PROBABILITY_DIRECT and TOTAL_PROBABILITY.",
                    )
                )

        return issues

    def _validate_asset_manifest(
        self, asset_man: dict[str, Any], path: Path
    ) -> list[LocalDepthSupplementIssue]:
        issues: list[LocalDepthSupplementIssue] = []
        if asset_man.get("synthetic_visuals") is not False:
            issues.append(
                self._issue(
                    "asset_manifest_integrity",
                    "SYNTHETIC_VISUALS_NOT_FALSE",
                    "asset_manifest.json",
                    "synthetic_visuals must be false.",
                )
            )

        assets = asset_man.get("assets", [])
        if len(assets) != 1:
            issues.append(
                self._issue(
                    "asset_manifest_integrity",
                    "ASSETS_COUNT_MISMATCH",
                    "asset_manifest.json",
                    f"Expected 1 asset, got {len(assets)}.",
                )
            )
            return issues

        a = assets[0]
        if a.get("asset_id") != "M12_D043_PROB_TREE_ASSET_001":
            issues.append(
                self._issue(
                    "asset_manifest_integrity",
                    "ASSET_ID_MISMATCH",
                    "asset_manifest.json",
                    "Asset id must be M12_D043_PROB_TREE_ASSET_001.",
                )
            )
        if a.get("sha256") != EXPECTED_PNG_ASSET_SHA256:
            issues.append(
                self._issue(
                    "asset_manifest_integrity",
                    "ASSET_MANIFEST_SHA_MISMATCH",
                    "asset_manifest.json",
                    f"Expected asset sha {EXPECTED_PNG_ASSET_SHA256}, got {a.get('sha256')}.",
                )
            )
        if a.get("width") != EXPECTED_PNG_WIDTH or a.get("height") != EXPECTED_PNG_HEIGHT:
            issues.append(
                self._issue(
                    "asset_manifest_integrity",
                    "ASSET_MANIFEST_DIMENSIONS_MISMATCH",
                    "asset_manifest.json",
                    f"Expected dimensions {EXPECTED_PNG_WIDTH}x{EXPECTED_PNG_HEIGHT}, got {a.get('width')}x{a.get('height')}.",
                )
            )
        if a.get("crop_box_pixels") != EXPECTED_CROP_BOX:
            issues.append(
                self._issue(
                    "asset_manifest_integrity",
                    "CROP_BOX_MISMATCH",
                    "asset_manifest.json",
                    f"Expected crop box {EXPECTED_CROP_BOX}, got {a.get('crop_box_pixels')}.",
                )
            )
        if a.get("rendered_source_page_dimensions") != EXPECTED_RENDERED_PAGE_DIMENSIONS:
            issues.append(
                self._issue(
                    "asset_manifest_integrity",
                    "RENDERED_PAGE_DIMENSIONS_MISMATCH",
                    "asset_manifest.json",
                    f"Expected rendered page dimensions {EXPECTED_RENDERED_PAGE_DIMENSIONS}, got {a.get('rendered_source_page_dimensions')}.",
                )
            )
        if a.get("extraction_method") != "SOURCE_PDF_RENDER_CROP_NO_REDRAW":
            issues.append(
                self._issue(
                    "asset_manifest_integrity",
                    "EXTRACTION_METHOD_MISMATCH",
                    "asset_manifest.json",
                    "Extraction method must be SOURCE_PDF_RENDER_CROP_NO_REDRAW.",
                )
            )

        # Check binary file bytes on disk
        png_path = path / "assets" / "M12_PROB_TREE_TRIAL_2026_13.png"
        if not png_path.is_file():
            issues.append(
                self._issue(
                    "asset_manifest_integrity",
                    "PNG_FILE_NOT_FOUND",
                    "assets/M12_PROB_TREE_TRIAL_2026_13.png",
                    "PNG asset file not found.",
                )
            )
        else:
            data = png_path.read_bytes()
            actual_sha = hashlib.sha256(data).hexdigest()
            if actual_sha != EXPECTED_PNG_ASSET_SHA256:
                issues.append(
                    self._issue(
                        "asset_manifest_integrity",
                        "PNG_BYTES_SHA_MISMATCH",
                        "assets/M12_PROB_TREE_TRIAL_2026_13.png",
                        f"Actual PNG bytes sha {actual_sha} does not match expected {EXPECTED_PNG_ASSET_SHA256}.",
                    )
                )
            if len(data) >= 24:
                w, h = struct.unpack(">II", data[16:24])
                if w != EXPECTED_PNG_WIDTH or h != EXPECTED_PNG_HEIGHT:
                    issues.append(
                        self._issue(
                            "asset_manifest_integrity",
                            "PNG_DIMENSIONS_MISMATCH",
                            "assets/M12_PROB_TREE_TRIAL_2026_13.png",
                            f"Actual PNG dimensions {w}x{h} do not match {EXPECTED_PNG_WIDTH}x{EXPECTED_PNG_HEIGHT}.",
                        )
                    )

        return issues

    def _validate_coverage_effects(
        self, cov_data: dict[str, Any]
    ) -> list[LocalDepthSupplementIssue]:
        issues: list[LocalDepthSupplementIssue] = []
        if cov_data.get("base_depth_dataset") != "DATA-MATH12-039":
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "BASE_DATASET_MISMATCH",
                    "coverage_after_043.json",
                    "base_depth_dataset must be DATA-MATH12-039.",
                )
            )
        if cov_data.get("base_depth_aggregate_sha256") != EXPECTED_BASE_DEPTH_AGGREGATE_SHA256:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "BASE_DEPTH_AGGREGATE_MISMATCH",
                    "coverage_after_043.json",
                    f"Expected base depth aggregate {EXPECTED_BASE_DEPTH_AGGREGATE_SHA256}, got {cov_data.get('base_depth_aggregate_sha256')}.",
                )
            )

        effects = cov_data.get("effects", {})
        if tuple(effects.get("derivative_remaining_zero_evidence", [])) != EXPECTED_DERIVATIVE_REMAINING_ZERO:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "DERIVATIVE_REMAINING_ZERO_MISMATCH",
                    "coverage_after_043.json",
                    f"derivative_remaining_zero_evidence must be exactly {EXPECTED_DERIVATIVE_REMAINING_ZERO}.",
                )
            )
        if tuple(effects.get("vector_legacy_remaining_zero_evidence", [])) != EXPECTED_VECTOR_REMAINING_ZERO:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "VECTOR_REMAINING_ZERO_MISMATCH",
                    "coverage_after_043.json",
                    f"vector_legacy_remaining_zero_evidence must be exactly empty {EXPECTED_VECTOR_REMAINING_ZERO}.",
                )
            )
        if effects.get("derivative_zero_evidence_problem_types_after") != 1:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "DERIVATIVE_ZERO_COUNT_MISMATCH",
                    "coverage_after_043.json",
                    "derivative_zero_evidence_problem_types_after must be 1.",
                )
            )
        if effects.get("vector_legacy_zero_evidence_after") != 0:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "VECTOR_ZERO_COUNT_MISMATCH",
                    "coverage_after_043.json",
                    "vector_legacy_zero_evidence_after must be 0.",
                )
            )
        if effects.get("probability_practice_units_after") != 22:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "PROBABILITY_PRACTICE_UNITS_MISMATCH",
                    "coverage_after_043.json",
                    "probability_practice_units_after must be 22.",
                )
            )
        if effects.get("probability_tree_or_total_after") != 3:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "PROBABILITY_TREE_COUNT_MISMATCH",
                    "coverage_after_043.json",
                    "probability_tree_or_total_after must be 3.",
                )
            )
        if effects.get("probability_source_families_after") != 4:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "PROBABILITY_SOURCE_FAMILIES_MISMATCH",
                    "coverage_after_043.json",
                    "probability_source_families_after must be 4.",
                )
            )

        if cov_data.get("official_scope_coverage") != "PASS_20_OF_20_UNCHANGED":
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "OFFICIAL_SCOPE_MISMATCH",
                    "coverage_after_043.json",
                    "official_scope_coverage must be PASS_20_OF_20_UNCHANGED.",
                )
            )

        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], cov_data: dict[str, Any]
    ) -> list[LocalDepthSupplementIssue]:
        issues: list[LocalDepthSupplementIssue] = []
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
                    "RIGHTS_STATUS_NOT_REVIEW_REQUIRED",
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
        self, path: Path, issues: list[LocalDepthSupplementIssue]
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
    ) -> LocalDepthSupplementIssue:
        return LocalDepthSupplementIssue(
            check=check, code=code, location=location, message=message
        )
