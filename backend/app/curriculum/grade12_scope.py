from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DATASET_ROOT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
)
DEFAULT_GRADE12_SCOPE_PATH = (
    DATASET_ROOT
    / "staging"
    / "grade12_scope_v0_1"
    / "grade12_scope_registry_v0_1.json"
)

EXPECTED_GRADE12_CHAPTER_ORDER = (
    "DERIVATIVE_APPLICATIONS",
    "VECTORS_GEOMETRY",
    "GROUPED_DATA_DISPERSION",
    "INTEGRALS",
    "OXYZ_CHAPTER",
    "PROBABILITY_CHAPTER",
)
EXPECTED_REGISTRY_SHA256 = (
    "8e37f1cfaeae612e4b0ca91504b15df87b6da64e5ce5b46a68f7ba72d8255c47"
)
EXPECTED_CANONICAL_SHA256 = {
    "chapters.json": "a56b7e2aa340d991d51b6d795c7c6fa5d4ddd3b0cfc183e1888219954e8d89ab",
    "topics.json": "66813ee14b5c5cd955c0a7236f25befaa9c9a9f575784cb730289f4a9b7046af",
    "manifest.json": "09adbf1d4b804690bb8eaa6367693f60b5448652e1d25966f586e4317c998b74",
}


@dataclass(frozen=True, slots=True, order=True)
class Grade12ScopeIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class Grade12ScopeReport:
    registry_path: str
    status: str
    checks: dict[str, bool]
    in_scope_chapters: tuple[str, ...]
    legacy_out_of_scope: tuple[str, ...]
    registry_sha256: str
    errors: tuple[Grade12ScopeIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "registry_path": self.registry_path,
            "status": self.status,
            "checks": self.checks,
            "in_scope_chapters": list(self.in_scope_chapters),
            "legacy_out_of_scope": list(self.legacy_out_of_scope),
            "registry_sha256": self.registry_sha256,
            "errors": [asdict(error) for error in self.errors],
        }


