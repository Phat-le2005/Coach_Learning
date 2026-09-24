from __future__ import annotations

import copy
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PRESERVED_PROVENANCE_FIELDS = (
    "source_code",
    "subsource_code",
    "source_page",
    "question_number",
    "fingerprint",
    "raw_question_text",
    "question_type_detected",
)
CORRECTION_FIELDS = {
    "candidate_id",
    "source_page",
    "original_subsource_code",
    "corrected_subsource_code",
}


@dataclass(frozen=True, slots=True, order=True)
class ProvenanceCorrectionIssue:
    check: str
    code: str
    candidate_id: str
    message: str


@dataclass(frozen=True, slots=True)
class ProvenanceCorrectionReport:
    path: str
    status: str
    correction_code: str | None
    total: int
    applied: int
    corrected_candidate_ids: tuple[str, ...]
    issues: tuple[ProvenanceCorrectionIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    @property
    def errors(self) -> int:
        return len(self.issues)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status,
            "correction_code": self.correction_code,
            "total": self.total,
            "applied": self.applied,
            "errors": self.errors,
            "corrected_candidate_ids": list(self.corrected_candidate_ids),
            "issues": [asdict(issue) for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class ProvenanceCorrectionResult:
    candidates: tuple[dict[str, Any], ...]
    report: ProvenanceCorrectionReport

    def candidate(self, candidate_id: str) -> dict[str, Any]:
        for candidate in self.candidates:
            if candidate.get("candidate_id") == candidate_id:
                return candidate
        raise KeyError(candidate_id)


class QuestionProvenanceCorrectionResolver:
    """Apply reviewed provenance corrections without mutating raw staging data."""

    def resolve(
        self,
        raw_candidates: list[dict[str, Any]],
        correction_path: Path,
        subsources: list[dict[str, Any]],
    ) -> ProvenanceCorrectionResult:
        path = correction_path.resolve()
        issues: list[ProvenanceCorrectionIssue] = []
        payload = self._load_payload(path, issues)
        corrections_value = payload.get("candidate_corrections", [])
        corrections = (
            corrections_value
            if isinstance(corrections_value, list)
            and all(isinstance(item, dict) for item in corrections_value)
            else []
        )
        if corrections_value != corrections:
            issues.append(ProvenanceCorrectionIssue(
                check="correction_file",
                code="INVALID_CORRECTIONS_SHAPE",
                candidate_id="<file>",
                message="candidate_corrections must be an array of objects.",
            ))

        correction_code = payload.get("correction_code")
        expected_source_code = payload.get("source_code")
        if not isinstance(correction_code, str) or not correction_code:
            issues.append(ProvenanceCorrectionIssue(
                check="correction_file",
                code="MISSING_CORRECTION_CODE",
                candidate_id="<file>",
                message="correction_code must be a non-empty string.",
            ))
            correction_code = None
        if not isinstance(expected_source_code, str) or not expected_source_code:
            issues.append(ProvenanceCorrectionIssue(
                check="correction_file",
                code="MISSING_SOURCE_CODE",
                candidate_id="<file>",
                message="source_code must be a non-empty string.",
            ))
            expected_source_code = None

        raw_by_id = {
            candidate_id: candidate
            for candidate in raw_candidates
            if isinstance((candidate_id := candidate.get("candidate_id")), str)
        }
        effective = copy.deepcopy(raw_candidates)
        effective_by_id = {
            candidate["candidate_id"]: candidate
            for candidate in effective
            if isinstance(candidate.get("candidate_id"), str)
        }
        subsource_by_code = {
            subsource["subsource_code"]: subsource
            for subsource in subsources
            if isinstance(subsource.get("subsource_code"), str)
        }
        candidate_id_counts = Counter(
            correction.get("candidate_id")
            for correction in corrections
            if isinstance(correction.get("candidate_id"), str)
        )
        duplicate_ids = {
            candidate_id
            for candidate_id, count in candidate_id_counts.items()
            if count > 1
        }
        for candidate_id in sorted(duplicate_ids):
            issues.append(ProvenanceCorrectionIssue(
                check="correction_scope",
                code="DUPLICATE_CANDIDATE_CORRECTION",
                candidate_id=candidate_id,
                message="A candidate may be corrected at most once.",
            ))

        applied_ids: set[str] = set()
        for index, correction in enumerate(corrections):
            candidate_id_value = correction.get("candidate_id")
            candidate_id = (
                candidate_id_value
                if isinstance(candidate_id_value, str) and candidate_id_value
                else f"<row:{index}>"
            )
            row_issue_count = len(issues)
            unknown_fields = sorted(set(correction) - CORRECTION_FIELDS)
            if unknown_fields:
                issues.append(ProvenanceCorrectionIssue(
                    check="correction_fields",
                    code="UNKNOWN_CORRECTION_FIELDS",
                    candidate_id=candidate_id,
                    message=f"Unknown correction fields: {unknown_fields}.",
                ))
            if candidate_id in duplicate_ids:
                continue

            raw = raw_by_id.get(candidate_id)
            view = effective_by_id.get(candidate_id)
            if raw is None or view is None:
                issues.append(ProvenanceCorrectionIssue(
                    check="candidate_reference",
                    code="CANDIDATE_NOT_FOUND",
                    candidate_id=candidate_id,
                    message="Correction candidate ID does not exist in raw staging data.",
                ))
                continue

            self._validate_correction(
                raw=raw,
                correction=correction,
                candidate_id=candidate_id,
                expected_source_code=expected_source_code,
                subsource_by_code=subsource_by_code,
                issues=issues,
            )
            if len(issues) != row_issue_count or correction_code is None:
                continue

            original_values = {
                field: raw.get(field) for field in PRESERVED_PROVENANCE_FIELDS
            }
            view["corrected_subsource_code"] = correction[
                "corrected_subsource_code"
            ]
            view["provenance_correction_code"] = correction_code
            if any(
                view.get(field) != value
                for field, value in original_values.items()
            ):
                issues.append(ProvenanceCorrectionIssue(
                    check="preserved_provenance",
                    code="PRESERVED_PROVENANCE_CHANGED",
                    candidate_id=candidate_id,
                    message="Applying the correction changed immutable raw provenance.",
                ))
                view.pop("corrected_subsource_code", None)
                view.pop("provenance_correction_code", None)
                continue
            applied_ids.add(candidate_id)

        sorted_issues = tuple(sorted(set(issues)))
        return ProvenanceCorrectionResult(
            candidates=tuple(effective),
            report=ProvenanceCorrectionReport(
                path=path.as_posix(),
                status="PASS" if not sorted_issues else "FAIL",
                correction_code=correction_code,
                total=len(corrections),
                applied=len(applied_ids),
                corrected_candidate_ids=tuple(sorted(applied_ids)),
                issues=sorted_issues,
            ),
        )

    @staticmethod
    def _load_payload(
        path: Path,
        issues: list[ProvenanceCorrectionIssue],
    ) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            issues.append(ProvenanceCorrectionIssue(
                check="correction_file",
                code="INVALID_CORRECTION_FILE",
                candidate_id="<file>",
                message=f"Cannot load provenance corrections: {error}.",
            ))
            return {}
        if isinstance(value, dict):
            return value
        issues.append(ProvenanceCorrectionIssue(
            check="correction_file",
            code="INVALID_CORRECTION_FILE_SHAPE",
            candidate_id="<file>",
            message="Provenance correction file must contain an object.",
        ))
        return {}

    @staticmethod
    def _validate_correction(
        *,
        raw: dict[str, Any],
        correction: dict[str, Any],
        candidate_id: str,
        expected_source_code: str | None,
        subsource_by_code: dict[str, dict[str, Any]],
        issues: list[ProvenanceCorrectionIssue],
    ) -> None:
        if raw.get("source_code") != expected_source_code:
            issues.append(ProvenanceCorrectionIssue(
                check="source_match",
                code="SOURCE_CODE_MISMATCH",
                candidate_id=candidate_id,
                message="Candidate source_code does not match the correction source.",
            ))
        correction_page = correction.get("source_page")
        candidate_page = raw.get("source_page")
        if correction_page != candidate_page:
            issues.append(ProvenanceCorrectionIssue(
                check="page_match",
                code="SOURCE_PAGE_MISMATCH",
                candidate_id=candidate_id,
                message="Correction source_page does not match the raw candidate page.",
            ))

        original_code = correction.get("original_subsource_code")
        corrected_code = correction.get("corrected_subsource_code")
        if original_code != raw.get("subsource_code"):
            issues.append(ProvenanceCorrectionIssue(
                check="original_subsource",
                code="ORIGINAL_SUBSOURCE_MISMATCH",
                candidate_id=candidate_id,
                message=(
                    "original_subsource_code does not match the raw candidate "
                    "subsource_code."
                ),
            ))
        original_subsource = (
            subsource_by_code.get(original_code)
            if isinstance(original_code, str)
            else None
        )
        corrected_subsource = (
            subsource_by_code.get(corrected_code)
            if isinstance(corrected_code, str)
            else None
        )
        if corrected_subsource is None:
            issues.append(ProvenanceCorrectionIssue(
                check="corrected_subsource",
                code="CORRECTED_SUBSOURCE_NOT_FOUND",
                candidate_id=candidate_id,
                message="corrected_subsource_code does not exist in the catalog.",
            ))
            return
        if corrected_subsource.get("source_code") != expected_source_code:
            issues.append(ProvenanceCorrectionIssue(
                check="corrected_subsource",
                code="CORRECTED_SUBSOURCE_SOURCE_MISMATCH",
                candidate_id=candidate_id,
                message="Corrected subsource does not belong to the correction source.",
            ))
        if not QuestionProvenanceCorrectionResolver._page_in_range(
            candidate_page, corrected_subsource
        ):
            issues.append(ProvenanceCorrectionIssue(
                check="corrected_subsource",
                code="CORRECTED_SUBSOURCE_PAGE_OUT_OF_RANGE",
                candidate_id=candidate_id,
                message="Candidate page is outside the corrected subsource range.",
            ))
        if original_subsource is None:
            issues.append(ProvenanceCorrectionIssue(
                check="original_subsource",
                code="ORIGINAL_SUBSOURCE_NOT_FOUND",
                candidate_id=candidate_id,
                message="original_subsource_code does not exist in the catalog.",
            ))
        elif QuestionProvenanceCorrectionResolver._page_in_range(
            candidate_page, original_subsource
        ):
            issues.append(ProvenanceCorrectionIssue(
                check="original_subsource",
                code="ORIGINAL_SUBSOURCE_PAGE_STILL_IN_RANGE",
                candidate_id=candidate_id,
                message="Candidate page still falls inside the original subsource range.",
            ))

    @staticmethod
    def _page_in_range(page: Any, subsource: dict[str, Any]) -> bool:
        start_page = subsource.get("start_page")
        end_page = subsource.get("end_page")
        return (
            isinstance(page, int)
            and not isinstance(page, bool)
            and isinstance(start_page, int)
            and not isinstance(start_page, bool)
            and isinstance(end_page, int)
            and not isinstance(end_page, bool)
            and start_page <= page <= end_page
        )
