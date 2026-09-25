from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.questions.effective_staging import effective_review_status
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    EXPECTED_LABELS,
    EXPECTED_RAW_CANDIDATE_SHA256,
    README_CONTENT,
    QuestionGroupStagingBuildError,
    QuestionGroupStagingBuilder,
)
from app.questions.question_type_resolution import (
    effective_question_type,
    requires_question_group,
)
from app.questions.staging_validator import (
    DEFAULT_CURRICULUM_STAGING_PATH,
    DEFAULT_QUESTION_STAGING_PATH,
    QuestionStagingValidator,
)


REQUIRED_GROUP_STAGING_FILES = (
    "README.md",
    "question_group_candidates.json",
    "structural_holds.json",
    "build_report.json",
)


@dataclass(frozen=True, slots=True, order=True)
class QuestionGroupStagingValidationIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class QuestionGroupStagingValidationReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    errors: tuple[QuestionGroupStagingValidationIssue, ...]
    build_report: dict[str, Any]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "errors": [asdict(error) for error in self.errors],
            "build_report": self.build_report,
        }


class QuestionGroupStagingValidator:
    """Read-only integrity checks for derived four-statement group staging."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_QUESTION_STAGING_PATH,
        curriculum_path: Path = DEFAULT_CURRICULUM_STAGING_PATH,
        group_staging_path: Path | None = None,
        review_root: Path | None = None,
    ) -> QuestionGroupStagingValidationReport:
        dataset_path = dataset_path.resolve()
        group_staging_path = (
            group_staging_path.resolve()
            if group_staging_path is not None
            else dataset_path / DEFAULT_QUESTION_GROUP_STAGING_PATH.name
        )
        issue_groups: dict[str, list[QuestionGroupStagingValidationIssue]] = {
            "required_files": [],
            "raw_staging_integrity": [],
            "upstream_staging": [],
            "generated_artifacts": [],
            "identifiers": [],
            "source_references": [],
            "group_structure": [],
            "selection_boundary": [],
            "provenance": [],
        }
        for name in REQUIRED_GROUP_STAGING_FILES:
            if not (group_staging_path / name).is_file():
                self._add(
                    issue_groups,
                    "required_files",
                    "MISSING_FILE",
                    name,
                    "Required derived question-group staging file is missing.",
                )

        raw_path = dataset_path / "candidate_questions.json"
        raw_sha256 = (
            hashlib.sha256(raw_path.read_bytes()).hexdigest()
            if raw_path.is_file()
            else ""
        )
        if raw_sha256 != EXPECTED_RAW_CANDIDATE_SHA256:
            self._add(
                issue_groups,
                "raw_staging_integrity",
                "RAW_CANDIDATE_SHA256_MISMATCH",
                raw_path.as_posix(),
                "Raw staging candidate file differs from the approved audit baseline.",
            )

        groups = self._load_list(
            group_staging_path / "question_group_candidates.json",
            issue_groups,
        )
        holds = self._load_list(
            group_staging_path / "structural_holds.json",
            issue_groups,
        )
        build_report = self._load_object(
            group_staging_path / "build_report.json",
            issue_groups,
        )

        upstream = QuestionStagingValidator().validate(
            dataset_path,
            curriculum_path,
            review_root,
        )
        if not upstream.is_valid:
            for issue in upstream.errors:
                self._add(
                    issue_groups,
                    "upstream_staging",
                    issue.code,
                    issue.location,
                    issue.message,
                )

        fresh = None
        try:
            fresh = QuestionGroupStagingBuilder().build(
                dataset_path,
                curriculum_path,
                review_root,
            )
        except (OSError, QuestionGroupStagingBuildError) as error:
            self._add(
                issue_groups,
                "upstream_staging",
                "FRESH_BUILD_FAILED",
                dataset_path.as_posix(),
                str(error),
            )
        if fresh is not None:
            expected_payloads = fresh.payloads()
            actual_payloads = {
                "question_group_candidates.json": groups,
                "structural_holds.json": holds,
                "build_report.json": build_report,
            }
            for name, expected in expected_payloads.items():
                if actual_payloads[name] != expected:
                    self._add(
                        issue_groups,
                        "generated_artifacts",
                        "GENERATED_ARTIFACT_STALE",
                        name,
                        "Generated artifact does not match a fresh in-memory build.",
                    )
            readme_path = group_staging_path / "README.md"
            if readme_path.is_file() and readme_path.read_text(
                encoding="utf-8"
            ) != README_CONTENT:
                self._add(
                    issue_groups,
                    "generated_artifacts",
                    "GENERATED_README_STALE",
                    "README.md",
                    "Generated README does not match the builder definition.",
                )

        raw_by_id = {
            str(candidate.get("candidate_id")): candidate
            for candidate in upstream.materialization.raw_candidates
            if isinstance(candidate.get("candidate_id"), str)
        }
        effective_by_id = {
            str(candidate.get("candidate_id")): candidate
            for candidate in upstream.materialization.effective_candidates
            if isinstance(candidate.get("candidate_id"), str)
        }
        group_ids: list[str] = []
        source_ids: list[str] = []
        for index, group in enumerate(groups):
            location = f"question_group_candidates.json[{index}]"
            group_id = group.get("group_candidate_id")
            source_id = group.get("source_candidate_id")
            if isinstance(group_id, str):
                group_ids.append(group_id)
            if isinstance(source_id, str):
                source_ids.append(source_id)
            source = effective_by_id.get(str(source_id))
            raw_source = raw_by_id.get(str(source_id))
            if source is None or raw_source is None:
                self._add(
                    issue_groups,
                    "source_references",
                    "SOURCE_CANDIDATE_NOT_FOUND",
                    location,
                    f"Source candidate {source_id!r} does not resolve.",
                )
                continue
            expected_group_id = QuestionGroupStagingBuilder.group_candidate_id(
                str(source_id)
            )
            if group_id != expected_group_id:
                self._add(
                    issue_groups,
                    "identifiers",
                    "NON_DETERMINISTIC_GROUP_ID",
                    location,
                    f"Expected {expected_group_id}; found {group_id!r}.",
                )
            if effective_review_status(source) == "REJECTED":
                self._add(
                    issue_groups,
                    "selection_boundary",
                    "REJECTED_SOURCE_EMITTED",
                    location,
                    "Rejected candidates cannot be emitted as groups.",
                )
            if effective_question_type(source) == "MULTIPLE_CHOICE":
                self._add(
                    issue_groups,
                    "selection_boundary",
                    "REVIEWED_MCQ_EMITTED",
                    location,
                    "A reviewed MULTIPLE_CHOICE candidate cannot become a group.",
                )
            if not requires_question_group(source):
                self._add(
                    issue_groups,
                    "selection_boundary",
                    "SOURCE_DOES_NOT_REQUIRE_GROUP",
                    location,
                    "Source candidate does not require the QuestionGroup model.",
                )
            self._validate_provenance(
                group,
                source,
                raw_source,
                location,
                issue_groups,
            )
            self._validate_group_structure(group, location, issue_groups)

        self._validate_unique(
            group_ids,
            "group_candidate_id",
            "DUPLICATE_GROUP_ID",
            issue_groups,
        )
        self._validate_unique(
            source_ids,
            "source_candidate_id",
            "DUPLICATE_SOURCE_CANDIDATE_ID",
            issue_groups,
        )

        hold_source_ids: list[str] = []
        for index, hold in enumerate(holds):
            location = f"structural_holds.json[{index}]"
            source_id = hold.get("source_candidate_id")
            if isinstance(source_id, str):
                hold_source_ids.append(source_id)
            source = effective_by_id.get(str(source_id))
            raw_source = raw_by_id.get(str(source_id))
            if source is None or raw_source is None:
                self._add(
                    issue_groups,
                    "source_references",
                    "HOLD_SOURCE_CANDIDATE_NOT_FOUND",
                    location,
                    f"Hold source candidate {source_id!r} does not resolve.",
                )
                continue
            self._validate_provenance(
                hold,
                source,
                raw_source,
                location,
                issue_groups,
            )
        self._validate_unique(
            hold_source_ids,
            "hold source_candidate_id",
            "DUPLICATE_HOLD_SOURCE_ID",
            issue_groups,
        )
        overlap = sorted(set(source_ids) & set(hold_source_ids))
        for candidate_id in overlap:
            self._add(
                issue_groups,
                "selection_boundary",
                "GROUP_HOLD_OVERLAP",
                candidate_id,
                "A source candidate cannot be both emitted and structurally held.",
            )

        active_ids = {
            str(candidate["candidate_id"])
            for candidate in upstream.materialization.effective_candidates
            if effective_review_status(candidate) != "REJECTED"
            and requires_question_group(candidate)
        }
        accounted_ids = set(source_ids) | set(hold_source_ids)
        if active_ids != accounted_ids:
            self._add(
                issue_groups,
                "selection_boundary",
                "ACTIVE_GROUP_INPUT_COVERAGE_MISMATCH",
                "derived staging",
                (
                    f"missing={sorted(active_ids - accounted_ids)}, "
                    f"unexpected={sorted(accounted_ids - active_ids)}."
                ),
            )

        checks = {
            name: not issues for name, issues in issue_groups.items()
        }
        errors = tuple(
            sorted({issue for issues in issue_groups.values() for issue in issues})
        )
        child_count = sum(
            len(items)
            for group in groups
            if isinstance((items := group.get("items")), list)
        )
        assigned_answers = sum(
            item.get("correct_answer") is not None
            for group in groups
            if isinstance(group.get("items"), list)
            for item in group["items"]
            if isinstance(item, dict)
        )
        return QuestionGroupStagingValidationReport(
            dataset_path=group_staging_path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts={
                "groups": len(groups),
                "structural_holds": len(holds),
                "child_statements": child_count,
                "assigned_child_answers": assigned_answers,
            },
            errors=errors,
            build_report=build_report,
        )

    @staticmethod
    def _load_list(
        path: Path,
        issues: dict[str, list[QuestionGroupStagingValidationIssue]],
    ) -> list[dict[str, Any]]:
        value = QuestionGroupStagingValidator._load_json(path, issues)
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
        if value is not None:
            QuestionGroupStagingValidator._add(
                issues,
                "generated_artifacts",
                "INVALID_JSON_SHAPE",
                path.name,
                "Expected a JSON array of objects.",
            )
        return []

    @staticmethod
    def _load_object(
        path: Path,
        issues: dict[str, list[QuestionGroupStagingValidationIssue]],
    ) -> dict[str, Any]:
        value = QuestionGroupStagingValidator._load_json(path, issues)
        if isinstance(value, dict):
            return value
        if value is not None:
            QuestionGroupStagingValidator._add(
                issues,
                "generated_artifacts",
                "INVALID_JSON_SHAPE",
                path.name,
                "Expected a JSON object.",
            )
        return {}

    @staticmethod
    def _load_json(
        path: Path,
        issues: dict[str, list[QuestionGroupStagingValidationIssue]],
    ) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            QuestionGroupStagingValidator._add(
                issues,
                "generated_artifacts",
                "INVALID_JSON",
                path.name,
                f"Cannot load JSON: {error}.",
            )
            return None

    @staticmethod
    def _validate_unique(
        values: list[str],
        location: str,
        code: str,
        issues: dict[str, list[QuestionGroupStagingValidationIssue]],
    ) -> None:
        duplicates = sorted({value for value in values if values.count(value) > 1})
        for value in duplicates:
            QuestionGroupStagingValidator._add(
                issues,
                "identifiers",
                code,
                location,
                f"Identifier is duplicated: {value}.",
            )

    @staticmethod
    def _validate_group_structure(
        group: dict[str, Any],
        location: str,
        issues: dict[str, list[QuestionGroupStagingValidationIssue]],
    ) -> None:
        items = group.get("items")
        if not isinstance(items, list) or len(items) != 4:
            QuestionGroupStagingValidator._add(
                issues,
                "group_structure",
                "CHILD_COUNT_INVALID",
                location,
                "Each group must contain exactly four child statements.",
            )
            return
        labels = [item.get("label") for item in items if isinstance(item, dict)]
        indexes = [
            item.get("order_index") for item in items if isinstance(item, dict)
        ]
        if labels != list(EXPECTED_LABELS):
            QuestionGroupStagingValidator._add(
                issues,
                "group_structure",
                "CHILD_LABELS_INVALID",
                location,
                f"Expected labels {list(EXPECTED_LABELS)}; found {labels}.",
            )
        if indexes != list(range(4)):
            QuestionGroupStagingValidator._add(
                issues,
                "group_structure",
                "CHILD_ORDER_INVALID",
                location,
                f"Expected order indexes [0, 1, 2, 3]; found {indexes}.",
            )
        for index, item in enumerate(items):
            item_location = f"{location}.items[{index}]"
            if not isinstance(item, dict):
                QuestionGroupStagingValidator._add(
                    issues,
                    "group_structure",
                    "CHILD_INVALID",
                    item_location,
                    "Child statement must be an object.",
                )
                continue
            if not isinstance(item.get("content"), str) or not item["content"]:
                QuestionGroupStagingValidator._add(
                    issues,
                    "group_structure",
                    "CHILD_CONTENT_EMPTY",
                    item_location,
                    "Child statement content must be non-empty.",
                )
            if item.get("correct_answer") is not None:
                QuestionGroupStagingValidator._add(
                    issues,
                    "group_structure",
                    "CHILD_ANSWER_ASSIGNED",
                    item_location,
                    "Structural staging must not assign TRUE/FALSE answers.",
                )
        if not isinstance(group.get("group_context"), str) or not group[
            "group_context"
        ]:
            QuestionGroupStagingValidator._add(
                issues,
                "group_structure",
                "GROUP_CONTEXT_EMPTY",
                location,
                "Group context must be non-empty.",
            )

    @staticmethod
    def _validate_provenance(
        record: dict[str, Any],
        source: dict[str, Any],
        raw_source: dict[str, Any],
        location: str,
        issues: dict[str, list[QuestionGroupStagingValidationIssue]],
    ) -> None:
        expected = QuestionGroupStagingBuilder._provenance(source)
        for field, value in expected.items():
            if record.get(field) != value:
                QuestionGroupStagingValidator._add(
                    issues,
                    "provenance",
                    "SOURCE_PROVENANCE_MISMATCH",
                    f"{location}.{field}",
                    f"Expected {value!r}; found {record.get(field)!r}.",
                )
        if record.get("source_fingerprint") != raw_source.get("fingerprint"):
            QuestionGroupStagingValidator._add(
                issues,
                "provenance",
                "RAW_FINGERPRINT_MISMATCH",
                location,
                "Derived source fingerprint does not match immutable raw staging.",
            )

    @staticmethod
    def _add(
        issues: dict[str, list[QuestionGroupStagingValidationIssue]],
        check: str,
        code: str,
        location: str,
        message: str,
    ) -> None:
        issues[check].append(QuestionGroupStagingValidationIssue(
            check=check,
            code=code,
            location=location,
            message=message,
        ))
