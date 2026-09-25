from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.questions.effective_staging import effective_review_status
from app.questions.question_type_resolution import (
    effective_question_type,
    requires_question_group,
)
from app.questions.staging_validator import (
    DEFAULT_CURRICULUM_STAGING_PATH,
    DEFAULT_QUESTION_STAGING_PATH,
    QuestionStagingValidator,
)


DATASET_CODE = "DATA-MATH12-006"
GENERATED_VERSION = "question_groups_v0_1"
EXPECTED_RAW_CANDIDATE_SHA256 = (
    "b627a458e0b18c0a4e0733e18864e0bd83165f94894a7d690e4fc1313f3ed4d5"
)
DEFAULT_QUESTION_GROUP_STAGING_PATH = (
    DEFAULT_QUESTION_STAGING_PATH / GENERATED_VERSION
)
EXPECTED_LABELS = ("a", "b", "c", "d")
SOURCE_PAGE_REVIEW_REQUIRED = "SOURCE_PAGE_REVIEW_REQUIRED"
README_CONTENT = """# DATA-MATH12-006 — QuestionGroup structural staging

This directory is generated deterministically from the effective reviewed question
staging view. It is an auditable structural split only and is not production seed data.

- Parent ProblemType, Concept, and LearningOutcome mappings are retained only as source
  provenance. Child taxonomy remains `REVIEW_REQUIRED`.
- Child TRUE/FALSE answers are deliberately unset and remain `UNREVIEWED`.
- Structural holds require source-page review and are not emitted as valid groups.
- No record in this directory is production-promotable without a separate academic
  review and promotion workflow.
"""


@dataclass(frozen=True, slots=True)
class GroupStructureIssue:
    code: str
    observed_labels: tuple[str, ...]
    reason: str
    action: str = SOURCE_PAGE_REVIEW_REQUIRED


@dataclass(frozen=True, slots=True)
class ParsedQuestionGroup:
    group_context: str | None
    statements: tuple[str, ...]
    issue: GroupStructureIssue | None

    @property
    def is_valid(self) -> bool:
        return self.issue is None


class QuestionGroupStructureParser:
    """Split only explicit lower-case a/b/c/d structure; never infer content."""

    _marker = re.compile(
        r"(?:(?<![\w])\(([a-d])\)|(?<![\w(])([a-d])\))"
    )

    def parse(self, raw_question_text: str) -> ParsedQuestionGroup:
        matches = tuple(self._marker.finditer(raw_question_text))
        labels = tuple(match.group(1) or match.group(2) for match in matches)
        duplicate_labels = len(labels) != len(set(labels))
        if duplicate_labels:
            return self._invalid(
                "MARKERS_DUPLICATED",
                labels,
                "Lower-case statement markers must occur exactly once.",
            )
        if len(labels) != 4 or set(labels) != set(EXPECTED_LABELS):
            return self._invalid(
                "MARKERS_MISSING",
                labels,
                "Exactly one lower-case marker for each of a, b, c, d is required.",
            )
        if labels != EXPECTED_LABELS:
            return self._invalid(
                "LABEL_ORDER_INVALID",
                labels,
                "Statement labels must remain in extracted order a, b, c, d.",
            )

        context = raw_question_text[: matches[0].start()].strip()
        if not context:
            return self._invalid(
                "EMPTY_GROUP_CONTEXT",
                labels,
                "Text before the first statement marker is empty.",
            )
        statements = tuple(
            raw_question_text[
                match.end() : matches[index + 1].start()
                if index + 1 < len(matches)
                else len(raw_question_text)
            ].strip()
            for index, match in enumerate(matches)
        )
        if any(not statement for statement in statements):
            return ParsedQuestionGroup(
                group_context=context,
                statements=statements,
                issue=GroupStructureIssue(
                    code="EMPTY_STATEMENT",
                    observed_labels=labels,
                    reason="Every statement marker must have non-empty source text.",
                ),
            )
        return ParsedQuestionGroup(
            group_context=context,
            statements=statements,
            issue=None,
        )

    @staticmethod
    def _invalid(
        code: str,
        labels: tuple[str, ...],
        reason: str,
    ) -> ParsedQuestionGroup:
        return ParsedQuestionGroup(
            group_context=None,
            statements=(),
            issue=GroupStructureIssue(
                code=code,
                observed_labels=labels,
                reason=reason,
            ),
        )


