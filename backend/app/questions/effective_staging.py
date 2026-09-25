from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.questions.provenance_corrections import (
    ProvenanceCorrectionReport,
    QuestionProvenanceCorrectionResolver,
)
from app.questions.review_overlay import (
    QuestionReviewOverlayResolver,
    ReviewBatchReport,
)


@dataclass(frozen=True, slots=True, order=True)
class EffectiveStagingIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class EffectiveQuestionStaging:
    """One immutable-by-convention view of all staging overlays in lexical order."""

    raw_candidates: tuple[dict[str, Any], ...]
    effective_candidates: tuple[dict[str, Any], ...]
    provenance_corrections: ProvenanceCorrectionReport
    review_batches: tuple[ReviewBatchReport, ...]
    issues: tuple[EffectiveStagingIssue, ...]

    @property
    def is_valid(self) -> bool:
        return (
            self.provenance_corrections.is_valid
            and all(batch.is_valid for batch in self.review_batches)
            and not self.issues
        )


def effective_review_status(candidate: dict[str, Any]) -> str:
    review_record = candidate.get("review_record")
    review_status = (
        review_record.get("review_status")
        if isinstance(review_record, dict)
        else None
    )
    if candidate.get("status") == "REJECTED" or str(review_status).startswith(
        "REJECTED"
    ):
        return "REJECTED"
    if str(review_status).startswith("HOLD_"):
        return "HOLD"
    if candidate.get("status") == "VERIFIED":
        return "VERIFIED"
    return "UNTOUCHED_REVIEW_REQUIRED"


class EffectiveQuestionStagingMaterializer:
    """Apply provenance and review overlays once for every staging consumer."""

    def materialize(
        self,
        raw_candidates: list[dict[str, Any]],
        subsources: list[dict[str, Any]],
        correction_path: Path,
        review_root: Path,
    ) -> EffectiveQuestionStaging:
        provenance_result = QuestionProvenanceCorrectionResolver().resolve(
            raw_candidates,
            correction_path,
            subsources,
        )
        issues = [
            EffectiveStagingIssue(
                check="provenance_corrections",
                code=issue.code,
                location=issue.candidate_id,
                message=issue.message,
            )
            for issue in provenance_result.report.issues
        ]
        effective_candidates = (
            list(provenance_result.candidates)
            if provenance_result.report.is_valid
            else copy.deepcopy(raw_candidates)
        )
        review_reports: list[ReviewBatchReport] = []
        reviewed_candidate_batches: dict[str, str] = {}
        batch_paths = (
            tuple(
                path
                for path in sorted(review_root.resolve().glob("batch_*"))
                if path.is_dir()
            )
            if review_root.is_dir()
            else ()
        )
        for batch_path in batch_paths:
            result = QuestionReviewOverlayResolver().resolve(
                effective_candidates,
                batch_path,
            )
            review_reports.append(result.report)
            issues.extend(
                EffectiveStagingIssue(
                    check="review_overlays",
                    code=error.code,
                    location=f"{batch_path.name}/{error.candidate_id}",
                    message=(
                        f"{error.message} "
                        f"[batch={batch_path.name}; path={result.report.path}; "
                        f"candidate_id={error.candidate_id}]"
                    ),
                )
                for error in result.report.errors
            )
            overlapping_ids = sorted(
                set(result.report.reviewed_candidate_ids)
                & set(reviewed_candidate_batches)
            )
            issues.extend(
                EffectiveStagingIssue(
                    check="review_batch_overlap",
                    code="CANDIDATE_REVIEW_BATCH_OVERLAP",
                    location=batch_path.name,
                    message=(
                        f"{candidate_id} was already reviewed by "
                        f"{reviewed_candidate_batches[candidate_id]}."
                    ),
                )
                for candidate_id in overlapping_ids
            )
            if result.report.is_valid and not overlapping_ids:
                effective_candidates = list(result.candidates)
                reviewed_candidate_batches.update(
                    {
                        candidate_id: result.report.batch_code
                        for candidate_id in result.report.reviewed_candidate_ids
                    }
                )

        return EffectiveQuestionStaging(
            raw_candidates=tuple(copy.deepcopy(raw_candidates)),
            effective_candidates=tuple(effective_candidates),
            provenance_corrections=provenance_result.report,
            review_batches=tuple(review_reports),
            issues=tuple(sorted(set(issues))),
        )
