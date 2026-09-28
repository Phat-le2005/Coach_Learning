from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from app.curriculum.vector_staging import DEFAULT_VECTOR_STAGING_PATH


DEFAULT_VECTOR_SOURCE_STAGING_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "vector_coordinates_v0_1"
    / "staging"
    / "v0_1"
)

EXPECTED_PRIMARY_SOURCES = {
    "NGOC_VY_40_DE_2026": (
        "1kVuA8ZIb402-_TM_fqI_tj1WuS0CBwg1",
        "15579d487c6ad6cdd6386c96ac829c48710c3ca66104acfbd0fc9e9183b586b4",
    ),
    "PROVINCIAL_TRIAL_2025": (
        "1RK3hOLaqhf2ZXDo_R1hJu2IwkYzZbvlP",
        "d3f2158ee028431e01b2f30f7e446d66d75e364c27d49c53f3e09c193325b7e0",
    ),
    "OFFICIAL_EXAM_SOLUTIONS_2025": (
        "1jGjnJ3Wq2ynISxB4P1g9mk2CXibl-YXy",
        "90d5cb68a6f91418287c6643548f4f40ea9bb1598705a177b41bce07b09df11f",
    ),
}
EXPECTED_SECONDARY_SOURCE = (
    "REFERENCE_EXAM_2025_PPTX",
    "1Grv0wWnH6JlQUjFFQwoByvQX42S646DV",
)
EXPECTED_ANSWER_AUTHORITY = (
    "1GuZuVoDDxbES41-1OA0azCFiD0NuBq76",
    "25631480f3a830c65571142b795755ae235d8734f1e621b19e992ae15f0f7b41",
)
EXPECTED_INCLUDE_INTENTS = (
    "vector relations and identities in spatial figures",
    "sum/difference/scalar multiplication of vectors in space",
    "dot product and vector angle as vector concepts",
    "point/vector coordinates in Oxyz",
    "vector coordinates from two points",
    "vector length and point-to-point distance",
    "coordinate expressions of vector operations",
    "midpoint/centroid by coordinates",
    "parameter conditions whose main object is vector coordinates",
    "real-world vector-coordinate modeling",
)
EXPECTED_EXCLUDED_INTENTS = (
    "plane equation or plane normal as the main task",
    "line equation or line direction representation as the main task",
    "sphere equation/center/radius/tangent plane as the main task",
    "coordinate geometry distance tasks whose primary object is plane/line/sphere",
    "Grade-11 exponential/logarithm questions",
)


@dataclass(frozen=True, slots=True, order=True)
class VectorSourceIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class VectorSourceReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    primary_source_ids: tuple[str, ...]
    rights_status: str | None
    secondary_only_promotion_evidence: bool
    errors: tuple[VectorSourceIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "primary_source_ids": list(self.primary_source_ids),
            "rights_status": self.rights_status,
            "secondary_only_promotion_evidence": self.secondary_only_promotion_evidence,
            "errors": [asdict(error) for error in self.errors],
        }


