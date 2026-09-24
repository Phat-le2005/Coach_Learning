from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PRESERVED_CANDIDATE_FIELDS = (
    "source_code",
    "subsource_code",
    "source_page",
    "question_number",
    "fingerprint",
    "raw_question_text",
    "question_type_detected",
)
REQUIRED_BATCH_FILES = (
    "README.md",
    "candidate_patch.json",
    "hold_candidates.json",
    "rejected_candidates.json",
    "review_stats.json",
    "verified_candidates.json",
)


@dataclass(frozen=True, slots=True, order=True)
class ReviewOverlayIssue:
    check: str
    code: str
    candidate_id: str
    message: str


@dataclass(frozen=True, slots=True)
class ReviewBatchReport:
    batch_code: str
    path: str
    status: str
    counts: dict[str, int]
    reviewed_candidate_ids: tuple[str, ...]
    errors: tuple[ReviewOverlayIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_code": self.batch_code,
            "path": self.path,
            "status": self.status,
            "counts": self.counts,
            "reviewed_candidate_ids": list(self.reviewed_candidate_ids),
            "errors": [asdict(error) for error in self.errors],
        }


@dataclass(frozen=True, slots=True)
class ReviewOverlayResult:
    candidates: tuple[dict[str, Any], ...]
    report: ReviewBatchReport

    def candidate(self, candidate_id: str) -> dict[str, Any]:
        for candidate in self.candidates:
            if candidate.get("candidate_id") == candidate_id:
                return candidate
        raise KeyError(candidate_id)


