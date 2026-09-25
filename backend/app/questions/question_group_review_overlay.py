from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
)


DEFAULT_QUESTION_GROUP_REVIEW_ROOT = (
    DEFAULT_QUESTION_GROUP_STAGING_PATH.parents[1] / "group_review"
)
REQUIRED_GROUP_REVIEW_FILES = (
    "README.md",
    "source_metadata.json",
    "source_evidence.json",
    "verified_groups.json",
    "hold_groups.json",
    "rejected_groups.json",
    "group_patch.json",
    "review_stats.json",
)
PRESERVED_STRUCTURAL_FIELDS = (
    "group_candidate_id",
    "source_candidate_id",
    "source_fingerprint",
    "source_code",
    "raw_subsource_code",
    "effective_subsource_code",
    "provenance_correction_code",
    "source_page",
    "question_number",
    "group_type",
    "group_context",
    "items",
)
ALLOWED_REVIEW_PATCH_FIELDS = {
    "reviewed_group_context",
    "reviewed_items",
    "visual_asset_required",
}


@dataclass(frozen=True, slots=True, order=True)
class GroupReviewOverlayIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class GroupReviewBatchReport:
    batch_code: str
    path: str
    status: str
    counts: dict[str, int]
    reviewed_group_ids: tuple[str, ...]
    errors: tuple[GroupReviewOverlayIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_code": self.batch_code,
            "path": self.path,
            "status": self.status,
            "counts": self.counts,
            "reviewed_group_ids": list(self.reviewed_group_ids),
            "errors": [asdict(error) for error in self.errors],
        }


@dataclass(frozen=True, slots=True)
class GroupReviewOverlayResult:
    groups: tuple[dict[str, Any], ...]
    report: GroupReviewBatchReport


@dataclass(frozen=True, slots=True)
class EffectiveQuestionGroupReview:
    structural_groups: tuple[dict[str, Any], ...]
    effective_groups: tuple[dict[str, Any], ...]
    review_batches: tuple[GroupReviewBatchReport, ...]
    issues: tuple[GroupReviewOverlayIssue, ...]

    @property
    def is_valid(self) -> bool:
        return all(batch.is_valid for batch in self.review_batches) and not self.issues

    @property
    def effective_usable_groups(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            group
            for group in self.effective_groups
            if not str(group.get("academic_review_status", "")).startswith("REJECTED_")
        )

    @property
    def promotion_ready_groups(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            group
            for group in self.effective_groups
            if group.get("promotion_ready") is True
        )


