from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.questions.question_group_review_overlay import (
    DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
    EffectiveQuestionGroupReview,
    EffectiveQuestionGroupReviewMaterializer,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    EXPECTED_LABELS,
    EXPECTED_RAW_CANDIDATE_SHA256,
)
from app.questions.question_group_staging_validator import (
    QuestionGroupStagingValidator,
)
from app.questions.staging_validator import DEFAULT_CURRICULUM_STAGING_PATH


EXPECTED_BATCH_CODE = "DATA-MATH12-007_BATCH_001"
EXPECTED_BASE_COMMIT = "41de2ae9aaa58ac1ffbc29a9304d9216dc270efb"
EXPECTED_ANSWER_PATTERNS = {
    "M12_DERIV_GROUP_0012": ("TRUE", "FALSE", "FALSE", "TRUE"),
    "M12_DERIV_GROUP_0019": ("TRUE", "FALSE", "FALSE", "TRUE"),
    "M12_DERIV_GROUP_0024": ("FALSE", "TRUE", "TRUE", "TRUE"),
    "M12_DERIV_GROUP_0031": ("FALSE", "TRUE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0035": ("TRUE", "FALSE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0041": ("TRUE", "FALSE", "TRUE", "TRUE"),
    "M12_DERIV_GROUP_0047": ("TRUE", "TRUE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0052": ("TRUE", "FALSE", "TRUE", "TRUE"),
}
EXPECTED_DUPLICATES = {
    "M12_DERIV_GROUP_0021": "M12_DERIV_GROUP_0019",
    "M12_DERIV_GROUP_0026": "M12_DERIV_GROUP_0024",
    "M12_DERIV_GROUP_0053": "M12_DERIV_GROUP_0052",
}
EXPECTED_OUT_OF_SCOPE = {
    "M12_DERIV_GROUP_0044",
    "M12_DERIV_GROUP_0055",
}
EXPECTED_VISUAL_GROUPS = {
    "M12_DERIV_GROUP_0012",
    "M12_DERIV_GROUP_0024",
}
EXPECTED_TARGET_IDS = (
    set(EXPECTED_ANSWER_PATTERNS) | set(EXPECTED_DUPLICATES) | EXPECTED_OUT_OF_SCOPE
)


@dataclass(frozen=True, slots=True, order=True)
class QuestionGroupReviewValidationIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class QuestionGroupReviewValidationReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    errors: tuple[QuestionGroupReviewValidationIssue, ...]
    review_batches: tuple[dict[str, Any], ...]
    materialization: EffectiveQuestionGroupReview

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
            "review_batches": list(self.review_batches),
        }


class QuestionGroupReviewValidator:
    """Validate academic overlays while keeping structural staging immutable."""

    def validate(
        self,
        group_staging_path: Path = DEFAULT_QUESTION_GROUP_STAGING_PATH,
        curriculum_path: Path = DEFAULT_CURRICULUM_STAGING_PATH,
        review_root: Path = DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
    ) -> QuestionGroupReviewValidationReport:
        group_staging_path = group_staging_path.resolve()
        curriculum_path = curriculum_path.resolve()
        review_root = review_root.resolve()
        issue_groups: dict[str, list[QuestionGroupReviewValidationIssue]] = {
            "structural_staging": [],
            "raw_integrity": [],
            "batch_overlay": [],
            "batch_acceptance": [],
            "source_evidence": [],
            "provenance": [],
            "review_content": [],
            "taxonomy": [],
            "duplicate_boundary": [],
            "promotion_boundary": [],
        }

        structural_report = QuestionGroupStagingValidator().validate(
            group_staging_path=group_staging_path,
        )
        if not structural_report.is_valid:
            self._add(
                issue_groups,
                "structural_staging",
                "DATA_006_VALIDATION_FAILED",
                group_staging_path.as_posix(),
                "DATA-MATH12-006 structural staging must pass before review overlays.",
            )
        expected_structural_counts = {
            "groups": 67,
            "structural_holds": 1,
            "child_statements": 268,
            "assigned_child_answers": 0,
        }
        if structural_report.counts != expected_structural_counts:
            self._add(
                issue_groups,
                "structural_staging",
                "DATA_006_COUNTS_CHANGED",
                "question_groups_v0_1",
                f"Expected {expected_structural_counts}; found {structural_report.counts}.",
            )

        structural_groups = self._load_list(
            group_staging_path / "question_group_candidates.json",
            issue_groups,
            "structural_staging",
        )
        structural_snapshot = json.dumps(
            structural_groups, ensure_ascii=False, sort_keys=True
        )
        materialization = EffectiveQuestionGroupReviewMaterializer().materialize(
            structural_groups,
            review_root,
        )
        for issue in materialization.issues:
            self._add(
                issue_groups,
                "batch_overlay",
                issue.code,
                issue.location,
                issue.message,
            )
        for batch in materialization.review_batches:
            for issue in batch.errors:
                self._add(
                    issue_groups,
                    "batch_overlay",
                    issue.code,
                    f"{Path(batch.path).name}/{issue.location}",
                    issue.message,
                )
        if json.dumps(
            materialization.structural_groups, ensure_ascii=False, sort_keys=True
        ) != structural_snapshot:
            self._add(
                issue_groups,
                "structural_staging",
                "STRUCTURAL_SNAPSHOT_MUTATED",
                "question_group_candidates.json",
                "Review materialization changed its immutable structural snapshot.",
            )

        raw_path = group_staging_path.parent / "candidate_questions.json"
        raw_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest() if raw_path.is_file() else ""
        if raw_sha != EXPECTED_RAW_CANDIDATE_SHA256:
            self._add(
                issue_groups,
                "raw_integrity",
                "RAW_CANDIDATE_SHA256_MISMATCH",
                raw_path.as_posix(),
                f"Expected {EXPECTED_RAW_CANDIDATE_SHA256}; found {raw_sha}.",
            )

        batch_paths = tuple(
            path for path in sorted(review_root.glob("batch_*")) if path.is_dir()
        )
        reviewed_ids: set[str] = set()
        verified_records: list[dict[str, Any]] = []
        hold_records: list[dict[str, Any]] = []
        rejected_records: list[dict[str, Any]] = []
        evidence_records: list[dict[str, Any]] = []
        for batch_path in batch_paths:
            verified = self._load_list(
                batch_path / "verified_groups.json", issue_groups, "batch_overlay"
            )
            holds = self._load_list(
                batch_path / "hold_groups.json", issue_groups, "batch_overlay"
            )
            rejected = self._load_list(
                batch_path / "rejected_groups.json", issue_groups, "batch_overlay"
            )
            evidence = self._load_list(
                batch_path / "source_evidence.json", issue_groups, "source_evidence"
            )
            patches = self._load_list(
                batch_path / "group_patch.json", issue_groups, "batch_overlay"
            )
            stats = self._load_object(
                batch_path / "review_stats.json", issue_groups, "batch_overlay"
            )
            source_metadata = self._load_object(
                batch_path / "source_metadata.json", issue_groups, "source_evidence"
            )
            current_ids = {
                str(record.get("group_candidate_id"))
                for record in (*verified, *holds, *rejected)
                if isinstance(record.get("group_candidate_id"), str)
            }
            overlap = reviewed_ids & current_ids
            for group_id in sorted(overlap):
                self._add(
                    issue_groups,
                    "batch_overlay",
                    "GROUP_REVIEW_BATCH_OVERLAP",
                    group_id,
                    "A group may be reviewed by at most one batch.",
                )
            reviewed_ids.update(current_ids)
            verified_records.extend(verified)
            hold_records.extend(holds)
            rejected_records.extend(rejected)
            evidence_records.extend(evidence)
            self._validate_batch_metadata(
                batch_path,
                stats,
                source_metadata,
                verified,
                holds,
                rejected,
                issue_groups,
            )
            self._validate_patch_consistency(
                patches, verified, issue_groups
            )

        structural_by_id = {
            str(group["group_candidate_id"]): group
            for group in structural_groups
            if isinstance(group.get("group_candidate_id"), str)
        }
        evidence_by_id = {
            str(record["evidence_id"]): record
            for record in evidence_records
            if isinstance(record.get("evidence_id"), str)
        }
        if len(evidence_by_id) != len(evidence_records):
            self._add(
                issue_groups,
                "source_evidence",
                "EVIDENCE_IDS_NOT_UNIQUE",
                "source_evidence.json",
                "Source evidence IDs must be unique.",
            )
        evidence_group_ids = {
            str(record.get("group_candidate_id")) for record in evidence_records
        }
        referenced_evidence_ids = {
            str(record.get("source_evidence_id"))
            for record in (*verified_records, *hold_records, *rejected_records)
        }
        if (
            evidence_group_ids != reviewed_ids
            or referenced_evidence_ids != set(evidence_by_id)
        ):
            self._add(
                issue_groups,
                "source_evidence",
                "SOURCE_EVIDENCE_COVERAGE_MISMATCH",
                "source_evidence.json",
                "Every reviewed group must map one-to-one to source evidence.",
            )
        problem_type_codes = self._taxonomy_codes(
            curriculum_path / "problem_types.json", issue_groups
        )
        concept_codes = self._taxonomy_codes(
            curriculum_path / "concepts.json", issue_groups
        )
        learning_outcome_codes = self._taxonomy_codes(
            curriculum_path / "learning_outcomes.json", issue_groups
        )

        for record in verified_records:
            self._validate_verified(
                record,
                structural_by_id,
                evidence_by_id,
                problem_type_codes,
                concept_codes,
                learning_outcome_codes,
                issue_groups,
            )
        self._validate_rejected(
            rejected_records,
            structural_by_id,
            evidence_by_id,
            issue_groups,
        )
        self._validate_exact_acceptance(
            verified_records,
            hold_records,
            rejected_records,
            reviewed_ids,
            issue_groups,
        )

        rejected_ids = {
            str(record.get("group_candidate_id")) for record in rejected_records
        }
        usable_ids = {
            str(group.get("group_candidate_id"))
            for group in materialization.effective_usable_groups
        }
        leaked = rejected_ids & usable_ids
        for group_id in sorted(leaked):
            self._add(
                issue_groups,
                "promotion_boundary",
                "REJECTED_GROUP_IN_USABLE_VIEW",
                group_id,
                "Rejected groups must be excluded from the effective usable view.",
            )
        if materialization.promotion_ready_groups:
            self._add(
                issue_groups,
                "promotion_boundary",
                "PROMOTION_READY_NOT_ZERO",
                "effective review",
                "DATA-MATH12-007 must not make any group production-promotable.",
            )

        checks = {name: not errors for name, errors in issue_groups.items()}
        errors = tuple(sorted({error for rows in issue_groups.values() for error in rows}))
        verified_children = sum(
            len(record.get("items", []))
            for record in verified_records
            if isinstance(record.get("items"), list)
        )
        assigned_answers = sum(
            item.get("correct_answer") in {"TRUE", "FALSE"}
            for record in verified_records
            if isinstance(record.get("items"), list)
            for item in record["items"]
            if isinstance(item, dict)
        )
        counts = {
            "structural_groups": len(structural_groups),
            "structural_holds": structural_report.counts.get("structural_holds", 0),
            "review_batches": len(batch_paths),
            "target_groups": len(reviewed_ids),
            "reviewed_groups": len(reviewed_ids),
            "verified": len(verified_records),
            "hold": len(hold_records),
            "rejected": len(rejected_records),
            "rejected_duplicate": len(set(EXPECTED_DUPLICATES) & rejected_ids),
            "rejected_out_of_scope": len(EXPECTED_OUT_OF_SCOPE & rejected_ids),
            "verified_child_statements": verified_children,
            "assigned_child_answers": assigned_answers,
            "visual_asset_required": sum(
                record.get("visual_asset_required") is True
                for record in verified_records
            ),
            "promotion_ready": len(materialization.promotion_ready_groups),
            "effective_usable_groups": len(materialization.effective_usable_groups),
        }
        return QuestionGroupReviewValidationReport(
            dataset_path=review_root.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts=counts,
            errors=errors,
            review_batches=tuple(batch.as_dict() for batch in materialization.review_batches),
            materialization=materialization,
        )

    def _validate_batch_metadata(
        self,
        batch_path: Path,
        stats: dict[str, Any],
        source_metadata: dict[str, Any],
        verified: list[dict[str, Any]],
        holds: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
    ) -> None:
        expected = {
            "dataset_code": "DATA-MATH12-007",
            "batch_code": EXPECTED_BATCH_CODE,
            "base_commit": EXPECTED_BASE_COMMIT,
            "raw_candidate_sha256": EXPECTED_RAW_CANDIDATE_SHA256,
            "target_groups": 13,
            "reviewed_groups": 13,
            "verified": 8,
            "hold": 0,
            "rejected": 5,
            "rejected_duplicate": 3,
            "rejected_out_of_scope": 2,
            "verified_child_statements": 32,
            "assigned_child_answers": 32,
            "visual_asset_required": 2,
            "source_evidence_backed_decisions": 13,
            "promotion_ready": 0,
            "production_imported": 0,
        }
        for field, value in expected.items():
            if stats.get(field) != value:
                self._add(
                    issues,
                    "batch_acceptance",
                    "BATCH_METADATA_MISMATCH",
                    f"{batch_path.name}/review_stats.json.{field}",
                    f"Expected {value!r}; found {stats.get(field)!r}.",
                )
        if source_metadata.get("source_code") != stats.get("source_code"):
            self._add(
                issues,
                "source_evidence",
                "SOURCE_METADATA_MISMATCH",
                batch_path.name,
                "Source metadata and review stats must identify the same source.",
            )
        if (
            source_metadata.get("file_name") != stats.get("source_file")
            or source_metadata.get("source_pdf_sha256")
            != stats.get("source_pdf_sha256")
        ):
            self._add(
                issues,
                "source_evidence",
                "SOURCE_FILE_LINEAGE_MISMATCH",
                batch_path.name,
                "Source filename and recorded SHA-256 must agree across metadata.",
            )
        if source_metadata.get("pdf_binary_in_bundle") is not False:
            self._add(
                issues,
                "source_evidence",
                "PDF_BINARY_BOUNDARY_INVALID",
                batch_path.name,
                "The reviewed data bundle must not contain the source PDF binary.",
            )
        actual_counts = (len(verified), len(holds), len(rejected))
        if actual_counts != (8, 0, 5):
            self._add(
                issues,
                "batch_acceptance",
                "BATCH_RECORD_COUNTS_MISMATCH",
                batch_path.name,
                f"Expected (8, 0, 5); found {actual_counts}.",
            )

    def _validate_verified(
        self,
        record: dict[str, Any],
        structural_by_id: dict[str, dict[str, Any]],
        evidence_by_id: dict[str, dict[str, Any]],
        problem_types: set[str],
        concepts: set[str],
        learning_outcomes: set[str],
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
    ) -> None:
        group_id = str(record.get("group_candidate_id") or "<missing>")
        structural = structural_by_id.get(group_id)
        if structural is None:
            self._add(issues, "batch_overlay", "GROUP_NOT_FOUND", group_id,
                      "VERIFIED group does not resolve in structural staging.")
            return
        expected_provenance = {
            "source_candidate_id": structural.get("source_candidate_id"),
            "source_fingerprint": structural.get("source_fingerprint"),
            "source_code": structural.get("source_code"),
            "raw_subsource_code": structural.get("raw_subsource_code"),
            "effective_subsource_code": structural.get("effective_subsource_code"),
            "provenance_correction_code": structural.get("provenance_correction_code"),
            "candidate_extraction_page": structural.get("source_page"),
            "question_number": structural.get("question_number"),
        }
        for field, value in expected_provenance.items():
            if record.get(field) != value:
                self._add(
                    issues, "provenance", "REVIEW_PROVENANCE_MISMATCH",
                    f"{group_id}.{field}", f"Expected {value!r}; found {record.get(field)!r}.",
                )
        required_values = {
            "review_status": "VERIFIED",
            "content_review": "CONFIRMED_FROM_SOURCE",
            "answer_verification": "SOURCE_BACKED",
            "taxonomy_review": "CONFIRMED_DERIVED",
            "taxonomy_basis": "COACH_LEARNING_DERIVED",
            "promotion_ready": False,
        }
        for field, value in required_values.items():
            if record.get(field) != value:
                self._add(
                    issues, "review_content", "VERIFIED_FIELD_INVALID",
                    f"{group_id}.{field}", f"Expected {value!r}; found {record.get(field)!r}.",
                )
        if not isinstance(record.get("reviewed_group_context"), str) or not record["reviewed_group_context"].strip():
            self._add(issues, "review_content", "REVIEWED_CONTEXT_EMPTY", group_id,
                      "VERIFIED group must have reviewed context.")
        items = record.get("items")
        if not isinstance(items, list) or len(items) != 4:
            self._add(issues, "review_content", "VERIFIED_CHILD_COUNT_INVALID", group_id,
                      "VERIFIED group must contain exactly four reviewed items.")
            return
        labels = [item.get("label") for item in items if isinstance(item, dict)]
        indexes = [item.get("order_index") for item in items if isinstance(item, dict)]
        if labels != list(EXPECTED_LABELS) or indexes != list(range(4)):
            self._add(issues, "review_content", "VERIFIED_CHILD_ORDER_INVALID", group_id,
                      "VERIFIED children must be a/b/c/d in order 0..3.")
        for index, item in enumerate(items):
            location = f"{group_id}.items[{index}]"
            if not isinstance(item, dict):
                self._add(issues, "review_content", "VERIFIED_CHILD_INVALID", location,
                          "Reviewed child must be an object.")
                continue
            if not isinstance(item.get("reviewed_content"), str) or not item["reviewed_content"].strip():
                self._add(issues, "review_content", "REVIEWED_CHILD_CONTENT_EMPTY", location,
                          "Reviewed child content is required.")
            if item.get("correct_answer") not in {"TRUE", "FALSE"}:
                self._add(issues, "review_content", "CHILD_ANSWER_INVALID", location,
                          "Reviewed answer must be TRUE or FALSE.")
            if item.get("answer_status") != "SOURCE_VERIFIED" or not item.get("answer_evidence"):
                self._add(issues, "source_evidence", "CHILD_ANSWER_NOT_SOURCE_BACKED", location,
                          "Every child answer must carry source-backed evidence.")
            if item.get("taxonomy_basis") != "COACH_LEARNING_DERIVED":
                self._add(issues, "taxonomy", "CHILD_TAXONOMY_BASIS_INVALID", location,
                          "Child taxonomy must be marked COACH_LEARNING_DERIVED.")
            self._validate_child_taxonomy(
                item, location, problem_types, concepts, learning_outcomes, issues
            )
        evidence = evidence_by_id.get(str(record.get("source_evidence_id")))
        if evidence is None:
            self._add(issues, "source_evidence", "SOURCE_EVIDENCE_NOT_FOUND", group_id,
                      "VERIFIED source_evidence_id does not resolve.")
        else:
            pattern = tuple(item.get("correct_answer") for item in items if isinstance(item, dict))
            if evidence.get("group_candidate_id") != group_id or tuple(evidence.get("answer_pattern", [])) != pattern:
                self._add(issues, "source_evidence", "ANSWER_EVIDENCE_MISMATCH", group_id,
                          "Source evidence answer pattern does not match reviewed children.")
            for field in ("source_code", "effective_subsource_code", "candidate_extraction_page", "question_number"):
                if evidence.get(field) != record.get(field):
                    self._add(issues, "source_evidence", "EVIDENCE_PROVENANCE_MISMATCH",
                              f"{group_id}.{field}", "Evidence provenance does not match review record.")

    def _validate_child_taxonomy(
        self,
        item: dict[str, Any],
        location: str,
        problem_type_codes: set[str],
        concept_codes: set[str],
        learning_outcome_codes: set[str],
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
    ) -> None:
        problem_types = item.get("problem_types")
        concepts = item.get("concepts")
        outcomes = item.get("learning_outcomes")
        if not isinstance(problem_types, list) or not problem_types:
            self._add(issues, "taxonomy", "CHILD_PROBLEM_TYPES_EMPTY", location,
                      "At least one child ProblemType is required.")
            problem_types = []
        if not isinstance(concepts, list) or not concepts:
            self._add(issues, "taxonomy", "CHILD_CONCEPTS_EMPTY", location,
                      "At least one child Concept is required.")
            concepts = []
        if not isinstance(outcomes, list) or not outcomes:
            self._add(issues, "taxonomy", "CHILD_OUTCOMES_EMPTY", location,
                      "At least one child LearningOutcome is required.")
            outcomes = []
        for row in problem_types:
            if not isinstance(row, dict) or row.get("code") not in problem_type_codes:
                self._add(issues, "taxonomy", "UNKNOWN_PROBLEM_TYPE", location,
                          f"Unknown child ProblemType: {row.get('code') if isinstance(row, dict) else row!r}.")
        primary_count = sum(
            row.get("is_primary") is True for row in problem_types if isinstance(row, dict)
        )
        if primary_count > 1:
            self._add(issues, "taxonomy", "MULTIPLE_PRIMARY_PROBLEM_TYPES", location,
                      "A child may have at most one primary ProblemType.")
        concept_weights: list[float] = []
        for row in concepts:
            if not isinstance(row, dict) or row.get("code") not in concept_codes:
                self._add(issues, "taxonomy", "UNKNOWN_CONCEPT", location,
                          f"Unknown child Concept: {row.get('code') if isinstance(row, dict) else row!r}.")
                continue
            weight = row.get("weight")
            if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0:
                self._add(issues, "taxonomy", "CONCEPT_WEIGHT_INVALID", location,
                          "Concept weights must be finite and greater than zero.")
            else:
                concept_weights.append(float(weight))
        if concept_weights and sum(concept_weights) > 1.0 + 1e-9:
            self._add(issues, "taxonomy", "CONCEPT_WEIGHT_SUM_EXCEEDS_ONE", location,
                      f"Concept weights total {sum(concept_weights):.12g}; maximum is 1.0.")
        for row in outcomes:
            if not isinstance(row, dict) or row.get("code") not in learning_outcome_codes:
                self._add(issues, "taxonomy", "UNKNOWN_LEARNING_OUTCOME", location,
                          f"Unknown child LearningOutcome: {row.get('code') if isinstance(row, dict) else row!r}.")

    def _validate_rejected(
        self,
        records: list[dict[str, Any]],
        structural_by_id: dict[str, dict[str, Any]],
        evidence_by_id: dict[str, dict[str, Any]],
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
    ) -> None:
        rejected_ids = {str(record.get("group_candidate_id")) for record in records}
        for record in records:
            group_id = str(record.get("group_candidate_id") or "<missing>")
            structural = structural_by_id.get(group_id)
            if structural is None:
                self._add(issues, "duplicate_boundary", "REJECTED_GROUP_NOT_FOUND", group_id,
                          "Rejected group does not resolve in structural staging.")
                continue
            if record.get("source_candidate_id") != structural.get("source_candidate_id"):
                self._add(issues, "provenance", "REJECTED_SOURCE_CANDIDATE_MISMATCH", group_id,
                          "Rejected group source candidate does not match structural staging.")
            if record.get("promotion_ready") is not False:
                self._add(issues, "promotion_boundary", "REJECTED_PROMOTION_INVALID", group_id,
                          "Rejected groups must have promotion_ready=false.")
            evidence = evidence_by_id.get(str(record.get("source_evidence_id")))
            if evidence is None or evidence.get("group_candidate_id") != group_id:
                self._add(issues, "source_evidence", "REJECTED_EVIDENCE_INVALID", group_id,
                          "Rejected group source evidence must resolve.")
            elif any(
                evidence.get(field) != expected
                for field, expected in {
                    "source_code": structural.get("source_code"),
                    "effective_subsource_code": structural.get(
                        "effective_subsource_code"
                    ),
                    "candidate_extraction_page": structural.get("source_page"),
                    "question_number": structural.get("question_number"),
                }.items()
            ):
                self._add(
                    issues,
                    "source_evidence",
                    "REJECTED_EVIDENCE_PROVENANCE_MISMATCH",
                    group_id,
                    "Rejected evidence provenance does not match structural staging.",
                )
            status = record.get("review_status")
            if status == "REJECTED_DUPLICATE_GROUP":
                target = record.get("duplicate_of_group_candidate_id")
                if target not in structural_by_id:
                    self._add(issues, "duplicate_boundary", "DUPLICATE_TARGET_NOT_FOUND", group_id,
                              "Duplicate target must be an existing canonical structural group.")
                if target == group_id or target in rejected_ids:
                    self._add(issues, "duplicate_boundary", "DUPLICATE_TARGET_INVALID", group_id,
                              "Duplicate target cannot be self or another rejected group.")
                if evidence is not None and evidence.get("duplicate_of_group_candidate_id") != target:
                    self._add(issues, "source_evidence", "DUPLICATE_EVIDENCE_MISMATCH", group_id,
                              "Duplicate evidence target does not match rejection record.")
            elif status != "REJECTED_OUT_OF_SCOPE":
                self._add(issues, "duplicate_boundary", "REJECTED_STATUS_INVALID", group_id,
                          "Rejected status is not supported by this review layer.")

    def _validate_exact_acceptance(
        self,
        verified: list[dict[str, Any]],
        holds: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
        reviewed_ids: set[str],
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
    ) -> None:
        if reviewed_ids != EXPECTED_TARGET_IDS:
            self._add(issues, "batch_acceptance", "TARGET_IDS_MISMATCH", "batch_001",
                      f"Expected {sorted(EXPECTED_TARGET_IDS)}; found {sorted(reviewed_ids)}.")
        patterns = {
            str(record.get("group_candidate_id")): tuple(
                item.get("correct_answer")
                for item in record.get("items", [])
                if isinstance(item, dict)
            )
            for record in verified
        }
        if patterns != EXPECTED_ANSWER_PATTERNS:
            self._add(issues, "batch_acceptance", "ANSWER_PATTERNS_MISMATCH", "batch_001",
                      "Reviewed answer patterns differ from the approved bundle.")
        duplicates = {
            str(record.get("group_candidate_id")): str(record.get("duplicate_of_group_candidate_id"))
            for record in rejected
            if record.get("review_status") == "REJECTED_DUPLICATE_GROUP"
        }
        if duplicates != EXPECTED_DUPLICATES:
            self._add(issues, "batch_acceptance", "DUPLICATE_MAPPINGS_MISMATCH", "batch_001",
                      "Duplicate mappings differ from the approved bundle.")
        out_of_scope = {
            str(record.get("group_candidate_id"))
            for record in rejected
            if record.get("review_status") == "REJECTED_OUT_OF_SCOPE"
        }
        if out_of_scope != EXPECTED_OUT_OF_SCOPE:
            self._add(issues, "batch_acceptance", "OUT_OF_SCOPE_IDS_MISMATCH", "batch_001",
                      "Out-of-scope group IDs differ from the approved bundle.")
        visuals = {
            str(record.get("group_candidate_id"))
            for record in verified
            if record.get("visual_asset_required") is True
        }
        if visuals != EXPECTED_VISUAL_GROUPS:
            self._add(issues, "batch_acceptance", "VISUAL_FLAGS_MISMATCH", "batch_001",
                      "Visual asset flags differ from the approved bundle.")
        if holds:
            self._add(issues, "batch_acceptance", "UNEXPECTED_HOLD_RECORDS", "batch_001",
                      "The approved batch contains no HOLD groups.")
        group_0031 = next(
            (record for record in verified if record.get("group_candidate_id") == "M12_DERIV_GROUP_0031"),
            {},
        )
        expected_0031 = {
            "raw_subsource_code": "HA_TINH_2025",
            "effective_subsource_code": "HUNG_YEN_2025",
            "provenance_correction_code": "PROV_CORR_HUNG_YEN_2025_PAGE_BOUNDARY",
        }
        if any(group_0031.get(field) != value for field, value in expected_0031.items()):
            self._add(issues, "provenance", "GROUP_0031_PROVENANCE_MISMATCH",
                      "M12_DERIV_GROUP_0031", "Approved provenance correction was not preserved.")

    def _validate_patch_consistency(
        self,
        patches: list[dict[str, Any]],
        verified: list[dict[str, Any]],
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
    ) -> None:
        verified_by_id = {
            str(record["group_candidate_id"]): record
            for record in verified
            if isinstance(record.get("group_candidate_id"), str)
        }
        for patch in patches:
            group_id = str(patch.get("group_candidate_id") or "<missing>")
            record = verified_by_id.get(group_id)
            values = patch.get("set")
            if record is None or not isinstance(values, dict):
                continue
            reviewed_items = values.get("reviewed_items")
            if not isinstance(reviewed_items, list) or any(
                not isinstance(item, dict)
                or set(item) != {"label", "order_index", "reviewed_content"}
                for item in reviewed_items
            ):
                self._add(
                    issues,
                    "review_content",
                    "PATCH_ITEM_FIELDS_INVALID",
                    group_id,
                    "Patches may contain reviewed child text and its label/order only.",
                )
            expected_items = [
                {
                    "label": item.get("label"),
                    "order_index": item.get("order_index"),
                    "reviewed_content": item.get("reviewed_content"),
                }
                for item in record.get("items", [])
                if isinstance(item, dict)
            ]
            if values.get("reviewed_group_context") != record.get("reviewed_group_context") or reviewed_items != expected_items:
                self._add(issues, "review_content", "PATCH_REVIEW_CONTENT_MISMATCH", group_id,
                          "Reviewed text patch must mirror the VERIFIED review record.")
            if values.get("visual_asset_required") != record.get("visual_asset_required"):
                self._add(issues, "review_content", "PATCH_VISUAL_FLAG_MISMATCH", group_id,
                          "Patch visual flag must mirror the VERIFIED review record.")

    @staticmethod
    def _taxonomy_codes(
        path: Path,
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
    ) -> set[str]:
        rows = QuestionGroupReviewValidator._load_list(
            path, issues, "taxonomy"
        )
        codes = {
            str(row["code"])
            for row in rows
            if isinstance(row.get("code"), str) and row["code"]
        }
        if len(codes) != len(rows):
            QuestionGroupReviewValidator._add(
                issues, "taxonomy", "TAXONOMY_CODES_INVALID", path.name,
                "Taxonomy codes must be present and unique.",
            )
        return codes

    @staticmethod
    def _load_json(
        path: Path,
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
        check: str,
    ) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as error:
            QuestionGroupReviewValidator._add(
                issues, check, "INVALID_OR_MISSING_JSON", path.as_posix(),
                f"Cannot load JSON: {error}.",
            )
            return None

    @staticmethod
    def _load_list(
        path: Path,
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
        check: str,
    ) -> list[dict[str, Any]]:
        value = QuestionGroupReviewValidator._load_json(path, issues, check)
        if isinstance(value, list) and all(isinstance(row, dict) for row in value):
            return value
        if value is not None:
            QuestionGroupReviewValidator._add(
                issues, check, "INVALID_JSON_SHAPE", path.as_posix(),
                "Expected an array of objects.",
            )
        return []

    @staticmethod
    def _load_object(
        path: Path,
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
        check: str,
    ) -> dict[str, Any]:
        value = QuestionGroupReviewValidator._load_json(path, issues, check)
        if isinstance(value, dict):
            return value
        if value is not None:
            QuestionGroupReviewValidator._add(
                issues, check, "INVALID_JSON_SHAPE", path.as_posix(),
                "Expected an object.",
            )
        return {}

    @staticmethod
    def _add(
        issues: dict[str, list[QuestionGroupReviewValidationIssue]],
        check: str,
        code: str,
        location: str,
        message: str,
    ) -> None:
        issues[check].append(QuestionGroupReviewValidationIssue(
            check=check,
            code=code,
            location=location,
            message=message,
        ))