class QuestionReviewOverlayResolver:
    """Apply an auditable review batch to an in-memory copy of staging candidates."""

    def resolve(
        self,
        raw_candidates: list[dict[str, Any]],
        batch_path: Path,
    ) -> ReviewOverlayResult:
        path = batch_path.resolve()
        issues = self._required_file_issues(path)
        verified = self._load_list(path / "verified_candidates.json", issues)
        holds = self._load_list(path / "hold_candidates.json", issues)
        rejected = self._load_list(path / "rejected_candidates.json", issues)
        patches = self._load_list(path / "candidate_patch.json", issues)
        stats = self._load_object(path / "review_stats.json", issues)

        raw_by_id = {
            candidate_id: candidate
            for candidate in raw_candidates
            if isinstance((candidate_id := candidate.get("candidate_id")), str)
        }
        reviewed = copy.deepcopy(raw_candidates)
        reviewed_by_id = {
            candidate["candidate_id"]: candidate
            for candidate in reviewed
            if isinstance(candidate.get("candidate_id"), str)
        }

        groups = {
            "VERIFIED": verified,
            "HOLD": holds,
            "REJECTED": rejected,
        }
        group_ids = {
            name: self._record_ids(records, name, issues)
            for name, records in groups.items()
        }
        patch_ids = self._record_ids(patches, "PATCH", issues)
        all_referenced_ids = set().union(*group_ids.values(), patch_ids)
        for candidate_id in sorted(all_referenced_ids - set(raw_by_id)):
            issues.append(ReviewOverlayIssue(
                check="candidate_references",
                code="CANDIDATE_NOT_FOUND",
                candidate_id=candidate_id,
                message="Review candidate ID does not exist in staging data.",
            ))

        self._validate_disjoint_groups(group_ids, issues)
        expected_patch_ids = group_ids["VERIFIED"] | group_ids["REJECTED"]
        if patch_ids != expected_patch_ids:
            issues.append(ReviewOverlayIssue(
                check="patch_scope",
                code="PATCH_SCOPE_MISMATCH",
                candidate_id="<batch>",
                message=(
                    "Patch IDs must exactly match VERIFIED and REJECTED candidate IDs; "
                    f"missing={sorted(expected_patch_ids - patch_ids)}, "
                    f"unexpected={sorted(patch_ids - expected_patch_ids)}."
                ),
            ))

        for patch_index, patch in enumerate(patches):
            candidate_id = patch.get("candidate_id")
            values = patch.get("set")
            if not isinstance(candidate_id, str) or candidate_id not in reviewed_by_id:
                continue
            if not isinstance(values, dict):
                issues.append(ReviewOverlayIssue(
                    check="patch_shape",
                    code="INVALID_PATCH_SET",
                    candidate_id=candidate_id,
                    message=f"candidate_patch.json[{patch_index}].set must be an object.",
                ))
                continue
            protected = sorted(set(values) & set(PRESERVED_CANDIDATE_FIELDS))
            if protected:
                issues.append(ReviewOverlayIssue(
                    check="preserved_fields",
                    code="PROTECTED_FIELD_PATCH",
                    candidate_id=candidate_id,
                    message=f"Patch attempts to change preserved fields: {protected}.",
                ))
                continue
            reviewed_by_id[candidate_id].update(copy.deepcopy(values))

        records_by_id = {
            str(record["candidate_id"]): record
            for records in groups.values()
            for record in records
            if isinstance(record.get("candidate_id"), str)
        }
        for candidate_id, record in records_by_id.items():
            candidate = reviewed_by_id.get(candidate_id)
            if candidate is not None:
                candidate["review_record"] = copy.deepcopy(record)

        self._validate_preserved_fields(
            raw_by_id, reviewed_by_id, all_referenced_ids, issues
        )
        self._validate_unspecified_candidates(
            raw_by_id, reviewed_by_id, all_referenced_ids, issues
        )
        self._validate_record_provenance(
            raw_by_id, groups, issues
        )
        self._validate_verified(
            raw_by_id, reviewed_by_id, verified, patches, issues
        )
        self._validate_holds(reviewed_by_id, holds, issues)
        self._validate_rejected(reviewed_by_id, rejected, issues)
        self._validate_stats(
            stats, group_ids, rejected, len(raw_candidates), issues
        )

        batch_code = str(stats.get("batch_code") or path.name)
        counts = {
            "verified": len(group_ids["VERIFIED"]),
            "hold": len(group_ids["HOLD"]),
            "rejected": len(group_ids["REJECTED"]),
            "reviewed": len(
                group_ids["VERIFIED"] | group_ids["HOLD"] | group_ids["REJECTED"]
            ),
        }
        sorted_issues = tuple(sorted(set(issues)))
        return ReviewOverlayResult(
            candidates=tuple(reviewed),
            report=ReviewBatchReport(
                batch_code=batch_code,
                path=path.as_posix(),
                status="PASS" if not sorted_issues else "FAIL",
                counts=counts,
                reviewed_candidate_ids=tuple(sorted(
                    group_ids["VERIFIED"] | group_ids["HOLD"] | group_ids["REJECTED"]
                )),
                errors=sorted_issues,
            ),
        )

    @staticmethod
    def _required_file_issues(path: Path) -> list[ReviewOverlayIssue]:
        return [
            ReviewOverlayIssue(
                check="batch_files",
                code="MISSING_FILE",
                candidate_id="<batch>",
                message=f"Required review batch file is missing: {name}.",
            )
            for name in REQUIRED_BATCH_FILES
            if not (path / name).is_file()
        ]

    @staticmethod
    def _load_json(path: Path, issues: list[ReviewOverlayIssue]) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            issues.append(ReviewOverlayIssue(
                check="batch_files",
                code="INVALID_JSON",
                candidate_id="<batch>",
                message=f"Cannot load {path.name}: {error}.",
            ))
            return None

    def _load_list(
        self, path: Path, issues: list[ReviewOverlayIssue]
    ) -> list[dict[str, Any]]:
        value = self._load_json(path, issues)
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
        if value is not None:
            issues.append(ReviewOverlayIssue(
                check="batch_files",
                code="INVALID_JSON_SHAPE",
                candidate_id="<batch>",
                message=f"{path.name} must contain an array of objects.",
            ))
        return []

    def _load_object(
        self, path: Path, issues: list[ReviewOverlayIssue]
    ) -> dict[str, Any]:
        value = self._load_json(path, issues)
        if isinstance(value, dict):
            return value
        if value is not None:
            issues.append(ReviewOverlayIssue(
                check="batch_files",
                code="INVALID_JSON_SHAPE",
                candidate_id="<batch>",
                message=f"{path.name} must contain an object.",
            ))
        return {}

    @staticmethod
    def _record_ids(
        records: list[dict[str, Any]],
        label: str,
        issues: list[ReviewOverlayIssue],
    ) -> set[str]:
        result: set[str] = set()
        for index, record in enumerate(records):
            candidate_id = record.get("candidate_id")
            if not isinstance(candidate_id, str) or not candidate_id:
                issues.append(ReviewOverlayIssue(
                    check="candidate_references",
                    code="MISSING_CANDIDATE_ID",
                    candidate_id="<missing>",
                    message=f"{label} record {index} has no candidate_id.",
                ))
            elif candidate_id in result:
                issues.append(ReviewOverlayIssue(
                    check="candidate_references",
                    code="DUPLICATE_CANDIDATE_ID",
                    candidate_id=candidate_id,
                    message=f"Candidate is duplicated in {label} records.",
                ))
            else:
                result.add(candidate_id)
        return result

    @staticmethod
    def _validate_disjoint_groups(
        group_ids: dict[str, set[str]],
        issues: list[ReviewOverlayIssue],
    ) -> None:
        names = tuple(group_ids)
        for left_index, left in enumerate(names):
            for right in names[left_index + 1:]:
                for candidate_id in sorted(group_ids[left] & group_ids[right]):
                    issues.append(ReviewOverlayIssue(
                        check="review_status",
                        code="CONFLICTING_REVIEW_STATUS",
                        candidate_id=candidate_id,
                        message=f"Candidate appears in both {left} and {right} records.",
                    ))

    @staticmethod
    def _validate_preserved_fields(
        raw_by_id: dict[str, dict[str, Any]],
        reviewed_by_id: dict[str, dict[str, Any]],
        reviewed_ids: set[str],
        issues: list[ReviewOverlayIssue],
    ) -> None:
        for candidate_id in sorted(reviewed_ids & set(raw_by_id)):
            for field in PRESERVED_CANDIDATE_FIELDS:
                if raw_by_id[candidate_id].get(field) != reviewed_by_id[candidate_id].get(field):
                    issues.append(ReviewOverlayIssue(
                        check="preserved_fields",
                        code="PRESERVED_FIELD_CHANGED",
                        candidate_id=candidate_id,
                        message=f"Review overlay changed preserved field {field}.",
                    ))

    @staticmethod
    def _validate_unspecified_candidates(
        raw_by_id: dict[str, dict[str, Any]],
        reviewed_by_id: dict[str, dict[str, Any]],
        reviewed_ids: set[str],
        issues: list[ReviewOverlayIssue],
    ) -> None:
        for candidate_id in sorted(set(raw_by_id) - reviewed_ids):
            if raw_by_id[candidate_id] != reviewed_by_id[candidate_id]:
                issues.append(ReviewOverlayIssue(
                    check="patch_scope",
                    code="UNSPECIFIED_CANDIDATE_CHANGED",
                    candidate_id=candidate_id,
                    message="Review overlay changed a candidate not named in this batch.",
                ))

    @staticmethod
    def _validate_record_provenance(
        raw_by_id: dict[str, dict[str, Any]],
        groups: dict[str, list[dict[str, Any]]],
        issues: list[ReviewOverlayIssue],
    ) -> None:
        for records in groups.values():
            for record in records:
                candidate_id = record.get("candidate_id")
                raw = raw_by_id.get(candidate_id) if isinstance(candidate_id, str) else None
                if raw is None:
                    continue
                for field in ("source_code", "subsource_code", "source_page", "question_number"):
                    if record.get(field) != raw.get(field):
                        issues.append(ReviewOverlayIssue(
                            check="preserved_fields",
                            code="REVIEW_PROVENANCE_MISMATCH",
                            candidate_id=candidate_id,
                            message=f"Review record does not match raw {field}.",
                        ))

    @staticmethod
    def _patches_by_id(
        patches: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        return {
            str(patch["candidate_id"]): patch["set"]
            for patch in patches
            if isinstance(patch.get("candidate_id"), str)
            and isinstance(patch.get("set"), dict)
        }

    def _validate_verified(
        self,
        raw_by_id: dict[str, dict[str, Any]],
        reviewed_by_id: dict[str, dict[str, Any]],
        verified: list[dict[str, Any]],
        patches: list[dict[str, Any]],
        issues: list[ReviewOverlayIssue],
    ) -> None:
        patches_by_id = self._patches_by_id(patches)
        required_text = (
            "reviewed_content",
            "verified_correct_answer",
            "answer_verification",
            "taxonomy_review",
            "content_review",
        )
        mirrored_patch_fields = (
            "reviewed_question_type",
            "reviewed_content",
            "reviewed_options",
            "verified_correct_answer",
        )
        validates_visual_assets = any(
            "visual_asset_required" in record for record in verified
        )
        for record in verified:
            candidate_id = record.get("candidate_id")
            if not isinstance(candidate_id, str):
                continue
            patch = patches_by_id.get(candidate_id, {})
            raw = raw_by_id.get(candidate_id)
            view = reviewed_by_id.get(candidate_id)
            if raw is None or view is None:
                continue
            if record.get("review_status") != "VERIFIED" or view.get("status") != "VERIFIED":
                issues.append(ReviewOverlayIssue(
                    check="verified_review",
                    code="INVALID_VERIFIED_STATUS",
                    candidate_id=candidate_id,
                    message="VERIFIED record and reviewed view must both be VERIFIED.",
                ))
            for field in required_text:
                if not isinstance(record.get(field), str) or not record[field]:
                    issues.append(ReviewOverlayIssue(
                        check="verified_review",
                        code="MISSING_VERIFIED_REVIEW_FIELD",
                        candidate_id=candidate_id,
                        message=f"VERIFIED review requires {field}.",
                    ))
            if record.get("taxonomy_review") != "CONFIRMED":
                issues.append(ReviewOverlayIssue(
                    check="verified_review",
                    code="TAXONOMY_REVIEW_NOT_CONFIRMED",
                    candidate_id=candidate_id,
                    message="VERIFIED candidate taxonomy review must be CONFIRMED.",
                ))
            if record.get("content_review") != "CONFIRMED_AGAINST_SOURCE_PAGE":
                issues.append(ReviewOverlayIssue(
                    check="verified_review",
                    code="CONTENT_REVIEW_NOT_CONFIRMED",
                    candidate_id=candidate_id,
                    message="VERIFIED candidate content review must be confirmed against source.",
                ))
            if record.get("answer_verification") != (
                "SOURCE_SOLUTION_CONFIRMED_AND_INDEPENDENT_CHECK"
            ):
                issues.append(ReviewOverlayIssue(
                    check="verified_review",
                    code="ANSWER_REVIEW_NOT_CONFIRMED",
                    candidate_id=candidate_id,
                    message="VERIFIED candidate answer requires source and independent checks.",
                ))
            if not isinstance(record.get("concepts"), list) or not record["concepts"]:
                issues.append(ReviewOverlayIssue(
                    check="verified_review",
                    code="MISSING_REVIEWED_CONCEPTS",
                    candidate_id=candidate_id,
                    message="VERIFIED candidate requires reviewed Concept mappings.",
                ))
            if not isinstance(record.get("learning_outcomes"), list) or not record["learning_outcomes"]:
                issues.append(ReviewOverlayIssue(
                    check="verified_review",
                    code="MISSING_REVIEWED_LEARNING_OUTCOMES",
                    candidate_id=candidate_id,
                    message="VERIFIED candidate requires reviewed LearningOutcome mappings.",
                ))
            if record.get("promotion_ready") is not False or patch.get("promotion_ready") is not False:
                issues.append(ReviewOverlayIssue(
                    check="promotion_boundary",
                    code="VERIFIED_PROMOTION_NOT_BLOCKED",
                    candidate_id=candidate_id,
                    message="VERIFIED review records must remain blocked from promotion.",
                ))
            if validates_visual_assets:
                if (
                    record.get("visual_asset_required") is not True
                    or patch.get("visual_asset_required") is not True
                ):
                    issues.append(ReviewOverlayIssue(
                        check="promotion_boundary",
                        code="VISUAL_ASSET_REQUIREMENT_MISSING",
                        candidate_id=candidate_id,
                        message=(
                            "Every VERIFIED candidate in this visual review batch must "
                            "require a visual asset."
                        ),
                    ))
                if (
                    not isinstance(record.get("visual_source_page"), int)
                    or patch.get("visual_source_page") != record.get("visual_source_page")
                ):
                    issues.append(ReviewOverlayIssue(
                        check="patch_consistency",
                        code="VISUAL_SOURCE_PAGE_MISMATCH",
                        candidate_id=candidate_id,
                        message=(
                            "Verified review and patch must identify the same visual "
                            "source page."
                        ),
                    ))
            if record.get("original_fingerprint") != raw.get("fingerprint"):
                issues.append(ReviewOverlayIssue(
                    check="preserved_fields",
                    code="ORIGINAL_FINGERPRINT_MISMATCH",
                    candidate_id=candidate_id,
                    message="Review original_fingerprint does not match raw fingerprint.",
                ))
            for field in mirrored_patch_fields:
                if patch.get(field) != record.get(field):
                    issues.append(ReviewOverlayIssue(
                        check="patch_consistency",
                        code="PATCH_REVIEW_MISMATCH",
                        candidate_id=candidate_id,
                        message=f"Patch {field} does not match verified review record.",
                    ))
            if record.get("problem_type_code") != raw.get("problem_type_code"):
                issues.append(ReviewOverlayIssue(
                    check="verified_review",
                    code="REVIEWED_PROBLEM_TYPE_MISMATCH",
                    candidate_id=candidate_id,
                    message="Reviewed ProblemType does not match the staging classification.",
                ))
            if record.get("concepts") != raw.get("concepts"):
                issues.append(ReviewOverlayIssue(
                    check="verified_review",
                    code="REVIEWED_CONCEPTS_MISMATCH",
                    candidate_id=candidate_id,
                    message="Reviewed Concept mappings do not match staging mappings.",
                ))
            if record.get("learning_outcomes") != raw.get("learning_outcomes"):
                issues.append(ReviewOverlayIssue(
                    check="verified_review",
                    code="REVIEWED_LEARNING_OUTCOMES_MISMATCH",
                    candidate_id=candidate_id,
                    message="Reviewed LearningOutcome mappings do not match staging mappings.",
                ))

    @staticmethod
    def _validate_holds(
        reviewed_by_id: dict[str, dict[str, Any]],
        holds: list[dict[str, Any]],
        issues: list[ReviewOverlayIssue],
    ) -> None:
        for record in holds:
            candidate_id = record.get("candidate_id")
            view = reviewed_by_id.get(candidate_id) if isinstance(candidate_id, str) else None
            if view is None:
                continue
            if (
                record.get("status_after_review") != "REVIEW_REQUIRED"
                or view.get("status") != "REVIEW_REQUIRED"
                or not str(record.get("review_status", "")).startswith("HOLD_")
            ):
                issues.append(ReviewOverlayIssue(
                    check="promotion_boundary",
                    code="INVALID_HOLD_STATUS",
                    candidate_id=candidate_id,
                    message="HOLD candidate must remain REVIEW_REQUIRED.",
                ))

    @staticmethod
    def _validate_rejected(
        reviewed_by_id: dict[str, dict[str, Any]],
        rejected: list[dict[str, Any]],
        issues: list[ReviewOverlayIssue],
    ) -> None:
        for record in rejected:
            candidate_id = record.get("candidate_id")
            view = reviewed_by_id.get(candidate_id) if isinstance(candidate_id, str) else None
            if view is None:
                continue
            if (
                record.get("status_after_review") != "REJECTED"
                or view.get("status") != "REJECTED"
                or not str(record.get("review_status", "")).startswith("REJECTED")
            ):
                issues.append(ReviewOverlayIssue(
                    check="promotion_boundary",
                    code="INVALID_REJECTED_STATUS",
                    candidate_id=candidate_id,
                    message="REJECTED candidate must remain rejected.",
                ))
            if record.get("review_status") == "REJECTED_DUPLICATE":
                duplicate_of = record.get("duplicate_of_candidate_id")
                if (
                    not isinstance(duplicate_of, str)
                    or duplicate_of not in reviewed_by_id
                    or duplicate_of == candidate_id
                ):
                    issues.append(ReviewOverlayIssue(
                        check="duplicate_references",
                        code="DUPLICATE_TARGET_NOT_FOUND",
                        candidate_id=candidate_id,
                        message=(
                            "REJECTED_DUPLICATE must reference another candidate in "
                            "the staging dataset."
                        ),
                    ))

    @staticmethod
    def _validate_stats(
        stats: dict[str, Any],
        group_ids: dict[str, set[str]],
        rejected: list[dict[str, Any]],
        total_candidates: int,
        issues: list[ReviewOverlayIssue],
    ) -> None:
        expected = {
            "verified": len(group_ids["VERIFIED"]),
            "hold": len(group_ids["HOLD"]),
            "rejected": len(group_ids["REJECTED"]),
            "reviewed_candidates": len(
                group_ids["VERIFIED"] | group_ids["HOLD"] | group_ids["REJECTED"]
            ),
            "total_candidates_in_data004": total_candidates,
        }
        rejected_status_counts = {
            status: sum(
                record.get("review_status") == status for record in rejected
            )
            for status in ("REJECTED_DUPLICATE", "REJECTED_OUT_OF_SCOPE")
        }
        optional_expected = {
            "rejected_duplicate": rejected_status_counts["REJECTED_DUPLICATE"],
            "rejected_out_of_scope": rejected_status_counts["REJECTED_OUT_OF_SCOPE"],
        }
        expected.update({
            field: value
            for field, value in optional_expected.items()
            if field in stats
        })
        for field, value in expected.items():
            if stats.get(field) != value:
                issues.append(ReviewOverlayIssue(
                    check="batch_counts",
                    code="REVIEW_STATS_MISMATCH",
                    candidate_id="<batch>",
                    message=f"review_stats.{field} must be {value}; found {stats.get(field)!r}.",
                ))
