from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.curriculum.grouped_data_dispersion_staging import (
    DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH,
    EXPECTED_PROBLEM_TYPE_CODES,
)
from app.questions.vector_source_staging import (
    EXPECTED_ANSWER_AUTHORITY,
    EXPECTED_PRIMARY_SOURCES,
)


DEFAULT_GROUPED_DATA_DISPERSION_SOURCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "grouped_data_dispersion_v0_1"
    / "staging"
    / "v0_1"
)
EXPECTED_SCAN_COUNTS = {
    "NGOC_VY_40_DE_2026": (75, 48),
    "PROVINCIAL_TRIAL_2025": (24, 16),
    "OFFICIAL_EXAM_SOLUTIONS_2025": (8, 4),
}
EXPECTED_INCLUDE_INTENTS = (
    "calculate grouped-data range",
    "calculate grouped-data interquartile range",
    "calculate grouped-data variance",
    "calculate grouped-data standard deviation",
    "compare grouped samples using range/IQR/variance/standard deviation",
    "infer stability/consistency from dispersion",
    "interpret or conclude from dispersion measures",
    "real-world/interdisciplinary use of grouped-data dispersion",
)
EXPECTED_EXCLUDE_INTENTS = (
    "grouped-data mean only",
    "grouped-data median only",
    "grouped-data mode only",
    "Q1/Q2/Q3 only when no dispersion measure or comparison is assessed",
    "identify the median group only",
    "probability tasks that merely reuse a grouped-data table",
)
EXPECTED_INCLUDE_EXAMPLES = (
    ("NGOC_VY_40_DE_2026", 1, "6", "CALCULATE_GROUPED_VARIANCE"),
    ("NGOC_VY_40_DE_2026", 2, "6", "CALCULATE_GROUPED_IQR"),
    ("NGOC_VY_40_DE_2026", 2, "8", "CALCULATE_GROUPED_STANDARD_DEVIATION"),
    ("PROVINCIAL_TRIAL_2025", 2, "11", "CALCULATE_GROUPED_RANGE"),
    ("PROVINCIAL_TRIAL_2025", 2, "12", "CALCULATE_GROUPED_IQR"),
)
EXPECTED_EXCLUSION_EXAMPLES = (
    ("NGOC_VY_40_DE_2026", 8, "6"),
    ("PROVINCIAL_TRIAL_2025", 6, "8"),
    ("OFFICIAL_EXAM_SOLUTIONS_2025", 3, "3"),
)


@dataclass(frozen=True, slots=True, order=True)
class GroupedDataDispersionSourceIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class GroupedDataDispersionSourceReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    scan_counts: dict[str, dict[str, int]]
    primary_source_ids: tuple[str, ...]
    rights_status: str | None
    production_eligible: bool
    database_import_allowed: bool
    errors: tuple[GroupedDataDispersionSourceIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "scan_counts": self.scan_counts,
            "primary_source_ids": list(self.primary_source_ids),
            "rights_status": self.rights_status,
            "production_eligible": self.production_eligible,
            "database_import_allowed": self.database_import_allowed,
            "errors": [asdict(error) for error in self.errors],
        }