class Grade12ScopeValidator:
    """Validate the non-destructive Grade-12 scope correction registry."""

    def validate(
        self, registry_path: Path = DEFAULT_GRADE12_SCOPE_PATH
    ) -> Grade12ScopeReport:
        path = registry_path.resolve()
        issues: list[Grade12ScopeIssue] = []
        data = self._load(path, issues)
        in_scope = tuple(
            row.get("code", "")
            for row in data.get("grade12_chapters", [])
            if isinstance(row, dict)
        )
        legacy = tuple(
            row.get("code", "")
            for row in data.get("legacy_out_of_scope", [])
            if isinstance(row, dict)
        )
        registry_hash = self._semantic_hash(data) if data else ""

        check_issues = {
            "registry_file": [issue for issue in issues if issue.check == "registry_file"],
            "registry_identity": self._validate_identity(data, registry_hash),
            "grade12_scope_order": self._validate_scope(data, in_scope),
            "grade11_legacy_exclusion": self._validate_legacy(data),
            "non_destructive_policy": self._validate_policy(data),
            "canonical_preservation": self._validate_canonical_preservation(),
        }
        for name, errors in check_issues.items():
            if name != "registry_file":
                issues.extend(errors)
        checks = {name: not errors for name, errors in check_issues.items()}
        errors = tuple(sorted(set(issues)))
        return Grade12ScopeReport(
            registry_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            in_scope_chapters=in_scope,
            legacy_out_of_scope=legacy,
            registry_sha256=registry_hash,
            errors=errors,
        )

    @staticmethod
    def _load(path: Path, issues: list[Grade12ScopeIssue]) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            issues.append(Grade12ScopeIssue(
                "registry_file", "INVALID_REGISTRY", path.name, str(error)
            ))
            return {}
        if not isinstance(value, dict):
            issues.append(Grade12ScopeIssue(
                "registry_file", "INVALID_REGISTRY_SHAPE", path.name,
                "Registry must be a JSON object.",
            ))
            return {}
        return value

    @staticmethod
    def _semantic_hash(value: Any) -> str:
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _validate_identity(
        data: dict[str, Any], registry_hash: str
    ) -> list[Grade12ScopeIssue]:
        expected = {
            "registry_code": "MATH_G12_GDPT2018_SCOPE_V0_1",
            "status": "REVIEW_CANDIDATE",
            "subject_code": "MATH_G12",
            "curriculum_code": "GDPT2018",
            "curriculum_version_code": "GDPT2018_2018",
        }
        issues = [
            Grade12ScopeIssue(
                "registry_identity", "INVALID_REGISTRY_IDENTITY", field,
                f"Expected {expected_value!r}; found {data.get(field)!r}.",
            )
            for field, expected_value in expected.items()
            if data.get(field) != expected_value
        ]
        if registry_hash != EXPECTED_REGISTRY_SHA256:
            issues.append(Grade12ScopeIssue(
                "registry_identity", "REGISTRY_HASH_MISMATCH", "sha256",
                f"Expected {EXPECTED_REGISTRY_SHA256}; found {registry_hash}.",
            ))
        return issues

    @staticmethod
    def _validate_scope(
        data: dict[str, Any], in_scope: tuple[str, ...]
    ) -> list[Grade12ScopeIssue]:
        issues: list[Grade12ScopeIssue] = []
        if in_scope != EXPECTED_GRADE12_CHAPTER_ORDER:
            issues.append(Grade12ScopeIssue(
                "grade12_scope_order", "INVALID_GRADE12_SCOPE_ORDER",
                "grade12_chapters", f"Found {in_scope!r}.",
            ))
        rows = data.get("grade12_chapters", [])
        if not isinstance(rows, list) or any(
            not isinstance(row, dict)
            or row.get("scope_status") != "IN_SCOPE_GRADE12"
            or row.get("order_index") != (index + 1) * 10
            for index, row in enumerate(rows)
        ):
            issues.append(Grade12ScopeIssue(
                "grade12_scope_order", "INVALID_GRADE12_SCOPE_ENTRY",
                "grade12_chapters", "Every chapter must be ordered and in scope.",
            ))
        return issues

    @staticmethod
    def _validate_legacy(data: dict[str, Any]) -> list[Grade12ScopeIssue]:
        rows = data.get("legacy_out_of_scope", [])
        matching = [
            row for row in rows
            if isinstance(row, dict) and row.get("code") == "EXPONENTIAL_LOGARITHM"
        ] if isinstance(rows, list) else []
        if len(matching) != 1:
            return [Grade12ScopeIssue(
                "grade11_legacy_exclusion", "MISSING_EXPONENTIAL_LOGARITHM_EXCLUSION",
                "legacy_out_of_scope", "Expected exactly one legacy exclusion.",
            )]
        row = matching[0]
        if (
            row.get("scope_status") != "OUT_OF_SCOPE_GRADE12"
            or row.get("actual_grade_level") != 11
            or row.get("destructive_delete_allowed") is not False
        ):
            return [Grade12ScopeIssue(
                "grade11_legacy_exclusion", "INVALID_EXPONENTIAL_LOGARITHM_EXCLUSION",
                "legacy_out_of_scope.EXPONENTIAL_LOGARITHM",
                "The legacy chapter must remain Grade 11, out of Grade-12 "
                "scope, and non-destructive.",
            )]
        return []

    @staticmethod
    def _validate_policy(data: dict[str, Any]) -> list[Grade12ScopeIssue]:
        policy = data.get("policy")
        if not isinstance(policy, dict) or (
            policy.get("do_not_delete_legacy_rows") is not True
            or policy.get("canonical_change_requires_separate_reviewed_promotion") is not True
        ):
            return [Grade12ScopeIssue(
                "non_destructive_policy", "INVALID_NON_DESTRUCTIVE_POLICY", "policy",
                "Legacy rows must be preserved and canonical promotion must be separate.",
            )]
        return []

    @staticmethod
    def _validate_canonical_preservation() -> list[Grade12ScopeIssue]:
        issues: list[Grade12ScopeIssue] = []
        for name, expected_hash in EXPECTED_CANONICAL_SHA256.items():
            path = DATASET_ROOT / name
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                actual = Grade12ScopeValidator._semantic_hash(value)
            except (OSError, json.JSONDecodeError):
                actual = ""
            if actual != expected_hash:
                issues.append(Grade12ScopeIssue(
                    "canonical_preservation", "CANONICAL_FILE_CHANGED", name,
                    f"Expected {expected_hash}; found {actual}.",
                ))
        return issues