@dataclass(frozen=True, slots=True)
class QuestionGroupStagingBuild:
    groups: tuple[dict[str, Any], ...]
    structural_holds: tuple[dict[str, Any], ...]
    report: dict[str, Any]

    def payloads(self) -> dict[str, Any]:
        return {
            "question_group_candidates.json": list(self.groups),
            "structural_holds.json": list(self.structural_holds),
            "build_report.json": self.report,
        }


class QuestionGroupStagingBuildError(ValueError):
    pass


class QuestionGroupStagingBuilder:
    def __init__(self, parser: QuestionGroupStructureParser | None = None) -> None:
        self._parser = parser or QuestionGroupStructureParser()

    def build(
        self,
        dataset_path: Path = DEFAULT_QUESTION_STAGING_PATH,
        curriculum_path: Path = DEFAULT_CURRICULUM_STAGING_PATH,
        review_root: Path | None = None,
    ) -> QuestionGroupStagingBuild:
        dataset_path = dataset_path.resolve()
        validation = QuestionStagingValidator().validate(
            dataset_path,
            curriculum_path,
            review_root,
        )
        if not validation.is_valid:
            codes = sorted({issue.code for issue in validation.errors})
            raise QuestionGroupStagingBuildError(
                f"Upstream question staging is invalid: {codes}."
            )

        raw_path = dataset_path / "candidate_questions.json"
        raw_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        if raw_sha256 != EXPECTED_RAW_CANDIDATE_SHA256:
            raise QuestionGroupStagingBuildError(
                "Raw candidate SHA-256 changed; derived staging build is blocked."
            )

        raw_candidates = list(validation.materialization.raw_candidates)
        effective_candidates = list(
            validation.materialization.effective_candidates
        )
        raw_by_id = {
            str(candidate["candidate_id"]): candidate
            for candidate in raw_candidates
        }
        active_candidates = sorted(
            (
                candidate
                for candidate in effective_candidates
                if effective_review_status(candidate) != "REJECTED"
                and requires_question_group(candidate)
            ),
            key=lambda candidate: str(candidate["candidate_id"]),
        )

        groups: list[dict[str, Any]] = []
        holds: list[dict[str, Any]] = []
        for candidate in active_candidates:
            parsed = self._parser.parse(str(candidate.get("raw_question_text") or ""))
            if parsed.issue is not None:
                holds.append(self._hold(candidate, parsed.issue))
            else:
                groups.append(self._group(candidate, parsed))

        raw_true_false_group_detected = sum(
            candidate.get("question_type_detected") == "TRUE_FALSE_GROUP"
            for candidate in raw_candidates
        )
        review_reclassified_group_to_mcq = sum(
            raw_by_id[str(candidate["candidate_id"])].get(
                "question_type_detected"
            )
            == "TRUE_FALSE_GROUP"
            and effective_question_type(candidate) == "MULTIPLE_CHOICE"
            for candidate in effective_candidates
        )
        rejected_raw_group_duplicates = sum(
            raw_by_id[str(candidate["candidate_id"])].get(
                "question_type_detected"
            )
            == "TRUE_FALSE_GROUP"
            and effective_review_status(candidate) == "REJECTED"
            and self._source_review_status(candidate) == "REJECTED_DUPLICATE"
            for candidate in effective_candidates
        )
        review_added_group_requirement = sum(
            raw_by_id[str(candidate["candidate_id"])].get(
                "question_type_detected"
            )
            != "TRUE_FALSE_GROUP"
            and effective_review_status(candidate) != "REJECTED"
            and requires_question_group(candidate)
            for candidate in effective_candidates
        )
        child_count = sum(len(group["items"]) for group in groups)
        assigned_answers = sum(
            item["correct_answer"] is not None
            for group in groups
            for item in group["items"]
        )
        report = {
            "dataset_code": DATASET_CODE,
            "generated_version": GENERATED_VERSION,
            "source_review_batches": [
                batch.batch_code
                for batch in validation.materialization.review_batches
            ],
            "academic_verification_claimed": False,
            "production_importable": False,
            "source_raw_sha256": raw_sha256,
            "raw_candidates": len(raw_candidates),
            "raw_true_false_group_detected": raw_true_false_group_detected,
            "review_reclassified_group_to_mcq": review_reclassified_group_to_mcq,
            "rejected_raw_group_duplicates": rejected_raw_group_duplicates,
            "review_added_group_requirement_from_non_group_raw": (
                review_added_group_requirement
            ),
            "active_group_inputs": len(active_candidates),
            "emitted_groups": len(groups),
            "structural_holds": len(holds),
            "emitted_child_statements": child_count,
            "assigned_child_answers": assigned_answers,
        }
        if len(groups) + len(holds) != len(active_candidates):
            raise QuestionGroupStagingBuildError(
                "Every active group input must become one group or one structural hold."
            )
        if child_count != len(groups) * 4 or assigned_answers:
            raise QuestionGroupStagingBuildError(
                "QuestionGroup child structure or answer boundary is invalid."
            )
        return QuestionGroupStagingBuild(
            groups=tuple(groups),
            structural_holds=tuple(holds),
            report=report,
        )

    def write(
        self,
        build: QuestionGroupStagingBuild,
        output_path: Path = DEFAULT_QUESTION_GROUP_STAGING_PATH,
    ) -> None:
        output_path.mkdir(parents=True, exist_ok=True)
        self._write_text(output_path / "README.md", README_CONTENT)
        for name, payload in build.payloads().items():
            self._write_text(
                output_path / name,
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            )

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def group_candidate_id(candidate_id: str) -> str:
        if "_CAND_" not in candidate_id:
            raise QuestionGroupStagingBuildError(
                f"Cannot derive a group ID from candidate ID {candidate_id!r}."
            )
        return candidate_id.replace("_CAND_", "_GROUP_", 1)

    def _group(
        self,
        candidate: dict[str, Any],
        parsed: ParsedQuestionGroup,
    ) -> dict[str, Any]:
        candidate_id = str(candidate["candidate_id"])
        return {
            "group_candidate_id": self.group_candidate_id(candidate_id),
            "source_candidate_id": candidate_id,
            **self._provenance(candidate),
            "group_type": "TRUE_FALSE_FOUR",
            "group_context": parsed.group_context,
            "source_review_status": self._source_review_status(candidate),
            "problem_type_code": candidate.get("problem_type_code"),
            "parent_concepts": copy.deepcopy(candidate.get("concepts", [])),
            "parent_learning_outcomes": copy.deepcopy(
                candidate.get("learning_outcomes", [])
            ),
            "child_taxonomy_status": "REVIEW_REQUIRED",
            "items": [
                {
                    "label": label,
                    "order_index": index,
                    "content": parsed.statements[index],
                    "correct_answer": None,
                    "answer_status": "UNREVIEWED",
                    "taxonomy_status": "REVIEW_REQUIRED",
                }
                for index, label in enumerate(EXPECTED_LABELS)
            ],
        }

    def _hold(
        self,
        candidate: dict[str, Any],
        issue: GroupStructureIssue,
    ) -> dict[str, Any]:
        return {
            "source_candidate_id": str(candidate["candidate_id"]),
            **self._provenance(candidate),
            "source_review_status": self._source_review_status(candidate),
            "hold_code": issue.code,
            "observed_labels": list(issue.observed_labels),
            "expected_labels": list(EXPECTED_LABELS),
            "reason": issue.reason,
            "action": issue.action,
        }

    @staticmethod
    def _provenance(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_fingerprint": candidate.get("fingerprint"),
            "source_code": candidate.get("source_code"),
            "raw_subsource_code": candidate.get("subsource_code"),
            "effective_subsource_code": candidate.get(
                "corrected_subsource_code",
                candidate.get("subsource_code"),
            ),
            "provenance_correction_code": candidate.get(
                "provenance_correction_code"
            ),
            "source_page": candidate.get("source_page"),
            "question_number": candidate.get("question_number"),
        }

    @staticmethod
    def _source_review_status(candidate: dict[str, Any]) -> str:
        review_record = candidate.get("review_record")
        review_status = (
            review_record.get("review_status")
            if isinstance(review_record, dict)
            else None
        )
        return (
            review_status
            if isinstance(review_status, str) and review_status
            else effective_review_status(candidate)
        )