class QuestionGroupReviewOverlayResolver:
    """Apply one reviewed batch without changing DATA-MATH12-006 fields."""

    def resolve(
        self,
        groups: list[dict[str, Any]],
        batch_path: Path,
    ) -> GroupReviewOverlayResult:
        path = batch_path.resolve()
        issues = self._required_file_issues(path)
        verified = self._load_list(path / "verified_groups.json", issues)
        holds = self._load_list(path / "hold_groups.json", issues)
        rejected = self._load_list(path / "rejected_groups.json", issues)
        patches = self._load_list(path / "group_patch.json", issues)
        evidence = self._load_list(path / "source_evidence.json", issues)
        stats = self._load_object(path / "review_stats.json", issues)
        self._load_object(path / "source_metadata.json", issues)

        original = copy.deepcopy(groups)
        effective = copy.deepcopy(groups)
        original_by_id = self._groups_by_id(original, "structural", issues)
        effective_by_id = self._groups_by_id(effective, "effective", issues)
        records = {"VERIFIED": verified, "HOLD": holds, "REJECTED": rejected}
        ids = {
            name: self._record_ids(rows, name, issues)
            for name, rows in records.items()
        }
        all_ids = set().union(*ids.values())
        for group_id in sorted(all_ids - set(original_by_id)):
            self._add(
                issues,
                "group_references",
                "GROUP_NOT_FOUND",
                group_id,
                "Reviewed group ID does not resolve in DATA-MATH12-006 staging.",
            )
        self._validate_disjoint(ids, issues)

        patch_ids = self._record_ids(patches, "PATCH", issues)
        if patch_ids != ids["VERIFIED"]:
            self._add(
                issues,
                "patch_scope",
                "PATCH_SCOPE_MISMATCH",
                path.name,
                "Patch IDs must exactly match VERIFIED group IDs.",
            )
        evidence_by_id = {
            str(row["evidence_id"]): row
            for row in evidence
            if isinstance(row.get("evidence_id"), str)
        }
        if len(evidence_by_id) != len(evidence):
            self._add(
                issues,
                "evidence",
                "DUPLICATE_OR_MISSING_EVIDENCE_ID",
                path.name,
                "Every source evidence record must have a unique evidence_id.",
            )

        for index, patch in enumerate(patches):
            group_id = patch.get("group_candidate_id")
            values = patch.get("set")
            location = f"group_patch.json[{index}]"
            if not isinstance(group_id, str) or group_id not in effective_by_id:
                continue
            if not isinstance(values, dict):
                self._add(issues, "patch_shape", "INVALID_PATCH_SET", location,
                          "Patch set must be an object.")
                continue
            unexpected = sorted(set(values) - ALLOWED_REVIEW_PATCH_FIELDS)
            if unexpected:
                self._add(
                    issues,
                    "patch_scope",
                    "PATCH_FIELD_NOT_ALLOWED",
                    location,
                    f"Review patch contains unsupported fields: {unexpected}.",
                )
                continue
            reviewed_items = values.get("reviewed_items")
            if not isinstance(reviewed_items, list) or any(
                not isinstance(item, dict)
                or set(item) != {"label", "order_index", "reviewed_content"}
                for item in reviewed_items
            ):
                self._add(
                    issues,
                    "patch_shape",
                    "PATCH_ITEM_FIELDS_INVALID",
                    location,
                    "Patches may contain reviewed child text and its label/order only.",
                )
                continue
            effective_by_id[group_id].update(copy.deepcopy(values))

        records_by_id: dict[str, dict[str, Any]] = {}
        for rows in records.values():
            for record in rows:
                group_id = record.get("group_candidate_id")
                if not isinstance(group_id, str):
                    continue
                records_by_id[group_id] = record
                group = effective_by_id.get(group_id)
                if group is None:
                    continue
                evidence_record = evidence_by_id.get(str(record.get("source_evidence_id")))
                if evidence_record is None:
                    self._add(
                        issues,
                        "evidence",
                        "SOURCE_EVIDENCE_NOT_FOUND",
                        group_id,
                        "source_evidence_id does not resolve.",
                    )
                group["academic_review_record"] = copy.deepcopy(record)
                group["academic_review_status"] = record.get("review_status")
                group["academic_review_batch"] = str(
                    stats.get("batch_code") or path.name
                )
                group["source_evidence"] = copy.deepcopy(evidence_record)
                group["promotion_ready"] = record.get("promotion_ready") is True

        for group_id in sorted(all_ids & set(original_by_id)):
            for field in PRESERVED_STRUCTURAL_FIELDS:
                if original_by_id[group_id].get(field) != effective_by_id[group_id].get(field):
                    self._add(
                        issues,
                        "structural_integrity",
                        "STRUCTURAL_FIELD_CHANGED",
                        f"{group_id}.{field}",
                        "Academic review overlay changed a DATA-MATH12-006 field.",
                    )
        for group_id in sorted(set(original_by_id) - all_ids):
            if original_by_id[group_id] != effective_by_id[group_id]:
                self._add(
                    issues,
                    "patch_scope",
                    "UNSPECIFIED_GROUP_CHANGED",
                    group_id,
                    "Review overlay changed a group not named by the batch.",
                )

        expected_counts = {
            "target_groups": len(all_ids),
            "reviewed_groups": len(all_ids),
            "verified": len(ids["VERIFIED"]),
            "hold": len(ids["HOLD"]),
            "rejected": len(ids["REJECTED"]),
            "rejected_duplicate": sum(
                row.get("review_status") == "REJECTED_DUPLICATE_GROUP"
                for row in rejected
            ),
            "rejected_out_of_scope": sum(
                row.get("review_status") == "REJECTED_OUT_OF_SCOPE"
                for row in rejected
            ),
            "promotion_ready": sum(
                row.get("promotion_ready") is True
                for rows in records.values()
                for row in rows
            ),
        }
        for field, expected in expected_counts.items():
            if stats.get(field) != expected:
                self._add(
                    issues,
                    "review_stats",
                    "STAT_COUNT_MISMATCH",
                    f"review_stats.json.{field}",
                    f"Expected {expected}; found {stats.get(field)!r}.",
                )

        errors = tuple(sorted(set(issues)))
        return GroupReviewOverlayResult(
            groups=tuple(effective),
            report=GroupReviewBatchReport(
                batch_code=str(stats.get("batch_code") or path.name),
                path=path.as_posix(),
                status="PASS" if not errors else "FAIL",
                counts={
                    "reviewed": len(all_ids),
                    "verified": len(ids["VERIFIED"]),
                    "hold": len(ids["HOLD"]),
                    "rejected": len(ids["REJECTED"]),
                },
                reviewed_group_ids=tuple(sorted(all_ids)),
                errors=errors,
            ),
        )

    @staticmethod
    def _required_file_issues(path: Path) -> list[GroupReviewOverlayIssue]:
        return [
            GroupReviewOverlayIssue(
                check="batch_files",
                code="MISSING_FILE",
                location=name,
                message="Required group review batch file is missing.",
            )
            for name in REQUIRED_GROUP_REVIEW_FILES
            if not (path / name).is_file()
        ]

    @staticmethod
    def _load_json(path: Path, issues: list[GroupReviewOverlayIssue]) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            QuestionGroupReviewOverlayResolver._add(
                issues, "batch_files", "INVALID_JSON", path.name,
                f"Cannot read JSON: {error}.",
            )
            return None

    @classmethod
    def _load_list(
        cls, path: Path, issues: list[GroupReviewOverlayIssue]
    ) -> list[dict[str, Any]]:
        value = cls._load_json(path, issues)
        if isinstance(value, list) and all(isinstance(row, dict) for row in value):
            return value
        if value is not None:
            cls._add(issues, "batch_files", "INVALID_JSON_SHAPE", path.name,
                     "Expected an array of objects.")
        return []

    @classmethod
    def _load_object(
        cls, path: Path, issues: list[GroupReviewOverlayIssue]
    ) -> dict[str, Any]:
        value = cls._load_json(path, issues)
        if isinstance(value, dict):
            return value
        if value is not None:
            cls._add(issues, "batch_files", "INVALID_JSON_SHAPE", path.name,
                     "Expected an object.")
        return {}

    @classmethod
    def _groups_by_id(
        cls,
        groups: list[dict[str, Any]],
        label: str,
        issues: list[GroupReviewOverlayIssue],
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for index, group in enumerate(groups):
            group_id = group.get("group_candidate_id")
            if not isinstance(group_id, str) or not group_id:
                cls._add(issues, "group_references", "MISSING_GROUP_ID",
                         f"{label}[{index}]", "Group ID is required.")
            elif group_id in result:
                cls._add(issues, "group_references", "DUPLICATE_GROUP_ID",
                         group_id, "Group ID is duplicated.")
            else:
                result[group_id] = group
        return result

    @classmethod
    def _record_ids(
        cls,
        records: list[dict[str, Any]],
        label: str,
        issues: list[GroupReviewOverlayIssue],
    ) -> set[str]:
        result: set[str] = set()
        for index, record in enumerate(records):
            group_id = record.get("group_candidate_id")
            if not isinstance(group_id, str) or not group_id:
                cls._add(issues, "group_references", "MISSING_GROUP_ID",
                         f"{label}[{index}]", "Review group ID is required.")
            elif group_id in result:
                cls._add(issues, "group_references", "DUPLICATE_GROUP_ID",
                         group_id, f"Group ID is duplicated in {label}.")
            else:
                result.add(group_id)
        return result

    @classmethod
    def _validate_disjoint(
        cls,
        ids: dict[str, set[str]],
        issues: list[GroupReviewOverlayIssue],
    ) -> None:
        names = tuple(ids)
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                for group_id in sorted(ids[left] & ids[right]):
                    cls._add(
                        issues,
                        "review_status",
                        "CONFLICTING_REVIEW_STATUS",
                        group_id,
                        f"Group appears in both {left} and {right}.",
                    )

    @staticmethod
    def _add(
        issues: list[GroupReviewOverlayIssue],
        check: str,
        code: str,
        location: str,
        message: str,
    ) -> None:
        issues.append(GroupReviewOverlayIssue(check, code, location, message))


class EffectiveQuestionGroupReviewMaterializer:
    """Compose valid group review batches in lexical order."""

    def materialize(
        self,
        structural_groups: list[dict[str, Any]],
        review_root: Path = DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
    ) -> EffectiveQuestionGroupReview:
        original = copy.deepcopy(structural_groups)
        effective = copy.deepcopy(structural_groups)
        reports: list[GroupReviewBatchReport] = []
        issues: list[GroupReviewOverlayIssue] = []
        reviewed_by_batch: dict[str, str] = {}
        batch_paths = (
            tuple(path for path in sorted(review_root.resolve().glob("batch_*")) if path.is_dir())
            if review_root.is_dir()
            else ()
        )
        for path in batch_paths:
            result = QuestionGroupReviewOverlayResolver().resolve(effective, path)
            reports.append(result.report)
            overlap = sorted(set(result.report.reviewed_group_ids) & set(reviewed_by_batch))
            for group_id in overlap:
                issues.append(GroupReviewOverlayIssue(
                    check="batch_overlap",
                    code="GROUP_REVIEW_BATCH_OVERLAP",
                    location=f"{path.name}/{group_id}",
                    message=f"Group was already reviewed by {reviewed_by_batch[group_id]}.",
                ))
            if result.report.is_valid and not overlap:
                effective = list(result.groups)
                reviewed_by_batch.update({
                    group_id: result.report.batch_code
                    for group_id in result.report.reviewed_group_ids
                })
        return EffectiveQuestionGroupReview(
            structural_groups=tuple(original),
            effective_groups=tuple(effective),
            review_batches=tuple(reports),
            issues=tuple(sorted(set(issues))),
        )