class GroupedDataDispersionQuestionSourceValidator:
    """Validate source locks and scan policy without loading source binaries."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_SOURCE_PATH,
    ) -> GroupedDataDispersionSourceReport:
        path = dataset_path.resolve()
        initial: list[GroupedDataDispersionSourceIssue] = []
        manifest = self._load_object(path / "source_manifest.json", initial)
        contract = self._load_object(path / "question_scan_contract.json", initial)
        seed = self._load_object(path / "source_scan_seed.json", initial)
        primary = manifest.get("primary_sources")
        authority = manifest.get("answer_authority")
        primary_rows = primary if isinstance(primary, list) else []
        authority_rows = authority if isinstance(authority, list) else []
        seed_sources = seed.get("sources")
        seed_rows = seed_sources if isinstance(seed_sources, list) else []
        checks_to_errors = {
            "required_files": [
                error for error in initial if error.check == "required_files"
            ],
            "source_identity": self._validate_source_identity(manifest),
            "source_hashes": self._validate_source_hashes(manifest),
            "rights_boundary": self._validate_rights(manifest, contract),
            "scan_contract": self._validate_contract(contract),
            "grade11_boundary": self._validate_scope_boundary(contract),
            "true_false_atomicity": self._validate_group_policy(contract),
            "heuristic_scan_counts": self._validate_scan_counts(seed),
            "confirmed_examples": self._validate_examples(seed),
            "source_references": self._validate_source_references(seed),
            "no_pdf_binaries": self._validate_no_pdfs(path),
            "non_importable": self._validate_non_importable(manifest, contract, seed),
        }
        errors = list(initial)
        for name, check_errors in checks_to_errors.items():
            if name != "required_files":
                errors.extend(check_errors)
        checks = {
            name: not check_errors
            for name, check_errors in checks_to_errors.items()
        }
        scan_counts = {
            str(row.get("source_key")): {
                "raw_question_windows_with_dispersion_keywords": int(
                    row.get("raw_question_windows_with_dispersion_keywords", 0)
                ),
                "heuristic_unique_windows": int(
                    row.get("heuristic_unique_windows", 0)
                ),
            }
            for row in seed_rows
            if isinstance(row, dict) and isinstance(row.get("source_key"), str)
        }
        return GroupedDataDispersionSourceReport(
            dataset_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts={
                "primary_sources": len(primary_rows),
                "answer_authorities": len(authority_rows),
                "seed_sources": len(seed_rows),
                "confirmed_include_examples": len(
                    seed.get("confirmed_include_examples", [])
                ),
                "confirmed_exclusion_examples": len(
                    seed.get("confirmed_exclusion_examples", [])
                ),
            },
            scan_counts=scan_counts,
            primary_source_ids=tuple(
                str(row.get("drive_file_id"))
                for row in primary_rows
                if isinstance(row, dict)
            ),
            rights_status=manifest.get("rights_status"),
            production_eligible=False,
            database_import_allowed=False,
            errors=tuple(sorted(set(errors))),
        )

    @staticmethod
    def _validate_source_identity(
        manifest: dict[str, Any],
    ) -> list[GroupedDataDispersionSourceIssue]:
        primary = manifest.get("primary_sources")
        actual = {
            row.get("source_key"): (row.get("drive_file_id"), row.get("sha256"))
            for row in primary
            if isinstance(row, dict)
        } if isinstance(primary, list) else {}
        authority = manifest.get("answer_authority")
        authority_identity = tuple(
            (row.get("drive_file_id"), row.get("sha256"))
            for row in authority
            if isinstance(row, dict)
        ) if isinstance(authority, list) else ()
        valid = (
            manifest.get("manifest_code")
            == "MATH12_GROUPED_DISPERSION_SOURCE_MANIFEST_V0_1"
            and manifest.get("status") == "SOURCE_LOCK_CANDIDATE"
            and actual == EXPECTED_PRIMARY_SOURCES
            and authority_identity == (EXPECTED_ANSWER_AUTHORITY,)
        )
        if valid:
            return []
        return [
            GroupedDataDispersionSourceIssue(
                "source_identity",
                "SOURCE_IDENTITY_MISMATCH",
                "source_manifest.json",
                "Source IDs or hashes differ from the locked bundle.",
            )
        ]

    @staticmethod
    def _validate_source_hashes(
        manifest: dict[str, Any],
    ) -> list[GroupedDataDispersionSourceIssue]:
        rows = [
            *manifest.get("primary_sources", []),
            *manifest.get("answer_authority", []),
        ]
        sha_pattern = re.compile(r"^[0-9a-f]{64}$")
        return [
            GroupedDataDispersionSourceIssue(
                "source_hashes",
                "INVALID_SOURCE_SHA256",
                f"source_manifest.json[{index}]",
                repr(row),
            )
            for index, row in enumerate(rows)
            if not isinstance(row, dict)
            or not isinstance(row.get("sha256"), str)
            or sha_pattern.fullmatch(row["sha256"]) is None
        ]

    @staticmethod
    def _validate_rights(
        manifest: dict[str, Any], contract: dict[str, Any]
    ) -> list[GroupedDataDispersionSourceIssue]:
        visual_policy = contract.get("visual_policy")
        valid = (
            manifest.get("rights_status") == "REVIEW_REQUIRED"
            and isinstance(visual_policy, dict)
            and visual_policy.get("rights_status") == "REVIEW_REQUIRED"
        )
        if valid:
            return []
        return [
            GroupedDataDispersionSourceIssue(
                "rights_boundary",
                "INVALID_RIGHTS_STATUS",
                "source_manifest.json",
                "Rights must remain REVIEW_REQUIRED.",
            )
        ]

    @staticmethod
    def _validate_contract(
        contract: dict[str, Any],
    ) -> list[GroupedDataDispersionSourceIssue]:
        valid = (
            contract.get("status") == "STRUCTURAL_SCAN"
            and contract.get("target_chapter_code") == "GROUPED_DATA_DISPERSION"
            and contract.get("initial_status") == "STRUCTURAL_CANDIDATE"
            and tuple(contract.get("allowed_question_structures", []))
            == ("MULTIPLE_CHOICE", "SHORT_ANSWER", "TRUE_FALSE_FOUR")
            and set(contract.get("never_auto_set", []))
            == {"VERIFIED", "APPROVED", "production_eligible"}
        )
        if valid:
            return []
        return [
            GroupedDataDispersionSourceIssue(
                "scan_contract",
                "INVALID_STRUCTURAL_SCAN_CONTRACT",
                "question_scan_contract.json",
                "Structural staging contract changed.",
            )
        ]

    @staticmethod
    def _validate_scope_boundary(
        contract: dict[str, Any],
    ) -> list[GroupedDataDispersionSourceIssue]:
        prerequisite = contract.get("prerequisite_policy")
        valid = (
            tuple(contract.get("include_primary_intents", []))
            == EXPECTED_INCLUDE_INTENTS
            and tuple(contract.get("exclude_primary_intents", []))
            == EXPECTED_EXCLUDE_INTENTS
            and isinstance(prerequisite, dict)
            and "Quartile interpolation and grouped mean may appear"
            in str(prerequisite.get("rule"))
            and "Grade-11 prerequisite content"
            in str(prerequisite.get("grade11_boundary"))
        )
        if valid:
            return []
        return [
            GroupedDataDispersionSourceIssue(
                "grade11_boundary",
                "GRADE11_SCAN_BOUNDARY_MISMATCH",
                "question_scan_contract.json",
                "Standalone mean/median/mode/quartile tasks must remain excluded.",
            )
        ]

    @staticmethod
    def _validate_group_policy(
        contract: dict[str, Any],
    ) -> list[GroupedDataDispersionSourceIssue]:
        policy = contract.get("mixed_group_policy")
        valid = (
            isinstance(policy, dict)
            and policy.get("rule")
            == "Never split TRUE_FALSE_FOUR shared context during structural staging."
            and policy.get("action")
            == "Keep full group; mark mixed_scope=true when only some children assess Grade-12 dispersion."
        )
        if valid:
            return []
        return [
            GroupedDataDispersionSourceIssue(
                "true_false_atomicity",
                "TRUE_FALSE_FOUR_POLICY_MISMATCH",
                "question_scan_contract.json.mixed_group_policy",
                "TRUE_FALSE_FOUR groups must remain atomic and mixed-scope aware.",
            )
        ]

    @staticmethod
    def _validate_scan_counts(
        seed: dict[str, Any],
    ) -> list[GroupedDataDispersionSourceIssue]:
        sources = seed.get("sources")
        actual = {
            row.get("source_key"): (
                row.get("raw_question_windows_with_dispersion_keywords"),
                row.get("heuristic_unique_windows"),
            )
            for row in sources
            if isinstance(row, dict)
        } if isinstance(sources, list) else {}
        if actual == EXPECTED_SCAN_COUNTS:
            return []
        return [
            GroupedDataDispersionSourceIssue(
                "heuristic_scan_counts",
                "HEURISTIC_SCAN_COUNT_MISMATCH",
                "source_scan_seed.json.sources",
                f"Expected {EXPECTED_SCAN_COUNTS!r}; found {actual!r}.",
            )
        ]

    @staticmethod
    def _validate_examples(
        seed: dict[str, Any],
    ) -> list[GroupedDataDispersionSourceIssue]:
        includes = tuple(
            (
                row.get("source_key"),
                row.get("source_page"),
                row.get("question_number"),
                row.get("suggested_problem_type"),
            )
            for row in seed.get("confirmed_include_examples", [])
            if isinstance(row, dict)
        )
        exclusions = tuple(
            (
                row.get("source_key"),
                row.get("source_page"),
                row.get("question_number"),
            )
            for row in seed.get("confirmed_exclusion_examples", [])
            if isinstance(row, dict)
        )
        exclusion_reasons = [
            str(row.get("reason", ""))
            for row in seed.get("confirmed_exclusion_examples", [])
            if isinstance(row, dict)
        ]
        valid = (
            includes == EXPECTED_INCLUDE_EXAMPLES
            and exclusions == EXPECTED_EXCLUSION_EXAMPLES
            and all(reason.strip() for reason in exclusion_reasons)
            and all(row[3] in EXPECTED_PROBLEM_TYPE_CODES for row in includes)
        )
        if valid:
            return []
        return [
            GroupedDataDispersionSourceIssue(
                "confirmed_examples",
                "CONFIRMED_EXAMPLE_SET_MISMATCH",
                "source_scan_seed.json",
                "Confirmed include/exclusion examples differ from the bundle.",
            )
        ]

    @staticmethod
    def _validate_source_references(
        seed: dict[str, Any],
    ) -> list[GroupedDataDispersionSourceIssue]:
        expected = set(EXPECTED_PRIMARY_SOURCES)
        sources = seed.get("sources", [])
        valid = (
            {row.get("source_key") for row in sources if isinstance(row, dict)}
            == expected
            and all(
                row.get("source_key") in expected
                for field in (
                    "confirmed_include_examples",
                    "confirmed_exclusion_examples",
                )
                for row in seed.get(field, [])
                if isinstance(row, dict)
            )
        )
        if valid:
            return []
        return [
            GroupedDataDispersionSourceIssue(
                "source_references",
                "UNKNOWN_SOURCE_REFERENCE",
                "source_scan_seed.json",
                "Every scan seed row must resolve to a locked primary source.",
            )
        ]

    @staticmethod
    def _validate_no_pdfs(path: Path) -> list[GroupedDataDispersionSourceIssue]:
        pdfs = [
            file_path
            for file_path in path.rglob("*")
            if file_path.is_file() and file_path.suffix.lower() == ".pdf"
        ]
        if not pdfs:
            return []
        return [
            GroupedDataDispersionSourceIssue(
                "no_pdf_binaries",
                "SOURCE_PDF_FORBIDDEN",
                pdfs[0].as_posix(),
                "Source PDFs must not be committed to staging.",
            )
        ]

    @staticmethod
    def _validate_non_importable(
        manifest: dict[str, Any],
        contract: dict[str, Any],
        seed: dict[str, Any],
    ) -> list[GroupedDataDispersionSourceIssue]:
        valid = (
            manifest.get("status") == "SOURCE_LOCK_CANDIDATE"
            and contract.get("initial_status") == "STRUCTURAL_CANDIDATE"
            and seed.get("status") == "HEURISTIC_TRIAGE"
            and "NOT final candidate counts" in str(seed.get("note"))
        )
        if valid:
            return []
        return [
            GroupedDataDispersionSourceIssue(
                "non_importable",
                "IMPORT_OR_PROMOTION_BOUNDARY_VIOLATION",
                "source staging",
                "Source staging must remain heuristic and non-importable.",
            )
        ]

    @classmethod
    def _load_object(
        cls,
        path: Path,
        errors: list[GroupedDataDispersionSourceIssue],
    ) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(
                GroupedDataDispersionSourceIssue(
                    "required_files",
                    "INVALID_OR_MISSING_JSON",
                    path.as_posix(),
                    str(error),
                )
            )
            return {}
        if isinstance(value, dict):
            return value
        errors.append(
            GroupedDataDispersionSourceIssue(
                "required_files",
                "INVALID_JSON_SHAPE",
                path.as_posix(),
                "Expected a JSON object.",
            )
        )
        return {}
