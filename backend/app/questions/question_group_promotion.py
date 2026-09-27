from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.questions.question_group_review_overlay import (
    DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
)
from app.questions.question_group_review_validator import (
    QuestionGroupReviewValidator,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    EXPECTED_RAW_CANDIDATE_SHA256,
)
from app.questions.question_group_visual_assets import (
    BLOCKED_SOURCE_VISUAL_MISSING,
    DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT,
    READY_SOURCE_CROP,
    QuestionGroupVisualAssetValidator,
)


DEFAULT_QUESTION_GROUP_PROMOTION_ROOT = (
    DEFAULT_QUESTION_GROUP_STAGING_PATH.parents[1] / "promotion" / "v0_1"
)
DEFAULT_SOURCE_CATALOG_PATH = (
    DEFAULT_QUESTION_GROUP_STAGING_PATH.parent / "source_catalog.json"
)
EXPECTED_BASE_COMMIT = "cc24bbf1f09f8bff9a2e81a6235b8682c755f4e9"
EXPECTED_GROUP_TYPE = "TRUE_FALSE_FOUR"
EXPECTED_SCORING_POLICY = "MOET_2025_TRUE_FALSE"
FORBIDDEN_INFERENCE_FIELDS = {
    "difficulty",
    "exam_weight",
    "cognitive_level",
    "explanation",
}
GLOBAL_RELEASE_BLOCKERS = {
    "RIGHTS_REVIEW_REQUIRED",
    "CURRICULUM_TAXONOMY_STAGING_ONLY",
    "QUESTION_GROUP_TRUSTED_IMPORT_PIPELINE_MISSING",
    "SCORING_METADATA_POLICY_MISSING",
}


@dataclass(frozen=True, slots=True, order=True)
class QuestionGroupPromotionIssue:
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class QuestionGroupPromotionReport:
    dataset_path: str
    status: str
    counts: dict[str, int]
    snapshot: tuple[dict[str, Any], ...]
    excluded_hold_ids: tuple[str, ...]
    excluded_rejected_ids: tuple[str, ...]
    excluded_visual_ids: tuple[str, ...]
    snapshot_sha256: str
    errors: tuple[QuestionGroupPromotionIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "counts": self.counts,
            "snapshot_group_ids": [
                group["external_group_key"] for group in self.snapshot
            ],
            "excluded_hold_ids": list(self.excluded_hold_ids),
            "excluded_rejected_ids": list(self.excluded_rejected_ids),
            "excluded_visual_ids": list(self.excluded_visual_ids),
            "snapshot_sha256": self.snapshot_sha256,
            "errors": [asdict(error) for error in self.errors],
        }