class VectorQuestionSourceValidator:
    """Validate source locks and scan policy without accessing source binaries."""

    def validate(
        self, dataset_path: Path = DEFAULT_VECTOR_SOURCE_STAGING_PATH
    ) -> VectorSourceReport:
        path = dataset_path.resolve()
        initial: list[VectorSourceIssue] = []
        manifest = self._load_object(path / "source_manifest.json", initial)
        contract = self._load_object(path / "question_scan_contract.json", initial)
        seed = self._load_object(path / "source_scan_seed.json", initial)
        primary = manifest.get("primary_sources", [])
        secondary = manifest.get("secondary_sources", [])
        authority = manifest.get("answer_authority", [])
        primary_ids = tuple(
            row.get("drive_file_id", "") for row in primary if isinstance(row, dict)
        ) if isinstance(primary, list) else ()
        secondary_key = EXPECTED_SECONDARY_SOURCE[0]

        checks_to_errors = {
            "required_files": [error for error in initial if error.check == "required_files"],
            "source_identity": self._validate_source_identity(manifest),
            "source_hashes": self._validate_source_hashes(manifest),
            "rights_boundary": self._validate_rights(manifest),
            "secondary_promotion_boundary": self._validate_secondary(manifest),
            "scan_contract": self._validate_contract(contract),
            "oxyz_boundary": self._validate_scope_boundary(contract),
            "source_scan_references": self._validate_seed(seed, manifest),
        }
        errors = list(initial)
        for name, check_errors in checks_to_errors.items():
            if name != "required_files":
                errors.extend(check_errors)
        checks = {name: not check_errors for name, check_errors in checks_to_errors.items()}
        ordered_errors = tuple(sorted(set(errors)))
        return VectorSourceReport(
            dataset_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts={
                "primary_sources": len(primary) if isinstance(primary, list) else 0,
                "secondary_sources": len(secondary) if isinstance(secondary, list) else 0,
                "answer_authorities": len(authority) if isinstance(authority, list) else 0,
                "seed_sources": len(seed.get("sources", []))
                if isinstance(seed.get("sources"), list) else 0,
            },
            primary_source_ids=primary_ids,
            rights_status=manifest.get("rights_status"),
            secondary_only_promotion_evidence=self.has_primary_promotion_evidence(
                [secondary_key], manifest
            ),
            errors=ordered_errors,
        )

    @staticmethod
    def _load_object(path: Path, errors: list[VectorSourceIssue]) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(VectorSourceIssue(
                "required_files", "INVALID_OR_MISSING_JSON", path.name, str(error)
            ))
            return {}
        if not isinstance(value, dict):
            errors.append(VectorSourceIssue(
                "required_files", "INVALID_JSON_SHAPE", path.name,
                "Expected a JSON object.",
            ))
            return {}
        return value

    @staticmethod
    def has_primary_promotion_evidence(
        source_keys: Iterable[str], manifest: dict[str, Any]
    ) -> bool:
        primary_keys = {
            row.get("source_key")
            for row in manifest.get("primary_sources", [])
            if isinstance(row, dict)
        }
        return any(source_key in primary_keys for source_key in source_keys)

    @staticmethod
    def _validate_source_identity(manifest: dict[str, Any]) -> list[VectorSourceIssue]:
        errors: list[VectorSourceIssue] = []
        primary = manifest.get("primary_sources", [])
        actual = {
            row.get("source_key"): (row.get("drive_file_id"), row.get("sha256"))
            for row in primary if isinstance(row, dict)
        } if isinstance(primary, list) else {}
        if actual != EXPECTED_PRIMARY_SOURCES:
            errors.append(VectorSourceIssue(
                "source_identity", "PRIMARY_SOURCE_IDENTITY_MISMATCH",
                "source_manifest.json.primary_sources", repr(actual),
            ))
        secondary = manifest.get("secondary_sources", [])
        secondary_identity = tuple(
            (row.get("source_key"), row.get("drive_file_id"))
            for row in secondary if isinstance(row, dict)
        ) if isinstance(secondary, list) else ()
        if secondary_identity != (EXPECTED_SECONDARY_SOURCE,):
            errors.append(VectorSourceIssue(
                "source_identity", "SECONDARY_SOURCE_IDENTITY_MISMATCH",
                "source_manifest.json.secondary_sources", repr(secondary_identity),
            ))
        authority = manifest.get("answer_authority", [])
        authority_identity = tuple(
            (row.get("drive_file_id"), row.get("sha256"))
            for row in authority if isinstance(row, dict)
        ) if isinstance(authority, list) else ()
        if authority_identity != (EXPECTED_ANSWER_AUTHORITY,):
            errors.append(VectorSourceIssue(
                "source_identity", "ANSWER_AUTHORITY_MISMATCH",
                "source_manifest.json.answer_authority", repr(authority_identity),
            ))
        return errors

    @staticmethod
    def _validate_source_hashes(manifest: dict[str, Any]) -> list[VectorSourceIssue]:
        pattern = re.compile(r"^[0-9a-f]{64}$")
        locked: list[Any] = []
        for field in ("primary_sources", "answer_authority"):
            value = manifest.get(field)
            if isinstance(value, list):
                locked.extend(value)
            else:
                locked.append(value)
        return [
            VectorSourceIssue(
                "source_hashes", "INVALID_SOURCE_SHA256", f"locked_sources[{index}]",
                repr(row.get("sha256") if isinstance(row, dict) else None),
            )
            for index, row in enumerate(locked)
            if not isinstance(row, dict)
            or not isinstance(row.get("sha256"), str)
            or pattern.fullmatch(row["sha256"]) is None
        ]

    @staticmethod
    def _validate_rights(manifest: dict[str, Any]) -> list[VectorSourceIssue]:
        return [] if manifest.get("rights_status") == "REVIEW_REQUIRED" else [
            VectorSourceIssue(
                "rights_boundary", "INVALID_RIGHTS_STATUS", "source_manifest.json",
                "Rights must remain REVIEW_REQUIRED.",
            )
        ]

    @staticmethod
    def _validate_secondary(manifest: dict[str, Any]) -> list[VectorSourceIssue]:
        secondary = manifest.get("secondary_sources", [])
        valid = (
            isinstance(secondary, list)
            and len(secondary) == 1
            and isinstance(secondary[0], dict)
            and secondary[0].get("source_key") == EXPECTED_SECONDARY_SOURCE[0]
            and secondary[0].get("promotion_allowed") is False
            and secondary[0].get("sha256") is None
            and secondary[0].get("role") == "SECONDARY_UNTIL_HASH_AND_PROVENANCE_LOCKED"
        )
        return [] if valid else [VectorSourceIssue(
            "secondary_promotion_boundary", "SECONDARY_SOURCE_PROMOTION_ALLOWED",
            "source_manifest.json.secondary_sources",
            "The secondary PPTX cannot be sole promotion evidence.",
        )]

    @staticmethod
    def _validate_contract(contract: dict[str, Any]) -> list[VectorSourceIssue]:
        group_policy = contract.get("mixed_group_policy")
        valid = (
            contract.get("status") == "STRUCTURAL_SCAN"
            and contract.get("target_chapter_code") == "VECTORS_GEOMETRY"
            and contract.get("initial_status") == "STRUCTURAL_CANDIDATE"
            and tuple(contract.get("allowed_question_structures", []))
            == ("MULTIPLE_CHOICE", "SHORT_ANSWER", "TRUE_FALSE_FOUR")
            and isinstance(group_policy, dict)
            and group_policy.get("rule")
            == "Never split a shared-context TRUE_FALSE_FOUR during structural staging."
            and group_policy.get("action")
            == "Keep full group, set mixed_scope=true, classify each child during academic review."
            and set(contract.get("never_auto_set", []))
            == {"VERIFIED", "APPROVED", "production_eligible"}
        )
        return [] if valid else [VectorSourceIssue(
            "scan_contract", "INVALID_STRUCTURAL_SCAN_CONTRACT",
            "question_scan_contract.json", "Structural candidate/group policy changed.",
        )]

    @staticmethod
    def _validate_scope_boundary(contract: dict[str, Any]) -> list[VectorSourceIssue]:
        valid = (
            tuple(contract.get("include_intents", [])) == EXPECTED_INCLUDE_INTENTS
            and tuple(contract.get("exclude_primary_intents", []))
            == EXPECTED_EXCLUDED_INTENTS
        )
        return [] if valid else [VectorSourceIssue(
            "oxyz_boundary", "INVALID_VECTOR_OXYZ_BOUNDARY",
            "question_scan_contract.json", "Vector/OXYZ scan boundaries changed.",
        )]

    @staticmethod
    def _validate_seed(
        seed: dict[str, Any], manifest: dict[str, Any]
    ) -> list[VectorSourceIssue]:
        primary_keys = set(EXPECTED_PRIMARY_SOURCES)
        problem_types = {
            row.get("code") for row in json.loads(
                (DEFAULT_VECTOR_STAGING_PATH / "problem_types.json").read_text(
                    encoding="utf-8"
                )
            ) if isinstance(row, dict)
        }
        errors: list[VectorSourceIssue] = []
        sources = seed.get("sources", [])
        if {
            row.get("source_key") for row in sources if isinstance(row, dict)
        } != primary_keys:
            errors.append(VectorSourceIssue(
                "source_scan_references", "SEED_SOURCE_MISMATCH",
                "source_scan_seed.json.sources", "Seed sources must match primaries.",
            ))
        for collection in ("confirmed_seed_examples", "confirmed_exclusion_examples"):
            for index, row in enumerate(seed.get(collection, [])):
                if not isinstance(row, dict) or row.get("source_key") not in primary_keys:
                    errors.append(VectorSourceIssue(
                        "source_scan_references", "UNKNOWN_SEED_SOURCE",
                        f"source_scan_seed.json.{collection}[{index}]", repr(row),
                    ))
                problem_type = row.get("suggested_problem_type") if isinstance(row, dict) else None
                if problem_type is not None and problem_type not in problem_types:
                    errors.append(VectorSourceIssue(
                        "source_scan_references", "UNKNOWN_PROBLEM_TYPE",
                        f"source_scan_seed.json.{collection}[{index}]", repr(problem_type),
                    ))
        if manifest.get("manifest_code") != "MATH12_VECTOR_SOURCE_MANIFEST_V0_1":
            errors.append(VectorSourceIssue(
                "source_scan_references", "MANIFEST_CODE_MISMATCH",
                "source_manifest.json", repr(manifest.get("manifest_code")),
            ))
        return errors
