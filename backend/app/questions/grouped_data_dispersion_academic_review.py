from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.questions.grouped_data_dispersion_materialization import (
    DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256,
    GroupedDataDispersionMaterializationValidator,
)

DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH = (
    DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH.parents[1]
    / "academic_review"
    / "v0_1"
)

EXPECTED_INPUT_CANDIDATE_SHA256 = "bb88a02a3c982b55a11e250af05432ba999f455f1af54cfb347c5dd277f4c619"
EXPECTED_COUNTS = {
    "standalone_reviews": 39,
    "group_reviews": 2,
    "verified": 38,
    "hold_missing_source_answer": 1,
    "hold_mixed_scope": 2,
}

@dataclass(frozen=True, slots=True, order=True)
class GroupedDataDispersionAcademicReviewIssue:
    check: str
    code: str
    location: str
    message: str

@dataclass(frozen=True, slots=True)
class GroupedDataDispersionAcademicReviewReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, Any]
    errors: tuple[GroupedDataDispersionAcademicReviewIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "errors": [asdict(x) for x in self.errors],
        }

class GroupedDataDispersionAcademicReviewValidator:
    def _load(self, path: Path, expected_type: type, errors: list[GroupedDataDispersionAcademicReviewIssue]):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(GroupedDataDispersionAcademicReviewIssue("required_files","INVALID_OR_MISSING_JSON",path.as_posix(),str(exc)))
            return expected_type()
        if not isinstance(value, expected_type):
            errors.append(GroupedDataDispersionAcademicReviewIssue("required_files","INVALID_JSON_SHAPE",path.as_posix(),expected_type.__name__))
            return expected_type()
        return value

    def validate(self, review_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH) -> GroupedDataDispersionAcademicReviewReport:
        path = review_path.resolve()
        errors: list[GroupedDataDispersionAcademicReviewIssue] = []
        manifest = self._load(path / "review_manifest.json", dict, errors)
        stats = self._load(path / "review_stats.json", dict, errors)
        standalone = self._load(path / "standalone_reviews.json", list, errors)
        groups = self._load(path / "group_reviews.json", list, errors)
        evidence = self._load(path / "source_evidence.json", list, errors)
        coverage = self._load(path / "coverage_after_review.json", list, errors)
        contract = self._load(path / "validation_contract.json", dict, errors)

        materialization = GroupedDataDispersionMaterializationValidator().validate()
        input_errors = []
        if not materialization.is_valid or materialization.aggregate_semantic_sha256 != EXPECTED_AGGREGATE_SEMANTIC_SHA256:
            input_errors.append(GroupedDataDispersionAcademicReviewIssue("input_identity","DATA_020_INPUT_DRIFT","materialized_v0_1","Input materialization is not the locked DATA-MATH12-020 dataset."))
        if manifest.get("input_candidate_semantic_sha256") != EXPECTED_INPUT_CANDIDATE_SHA256:
            input_errors.append(GroupedDataDispersionAcademicReviewIssue("input_identity","CANDIDATE_HASH_MISMATCH","review_manifest.json","Candidate semantic hash does not match DATA-MATH12-020."))

        total_errors = []
        counts = Counter([r.get("review_status") for r in standalone] + [r.get("review_status") for r in groups])
        if len(standalone) != 39 or len(groups) != 2 or counts.get("VERIFIED",0) != 38 or counts.get("HOLD_MISSING_SOURCE_ANSWER",0) != 1 or counts.get("HOLD_MIXED_SCOPE",0) != 2:
            total_errors.append(GroupedDataDispersionAcademicReviewIssue("exact_totals","REVIEW_TOTAL_MISMATCH","review files",repr(dict(counts))))

        semantic_errors = []
        evidence_by_candidate = {r.get("candidate_id"): r for r in evidence}
        for row in standalone:
            status = row.get("review_status")
            if status == "VERIFIED":
                if row.get("correct_answer") not in {"A","B","C","D"}:
                    semantic_errors.append(GroupedDataDispersionAcademicReviewIssue("standalone_semantics","VERIFIED_ANSWER_MISSING",str(row.get("candidate_id")),"Verified standalone must have A-D answer."))
                ev = evidence_by_candidate.get(row.get("candidate_id"))
                if not ev or ev.get("evidence_type") != "SOURCE_QUESTION_AND_SOLUTION_OCCURRENCE" or not ev.get("solution_pages"):
                    semantic_errors.append(GroupedDataDispersionAcademicReviewIssue("standalone_semantics","SOURCE_SOLUTION_EVIDENCE_MISSING",str(row.get("candidate_id")),"Verified answer requires source solution occurrence."))
            if row.get("promotion_ready") is not False:
                semantic_errors.append(GroupedDataDispersionAcademicReviewIssue("promotion_boundary","PROMOTION_READY_FORBIDDEN",str(row.get("candidate_id")),"DATA-021 cannot promote directly."))

        group_errors = []
        for row in groups:
            if row.get("review_status") != "HOLD_MIXED_SCOPE" or row.get("promotion_ready") is not False:
                group_errors.append(GroupedDataDispersionAcademicReviewIssue("question_groups","MIXED_SCOPE_GROUP_MUST_HOLD",str(row.get("group_candidate_id")),"Mixed-scope groups remain on hold."))
            if any(item.get("correct_answer") is not None for item in row.get("items", [])):
                group_errors.append(GroupedDataDispersionAcademicReviewIssue("question_groups","UNVERIFIED_CHILD_ANSWER_PRESENT",str(row.get("group_candidate_id")),"Held group children must remain unverified."))

        contract_errors = []
        required = contract.get("required_invariants", {})
        expected = {"input_candidate_count":41,"standalone_reviews":39,"group_reviews":2,"verified":38,"hold_missing_source_answer":1,"hold_mixed_scope":2,"production_release_eligible":0,"database_import_allowed":False,"canonical_snapshot_allowed":False}
        if any(required.get(k) != v for k,v in expected.items()):
            contract_errors.append(GroupedDataDispersionAcademicReviewIssue("review_contract","CONTRACT_MISMATCH","validation_contract.json",repr(expected)))

        coverage_errors = []
        if len(coverage) != 12 or stats.get("problem_types_total") != 12:
            coverage_errors.append(GroupedDataDispersionAcademicReviewIssue("coverage","COVERAGE_SHAPE_MISMATCH","coverage_after_review.json","Expected 12 taxonomy problem types."))

        checks_to_errors = {
            "required_files": [e for e in errors if e.check == "required_files"],
            "input_identity": input_errors,
            "review_contract": contract_errors,
            "exact_totals": total_errors,
            "standalone_semantics": semantic_errors,
            "question_groups": group_errors,
            "coverage": coverage_errors,
            "promotion_boundary": [e for e in semantic_errors if e.check == "promotion_boundary"],
        }
        all_errors = list(errors) + input_errors + contract_errors + total_errors + semantic_errors + group_errors + coverage_errors
        checks = {k: not v for k,v in checks_to_errors.items()}
        return GroupedDataDispersionAcademicReviewReport(
            dataset_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts={
                "standalone_reviews": len(standalone),
                "group_reviews": len(groups),
                "review_status_counts": dict(counts),
                "verified": counts.get("VERIFIED",0),
                "hold": counts.get("HOLD_MISSING_SOURCE_ANSWER",0) + counts.get("HOLD_MIXED_SCOPE",0),
                "production_release_eligible": 0,
            },
            errors=tuple(sorted(set(all_errors))),
        )