class QuestionGroupPromotionValidator:
    """Preflight DATA-MATH12-011 and materialize a read-only snapshot."""

    def validate(
        self,
        promotion_root: Path = DEFAULT_QUESTION_GROUP_PROMOTION_ROOT,
        group_staging_path: Path = DEFAULT_QUESTION_GROUP_STAGING_PATH,
        review_root: Path = DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
        visual_root: Path = DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT,
        source_catalog_path: Path = DEFAULT_SOURCE_CATALOG_PATH,
    ) -> QuestionGroupPromotionReport:
        promotion_root = promotion_root.resolve()
        group_staging_path = group_staging_path.resolve()
        review_root = review_root.resolve()
        visual_root = visual_root.resolve()
        source_catalog_path = source_catalog_path.resolve()
        errors: list[QuestionGroupPromotionIssue] = []

        manifest = self._load_object(
            promotion_root / "promotion_manifest.json", errors
        )
        policy = self._load_object(promotion_root / "promotion_policy.json", errors)
        stats = self._load_object(promotion_root / "promotion_stats.json", errors)
        self._validate_manifest_metadata(manifest, policy, errors)
        self._reject_forbidden_fields(manifest, "promotion_manifest.json", errors)

        review_report = QuestionGroupReviewValidator().validate(
            group_staging_path=group_staging_path,
            review_root=review_root,
        )
        if not review_report.is_valid:
            self._add(
                errors,
                "ACADEMIC_REVIEW_INVALID",
                review_root.as_posix(),
                "The academic QuestionGroup review layer must pass validation.",
            )

        visual_report = QuestionGroupVisualAssetValidator().validate(
            asset_root=visual_root,
            group_staging_path=group_staging_path,
            review_root=review_root,
        )
        if not visual_report.is_valid:
            self._add(
                errors,
                "VISUAL_REGISTRY_INVALID",
                visual_root.as_posix(),
                "The visual asset registry must pass validation.",
            )

        effective_groups = review_report.materialization.effective_groups
        effective_by_id = {
            str(group["group_candidate_id"]): group
            for group in effective_groups
            if isinstance(group.get("group_candidate_id"), str)
        }
        verified_ids = {
            group_id
            for group_id, group in effective_by_id.items()
            if group.get("academic_review_status") == "VERIFIED"
        }
        hold_ids = {
            group_id
            for group_id, group in effective_by_id.items()
            if str(group.get("academic_review_status", "")).startswith("HOLD_")
        }
        rejected_ids = {
            group_id
            for group_id, group in effective_by_id.items()
            if str(group.get("academic_review_status", "")).startswith("REJECTED_")
        }
        batch_by_group_id = self._review_batch_map(
            review_report.review_batches, errors
        )

        records_value = manifest.get("records")
        if not isinstance(records_value, list) or not all(
            isinstance(record, dict) for record in records_value
        ):
            self._add(
                errors,
                "PROMOTION_RECORDS_INVALID",
                "promotion_manifest.json.records",
                "Promotion records must be an array of objects.",
            )
            records: list[dict[str, Any]] = []
        else:
            records = records_value
        record_by_id = self._records_by_id(records, errors)
        self._validate_exact_set(
            set(record_by_id), verified_ids, "promotion_manifest.json.records", errors
        )

        source_rights = self._load_source_rights(source_catalog_path, errors)
        visual_by_group_id = {
            str(record["group_candidate_id"]): record
            for record in visual_report.records
            if isinstance(record.get("group_candidate_id"), str)
        }

        snapshot: list[dict[str, Any]] = []
        visual_missing_ids: set[str] = set()
        for group_id in sorted(record_by_id):
            record = record_by_id[group_id]
            group = effective_by_id.get(group_id)
            if group is None:
                self._add(
                    errors,
                    "PROMOTION_GROUP_UNKNOWN",
                    group_id,
                    "Promotion record does not resolve to a structural group.",
                )
                continue
            if group_id not in verified_ids:
                self._add(
                    errors,
                    "NON_VERIFIED_GROUP_INCLUDED",
                    group_id,
                    "Only academically VERIFIED groups may enter promotion preflight.",
                )
                continue

            visual_record = visual_by_group_id.get(group_id)
            derived = self._validate_record(
                record=record,
                group=group,
                review_batch=batch_by_group_id.get(group_id),
                visual_record=visual_record,
                source_rights=source_rights,
                errors=errors,
            )
            if derived["visual_missing"]:
                visual_missing_ids.add(group_id)
            if derived["snapshot_ready"]:
                snapshot.append(
                    self._materialize_snapshot(
                        manifest=manifest,
                        record=record,
                        group=group,
                        rights_status=derived["rights_status"],
                        visual_asset_id=derived["visual_asset_id"],
                    )
                )

        snapshot.sort(key=lambda group: str(group["external_group_key"]))
        self._validate_snapshot(snapshot, effective_by_id, record_by_id, errors)

        raw_path = group_staging_path.parent / "candidate_questions.json"
        raw_sha256 = self._sha256(raw_path, errors)
        if raw_sha256 != EXPECTED_RAW_CANDIDATE_SHA256:
            self._add(
                errors,
                "RAW_CANDIDATE_SHA_MISMATCH",
                raw_path.as_posix(),
                f"Expected {EXPECTED_RAW_CANDIDATE_SHA256}; found {raw_sha256!r}.",
            )
        if manifest.get("source_raw_candidate_sha256") != raw_sha256:
            self._add(
                errors,
                "MANIFEST_RAW_SHA_MISMATCH",
                "promotion_manifest.json.source_raw_candidate_sha256",
                "Manifest raw candidate SHA-256 must match the immutable source file.",
            )

        counts = self._build_counts(
            effective_groups=effective_groups,
            verified_ids=verified_ids,
            hold_ids=hold_ids,
            rejected_ids=rejected_ids,
            records=records,
            snapshot=snapshot,
            visual_report_counts=visual_report.counts,
            visual_missing_ids=visual_missing_ids,
            source_rights=source_rights,
            effective_by_id=effective_by_id,
        )
        self._validate_stats(stats, counts, records, errors)
        self._validate_policy(policy, errors)

        snapshot_json = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        final_errors = tuple(sorted(set(errors)))
        return QuestionGroupPromotionReport(
            dataset_path=promotion_root.as_posix(),
            status="PASS" if not final_errors else "FAIL",
            counts=counts,
            snapshot=tuple(snapshot),
            excluded_hold_ids=tuple(sorted(hold_ids)),
            excluded_rejected_ids=tuple(sorted(rejected_ids)),
            excluded_visual_ids=tuple(sorted(visual_missing_ids)),
            snapshot_sha256=hashlib.sha256(snapshot_json).hexdigest(),
            errors=final_errors,
        )

    def _validate_manifest_metadata(
        self,
        manifest: dict[str, Any],
        policy: dict[str, Any],
        errors: list[QuestionGroupPromotionIssue],
    ) -> None:
        expected = {
            "dataset_code": "DATA-MATH12-011",
            "promotion_set_code": "DATA-MATH12-011_PROMOTION_V0_1",
            "base_commit": EXPECTED_BASE_COMMIT,
            "subject_code": "MATH12",
            "curriculum_version_code": "GDPT2018_2018",
            "chapter": "derivative_applications_v0_1",
            "policy_version": "promotion_policy_v0_1",
        }
        for field, value in expected.items():
            if manifest.get(field) != value:
                self._add(
                    errors,
                    "MANIFEST_METADATA_MISMATCH",
                    f"promotion_manifest.json.{field}",
                    f"Expected {value!r}; found {manifest.get(field)!r}.",
                )
        if policy.get("policy_version") != manifest.get("policy_version"):
            self._add(
                errors,
                "POLICY_VERSION_MISMATCH",
                "promotion_policy.json.policy_version",
                "Policy version must match the promotion manifest.",
            )

    def _validate_record(
        self,
        record: dict[str, Any],
        group: dict[str, Any],
        review_batch: str | None,
        visual_record: dict[str, Any] | None,
        source_rights: dict[str, str],
        errors: list[QuestionGroupPromotionIssue],
    ) -> dict[str, Any]:
        group_id = str(group["group_candidate_id"])
        academic = group.get("academic_review_record")
        evidence = group.get("source_evidence")
        if not isinstance(academic, dict) or not isinstance(evidence, dict):
            self._add(
                errors,
                "VERIFIED_LINEAGE_MISSING",
                group_id,
                "VERIFIED group must contain academic review and source evidence.",
            )
            return {
                "snapshot_ready": False,
                "visual_missing": False,
                "visual_asset_id": None,
                "rights_status": None,
            }

        expected_fields = {
            "review_batch": review_batch,
            "academic_review_status": "VERIFIED",
            "source_code": evidence.get("source_code"),
            "effective_subsource_code": evidence.get("effective_subsource_code"),
            "child_count": len(academic.get("items", []))
            if isinstance(academic.get("items"), list)
            else None,
            "visual_asset_required": academic.get("visual_asset_required"),
        }
        for field, expected in expected_fields.items():
            if record.get(field) != expected:
                self._add(
                    errors,
                    "PROMOTION_RECORD_MISMATCH",
                    f"{group_id}.{field}",
                    f"Expected {expected!r}; found {record.get(field)!r}.",
                )

        source_code = evidence.get("source_code")
        rights_status = source_rights.get(str(source_code))
        if rights_status is None:
            self._add(
                errors,
                "SOURCE_RIGHTS_UNKNOWN",
                group_id,
                "Group source does not resolve in source_catalog.json.",
            )
        if record.get("rights_status") != rights_status:
            self._add(
                errors,
                "RIGHTS_STATUS_MISMATCH",
                f"{group_id}.rights_status",
                f"Expected source-catalog rights {rights_status!r}.",
            )
        if rights_status != "REVIEW_REQUIRED":
            self._add(
                errors,
                "RIGHTS_BOUNDARY_CHANGED",
                group_id,
                "DATA-MATH12-011 requires REVIEW_REQUIRED source rights.",
            )

        visual_required = academic.get("visual_asset_required") is True
        if visual_required and visual_record is None:
            visual_status = None
            visual_asset_id = None
            visual_missing = False
            self._add(
                errors,
                "VISUAL_RECORD_MISSING",
                group_id,
                "Visual-required VERIFIED group has no registry record.",
            )
        elif visual_required:
            visual_status = visual_record.get("asset_status")
            visual_asset_id = (
                visual_record.get("asset_id")
                if visual_status == READY_SOURCE_CROP
                else None
            )
            visual_missing = visual_status == BLOCKED_SOURCE_VISUAL_MISSING
        else:
            visual_status = "NOT_REQUIRED"
            visual_asset_id = None
            visual_missing = False
            if visual_record is not None:
                self._add(
                    errors,
                    "NON_VISUAL_ASSET_PRESENT",
                    group_id,
                    "A non-visual group must not reference a visual registry record.",
                )

        if record.get("visual_status") != visual_status:
            self._add(
                errors,
                "VISUAL_STATUS_MISMATCH",
                f"{group_id}.visual_status",
                f"Expected {visual_status!r}; found {record.get('visual_status')!r}.",
            )
        if record.get("visual_asset_id") != visual_asset_id:
            self._add(
                errors,
                "VISUAL_ASSET_ID_MISMATCH",
                f"{group_id}.visual_asset_id",
                f"Expected {visual_asset_id!r}; found {record.get('visual_asset_id')!r}.",
            )

        snapshot_ready = not visual_required or visual_status == READY_SOURCE_CROP
        if record.get("canonical_snapshot_ready") is not snapshot_ready:
            self._add(
                errors,
                "SNAPSHOT_GATE_MISMATCH",
                f"{group_id}.canonical_snapshot_ready",
                f"Derived canonical snapshot readiness is {snapshot_ready}.",
            )
        expected_snapshot_blockers = ["SOURCE_VISUAL_MISSING"] if visual_missing else []
        if record.get("canonical_snapshot_blockers") != expected_snapshot_blockers:
            self._add(
                errors,
                "SNAPSHOT_BLOCKERS_MISMATCH",
                f"{group_id}.canonical_snapshot_blockers",
                f"Expected {expected_snapshot_blockers!r}.",
            )

        release_blockers = record.get("release_blockers")
        expected_release_blockers = set(GLOBAL_RELEASE_BLOCKERS)
        if visual_missing:
            expected_release_blockers.add("SOURCE_VISUAL_MISSING")
        if (
            not isinstance(release_blockers, list)
            or not all(isinstance(item, str) for item in release_blockers)
            or len(release_blockers) != len(set(release_blockers))
            or set(release_blockers) != expected_release_blockers
        ):
            self._add(
                errors,
                "RELEASE_BLOCKERS_MISMATCH",
                f"{group_id}.release_blockers",
                f"Expected blocker set {sorted(expected_release_blockers)!r}.",
            )
        if record.get("production_release_eligible") is not False:
            self._add(
                errors,
                "PRODUCTION_ELIGIBILITY_FORBIDDEN",
                f"{group_id}.production_release_eligible",
                "Production release eligibility must remain false.",
            )
        if record.get("database_import_ready") is True:
            self._add(
                errors,
                "DATABASE_IMPORT_FORBIDDEN",
                f"{group_id}.database_import_ready",
                "Database import readiness must remain false in this phase.",
            )
        return {
            "snapshot_ready": snapshot_ready,
            "visual_missing": visual_missing,
            "visual_asset_id": visual_asset_id,
            "rights_status": rights_status,
        }

    @staticmethod
    def _materialize_snapshot(
        manifest: dict[str, Any],
        record: dict[str, Any],
        group: dict[str, Any],
        rights_status: Any,
        visual_asset_id: Any,
    ) -> dict[str, Any]:
        academic = group["academic_review_record"]
        evidence = group["source_evidence"]
        children = []
        for item in academic["items"]:
            children.append(
                {
                    "external_question_key": (
                        f"{group['group_candidate_id']}:{item['label']}"
                    ),
                    "label": item["label"],
                    "order_index": item["order_index"],
                    "question_type": "TRUE_FALSE",
                    "content": item["reviewed_content"],
                    "correct_answer": item["correct_answer"],
                    "answer_status": item["answer_status"],
                    "answer_evidence": item["answer_evidence"],
                    "problem_types": copy.deepcopy(item["problem_types"]),
                    "concepts": copy.deepcopy(item["concepts"]),
                    "learning_outcomes": copy.deepcopy(item["learning_outcomes"]),
                    "taxonomy_basis": item["taxonomy_basis"],
                }
            )
        return {
            "external_group_key": group["group_candidate_id"],
            "subject_code": manifest["subject_code"],
            "curriculum_version_code": manifest["curriculum_version_code"],
            "chapter": manifest["chapter"],
            "group_type": EXPECTED_GROUP_TYPE,
            "scoring_policy": EXPECTED_SCORING_POLICY,
            "content": academic["reviewed_group_context"],
            "source": {
                "source_candidate_id": group["source_candidate_id"],
                "source_fingerprint": group["source_fingerprint"],
                "source_code": evidence["source_code"],
                "raw_subsource_code": academic.get("raw_subsource_code"),
                "effective_subsource_code": evidence["effective_subsource_code"],
                "provenance_correction_code": academic.get(
                    "provenance_correction_code"
                ),
                "candidate_extraction_page": evidence["candidate_extraction_page"],
                "canonical_question_pages": copy.deepcopy(
                    evidence["canonical_question_pages"]
                ),
                "solution_pages": copy.deepcopy(evidence["solution_pages"]),
                "question_number": evidence["question_number"],
                "source_evidence_id": academic["source_evidence_id"],
                "review_batch": record["review_batch"],
                "academic_review_batch": group["academic_review_batch"],
                "rights_status": rights_status,
            },
            "review_lineage": {
                "academic_review_record": copy.deepcopy(academic),
                "source_evidence": copy.deepcopy(evidence),
            },
            "visual_asset_id": visual_asset_id,
            "children": children,
            "production_release_eligible": False,
        }

    def _validate_snapshot(
        self,
        snapshot: list[dict[str, Any]],
        effective_by_id: dict[str, dict[str, Any]],
        record_by_id: dict[str, dict[str, Any]],
        errors: list[QuestionGroupPromotionIssue],
    ) -> None:
        for group_snapshot in snapshot:
            group_id = str(group_snapshot.get("external_group_key"))
            group = effective_by_id[group_id]
            academic = group["academic_review_record"]
            record = record_by_id[group_id]
            if group_snapshot.get("group_type") != EXPECTED_GROUP_TYPE:
                self._add(errors, "SNAPSHOT_GROUP_TYPE_INVALID", group_id,
                          "Snapshot group_type must be TRUE_FALSE_FOUR.")
            if group_snapshot.get("scoring_policy") != EXPECTED_SCORING_POLICY:
                self._add(errors, "SNAPSHOT_SCORING_POLICY_INVALID", group_id,
                          "Snapshot scoring policy must preserve MOET semantics.")
            if group_snapshot.get("content") != academic.get("reviewed_group_context"):
                self._add(errors, "SNAPSHOT_CONTEXT_MISMATCH", group_id,
                          "Snapshot content must equal reviewed group context.")
            if group_snapshot.get("production_release_eligible") is not False:
                self._add(errors, "SNAPSHOT_PRODUCTION_ELIGIBLE", group_id,
                          "Internal snapshots cannot be production eligible.")
            if group_snapshot.get("visual_asset_id") != record.get("visual_asset_id"):
                self._add(errors, "SNAPSHOT_VISUAL_MISMATCH", group_id,
                          "Snapshot visual reference must match promotion preflight.")

            children = group_snapshot.get("children")
            reviewed_items = academic.get("items")
            if not isinstance(children, list) or len(children) != 4:
                self._add(errors, "SNAPSHOT_CHILD_COUNT_INVALID", group_id,
                          "Snapshot groups require exactly four children.")
                continue
            if not isinstance(reviewed_items, list):
                self._add(errors, "REVIEWED_ITEMS_INVALID", group_id,
                          "Reviewed items must be an array.")
                continue
            for index, (child, reviewed) in enumerate(zip(children, reviewed_items)):
                expected_label = "abcd"[index]
                expected_taxonomy = {
                    "problem_types": reviewed.get("problem_types"),
                    "concepts": reviewed.get("concepts"),
                    "learning_outcomes": reviewed.get("learning_outcomes"),
                    "taxonomy_basis": reviewed.get("taxonomy_basis"),
                }
                actual_taxonomy = {
                    field: child.get(field) for field in expected_taxonomy
                }
                if child.get("label") != expected_label or child.get("order_index") != index:
                    self._add(errors, "SNAPSHOT_CHILD_ORDER_INVALID",
                              f"{group_id}:{expected_label}",
                              "Children must use labels a,b,c,d and indexes 0..3.")
                if child.get("external_question_key") != f"{group_id}:{expected_label}":
                    self._add(errors, "SNAPSHOT_CHILD_KEY_INVALID",
                              f"{group_id}:{expected_label}",
                              "Child external key must preserve group and label.")
                if child.get("question_type") != "TRUE_FALSE":
                    self._add(errors, "SNAPSHOT_CHILD_TYPE_INVALID",
                              f"{group_id}:{expected_label}",
                              "Snapshot children must be TRUE_FALSE.")
                if child.get("content") != reviewed.get("reviewed_content"):
                    self._add(errors, "SNAPSHOT_CHILD_CONTENT_MISMATCH",
                              f"{group_id}:{expected_label}",
                              "Child content must equal academic review.")
                if child.get("correct_answer") not in {"TRUE", "FALSE"} or (
                    child.get("correct_answer") != reviewed.get("correct_answer")
                ):
                    self._add(errors, "SNAPSHOT_CHILD_ANSWER_MISMATCH",
                              f"{group_id}:{expected_label}",
                              "Child answer must equal the trusted reviewed answer.")
                if actual_taxonomy != expected_taxonomy:
                    self._add(errors, "SNAPSHOT_CHILD_TAXONOMY_MISMATCH",
                              f"{group_id}:{expected_label}",
                              "Child taxonomy must equal the academic review record.")
            self._reject_forbidden_fields(
                group_snapshot, f"snapshot.{group_id}", errors
            )

    @staticmethod
    def _build_counts(
        effective_groups: tuple[dict[str, Any], ...],
        verified_ids: set[str],
        hold_ids: set[str],
        rejected_ids: set[str],
        records: list[dict[str, Any]],
        snapshot: list[dict[str, Any]],
        visual_report_counts: dict[str, int],
        visual_missing_ids: set[str],
        source_rights: dict[str, str],
        effective_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, int]:
        reviewed_groups = sum(
            isinstance(group.get("academic_review_record"), dict)
            for group in effective_groups
        )
        verified_children = sum(
            len(effective_by_id[group_id]["academic_review_record"].get("items", []))
            for group_id in verified_ids
        )
        visual_required = sum(
            effective_by_id[group_id]["academic_review_record"].get(
                "visual_asset_required"
            )
            is True
            for group_id in verified_ids
        )
        rights_review_required = sum(
            source_rights.get(
                str(effective_by_id[group_id]["source_evidence"].get("source_code"))
            )
            == "REVIEW_REQUIRED"
            for group_id in verified_ids
        )
        return {
            "structural_groups": len(effective_groups),
            "reviewed_groups": reviewed_groups,
            "academic_verified_groups": len(verified_ids),
            "academic_hold_groups": len(hold_ids),
            "academic_rejected_groups": len(rejected_ids),
            "verified_children": verified_children,
            "visual_required_verified_groups": visual_required,
            "visual_ready_groups": visual_report_counts.get("ready_source_crops", 0),
            "visual_missing_groups": len(visual_missing_ids),
            "visual_not_required_groups": len(verified_ids) - visual_required,
            "canonical_snapshot_ready_groups": len(snapshot),
            "canonical_snapshot_ready_children": sum(
                len(group["children"]) for group in snapshot
            ),
            "canonical_snapshot_blocked_groups": len(verified_ids) - len(snapshot),
            "rights_review_required_groups": rights_review_required,
            "taxonomy_staging_only_groups": len(verified_ids),
            "production_release_eligible_groups": sum(
                record.get("production_release_eligible") is True
                for record in records
            ),
            "database_import_ready_groups": sum(
                record.get("database_import_ready") is True for record in records
            ),
        }

    def _validate_stats(
        self,
        stats: dict[str, Any],
        counts: dict[str, int],
        records: list[dict[str, Any]],
        errors: list[QuestionGroupPromotionIssue],
    ) -> None:
        stat_mapping = {
            "structural_groups": "structural_groups",
            "reviewed_groups": "reviewed_groups",
            "academic_verified_groups": "academic_verified_groups",
            "academic_hold_groups": "academic_hold_groups",
            "academic_rejected_groups": "academic_rejected_groups",
            "canonical_snapshot_ready_groups": "canonical_snapshot_ready_groups",
            "canonical_snapshot_ready_children": "canonical_snapshot_ready_children",
            "canonical_snapshot_blocked_groups": "canonical_snapshot_blocked_groups",
            "visual_ready_groups": "visual_ready_groups",
            "visual_not_required_groups": "visual_not_required_groups",
            "visual_missing_groups": "visual_missing_groups",
            "rights_review_required_groups": "rights_review_required_groups",
            "taxonomy_staging_only_groups": "taxonomy_staging_only_groups",
            "production_release_eligible_groups": (
                "production_release_eligible_groups"
            ),
            "database_import_ready_groups": "database_import_ready_groups",
        }
        for stats_field, count_field in stat_mapping.items():
            if stats.get(stats_field) != counts[count_field]:
                self._add(
                    errors,
                    "PROMOTION_STATS_MISMATCH",
                    f"promotion_stats.json.{stats_field}",
                    f"Expected derived value {counts[count_field]!r}; "
                    f"found {stats.get(stats_field)!r}.",
                )
        unresolved = sorted(
            str(record["group_candidate_id"])
            for record in records
            if record.get("visual_status") == BLOCKED_SOURCE_VISUAL_MISSING
            and isinstance(record.get("group_candidate_id"), str)
        )
        if stats.get("unresolved_visual_group_ids") != unresolved:
            self._add(
                errors,
                "PROMOTION_STATS_UNRESOLVED_MISMATCH",
                "promotion_stats.json.unresolved_visual_group_ids",
                f"Expected {unresolved!r}.",
            )
        source_breakdown: dict[str, dict[str, int]] = {}
        for record in records:
            source_code = record.get("source_code")
            if not isinstance(source_code, str):
                continue
            values = source_breakdown.setdefault(
                source_code,
                {"academic_verified": 0, "canonical_snapshot_ready": 0},
            )
            values["academic_verified"] += 1
            values["canonical_snapshot_ready"] += (
                record.get("canonical_snapshot_ready") is True
            )
        if stats.get("source_breakdown") != source_breakdown:
            self._add(
                errors,
                "PROMOTION_STATS_SOURCE_BREAKDOWN_MISMATCH",
                "promotion_stats.json.source_breakdown",
                "Source breakdown must match promotion records.",
            )

    def _validate_policy(
        self,
        policy: dict[str, Any],
        errors: list[QuestionGroupPromotionIssue],
    ) -> None:
        materialization = policy.get("canonical_materialization")
        forbidden = (
            materialization.get("forbidden_inference_fields")
            if isinstance(materialization, dict)
            else None
        )
        if not isinstance(forbidden, list) or set(forbidden) != FORBIDDEN_INFERENCE_FIELDS:
            self._add(
                errors,
                "FORBIDDEN_INFERENCE_POLICY_MISMATCH",
                "promotion_policy.json.canonical_materialization",
                f"Expected forbidden fields {sorted(FORBIDDEN_INFERENCE_FIELDS)!r}.",
            )
        release_gate = policy.get("production_release_gate")
        if not isinstance(release_gate, dict) or release_gate.get(
            "current_result"
        ) != "0 groups eligible":
            self._add(
                errors,
                "PRODUCTION_GATE_POLICY_INVALID",
                "promotion_policy.json.production_release_gate",
                "Production policy must keep zero groups eligible.",
            )

    @classmethod
    def _records_by_id(
        cls,
        records: list[dict[str, Any]],
        errors: list[QuestionGroupPromotionIssue],
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for index, record in enumerate(records):
            group_id = record.get("group_candidate_id")
            location = f"promotion_manifest.json.records[{index}]"
            if not isinstance(group_id, str) or not group_id:
                cls._add(errors, "PROMOTION_GROUP_ID_INVALID", location,
                         "group_candidate_id must be a non-empty string.")
            elif group_id in result:
                cls._add(errors, "PROMOTION_GROUP_ID_DUPLICATE", location,
                         f"Duplicate promotion group {group_id}.")
            else:
                result[group_id] = record
        return result

    @classmethod
    def _validate_exact_set(
        cls,
        actual: set[str],
        expected: set[str],
        location: str,
        errors: list[QuestionGroupPromotionIssue],
    ) -> None:
        for group_id in sorted(expected - actual):
            cls._add(errors, "VERIFIED_GROUP_MISSING", location,
                     f"VERIFIED group {group_id} is missing from promotion manifest.")
        for group_id in sorted(actual - expected):
            cls._add(errors, "NON_VERIFIED_GROUP_INCLUDED", location,
                     f"Non-VERIFIED group {group_id} cannot enter promotion preflight.")

    @classmethod
    def _review_batch_map(
        cls,
        batches: tuple[dict[str, Any], ...],
        errors: list[QuestionGroupPromotionIssue],
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for batch in batches:
            batch_name = Path(str(batch.get("path"))).name
            group_ids = batch.get("reviewed_group_ids")
            if not isinstance(group_ids, list):
                cls._add(errors, "REVIEW_BATCH_IDS_INVALID", batch_name,
                         "reviewed_group_ids must be an array.")
                continue
            for group_id in group_ids:
                if isinstance(group_id, str):
                    result[group_id] = batch_name
        return result

    @classmethod
    def _load_source_rights(
        cls,
        path: Path,
        errors: list[QuestionGroupPromotionIssue],
    ) -> dict[str, str]:
        catalog = cls._load_object(path, errors)
        sources = catalog.get("sources")
        if not isinstance(sources, list) or not all(
            isinstance(source, dict) for source in sources
        ):
            cls._add(errors, "SOURCE_CATALOG_INVALID", path.as_posix(),
                     "source_catalog.json.sources must be an array of objects.")
            return {}
        result: dict[str, str] = {}
        for source in sources:
            source_code = source.get("source_code")
            rights = source.get("rights_status")
            if isinstance(source_code, str) and isinstance(rights, str):
                if source_code in result:
                    cls._add(errors, "SOURCE_CODE_DUPLICATE", source_code,
                             "Source catalog codes must be unique.")
                result[source_code] = rights
        return result

    @classmethod
    def _reject_forbidden_fields(
        cls,
        value: Any,
        location: str,
        errors: list[QuestionGroupPromotionIssue],
    ) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child_location = f"{location}.{key}"
                if key in FORBIDDEN_INFERENCE_FIELDS:
                    cls._add(
                        errors,
                        "FORBIDDEN_INFERENCE_FIELD",
                        child_location,
                        f"{key} is outside the DATA-MATH12-011 schema.",
                    )
                cls._reject_forbidden_fields(item, child_location, errors)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                cls._reject_forbidden_fields(
                    item, f"{location}[{index}]", errors
                )

    @staticmethod
    def _sha256(
        path: Path,
        errors: list[QuestionGroupPromotionIssue],
    ) -> str | None:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            QuestionGroupPromotionValidator._add(
                errors,
                "RAW_CANDIDATE_UNREADABLE",
                path.as_posix(),
                f"Cannot read immutable raw candidate file: {error}.",
            )
            return None

    @classmethod
    def _load_object(
        cls,
        path: Path,
        errors: list[QuestionGroupPromotionIssue],
    ) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            cls._add(errors, "REQUIRED_FILE_MISSING", path.as_posix(),
                     "Required promotion input is missing.")
            return {}
        except (OSError, json.JSONDecodeError) as error:
            cls._add(errors, "JSON_INVALID", path.as_posix(),
                     f"Cannot read JSON: {error}.")
            return {}
        if not isinstance(value, dict):
            cls._add(errors, "JSON_SHAPE_INVALID", path.as_posix(),
                     "Expected a JSON object.")
            return {}
        return value

    @staticmethod
    def _add(
        errors: list[QuestionGroupPromotionIssue],
        code: str,
        location: str,
        message: str,
    ) -> None:
        errors.append(QuestionGroupPromotionIssue(code, location, message))
