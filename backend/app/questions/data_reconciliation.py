"""Audit and reversibly quarantine unsafe local Question Bank rows.

This never edits academic content or review files. A REVIEW row remains in the
database for source correction, but is not selected as an approved question.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.questions.models import (
    Question, QuestionGroup, QuestionStatus, QuestionType,
)
from app.questions.presentation_quality import (
    has_broken_math_extraction, question_has_broken_math_extraction,
)


DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "questions" / "math" / "grade12"


@dataclass(frozen=True)
class StatusChange:
    id: str
    source_reference: str | None
    old_status: str
    new_status: str
    reasons: tuple[str, ...]
    content_hash: str | None = None


@dataclass(frozen=True)
class ReconciliationPlan:
    questions: tuple[StatusChange, ...]
    groups: tuple[StatusChange, ...]

    def summary(self) -> dict[str, object]:
        reasons = Counter(reason for row in (*self.questions, *self.groups) for reason in row.reasons)
        return {"questions": len(self.questions), "groups": len(self.groups),
                "reasons": dict(sorted(reasons.items()))}


def _review_exclusions(root: Path) -> tuple[set[str], set[str]]:
    standalone: set[str] = set()
    groups: set[str] = set()
    for dataset in ("vector_coordinates_v0_1", "grouped_data_dispersion_v0_1"):
        review = root / dataset / "academic_review" / "v0_1"
        for row in json.loads((review / "standalone_reviews.json").read_text(encoding="utf-8")):
            if row["review_status"] != "VERIFIED":
                standalone.add(row["candidate_id"])
        for row in json.loads((review / "group_reviews.json").read_text(encoding="utf-8")):
            if row["review_status"] != "VERIFIED":
                # Imported Vector groups reference source evidence; Dispersion
                # groups reference the source candidate. Match either form.
                groups.update(filter(None, (row.get("source_evidence_id"), row.get("source_candidate_id"))))
        if dataset == "vector_coordinates_v0_1":
            overrides = json.loads((root / dataset / "staging" / "materialized_v0_1" /
                                    "scope_review_overrides.json").read_text(encoding="utf-8"))
            standalone.update(row["candidate_id"] for row in overrides["decisions"])
    return standalone, groups


def build_plan(session: Session, *, data_root: Path = DATA_ROOT) -> ReconciliationPlan:
    excluded_questions, excluded_groups = _review_exclusions(data_root)
    questions = list(session.scalars(select(Question).options(
        selectinload(Question.options), selectinload(Question.problem_type_links),
        selectinload(Question.concept_links), selectinload(Question.learning_outcome_links),
    )))
    groups = list(session.scalars(select(QuestionGroup).options(
        selectinload(QuestionGroup.items),
    )))
    by_id = {question.id: question for question in questions}
    question_reasons: dict[UUID, set[str]] = defaultdict(set)
    group_reasons: dict[UUID, set[str]] = defaultdict(set)

    for question in questions:
        if question.status != QuestionStatus.APPROVED:
            continue
        if question.source_reference in excluded_questions:
            question_reasons[question.id].add("SOURCE_REVIEW_NOT_VERIFIED")
        if question_has_broken_math_extraction(question):
            question_reasons[question.id].add("PDF_TEXT_NEEDS_SOURCE_REVIEW")
        if question.question_type in {QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE,
                                      QuestionType.SHORT_ANSWER} and not question.correct_answer:
            question_reasons[question.id].add("OBJECTIVE_ANSWER_MISSING")
        # The explicit SAMPLE_TEST open-response row is a local handwriting/OCR
        # sandbox. It has no academic mappings and is already excluded by all
        # classified practice selectors; preserve existing student drafts.
        is_ocr_sandbox = (question.source_type == "SAMPLE_TEST"
                          and question.question_type == QuestionType.OPEN_RESPONSE)
        if not is_ocr_sandbox and (
            not question.problem_type_links or not question.concept_links
            or not question.learning_outcome_links
        ):
            question_reasons[question.id].add("ACADEMIC_MAPPING_INCOMPLETE")

    for group in groups:
        if group.status != QuestionStatus.APPROVED:
            continue
        if group.source_reference in excluded_groups:
            group_reasons[group.id].add("SOURCE_REVIEW_NOT_VERIFIED")
        if has_broken_math_extraction(group.content):
            group_reasons[group.id].add("PDF_TEXT_NEEDS_SOURCE_REVIEW")
        if len(group.items) != 4:
            group_reasons[group.id].add("GROUP_STRUCTURE_INVALID")
        for item in group.items:
            child = by_id.get(item.question_id)
            if child is None or child.status != QuestionStatus.APPROVED:
                group_reasons[group.id].add("GROUP_CHILD_UNAVAILABLE")
            elif child.id in question_reasons:
                group_reasons[group.id].add("GROUP_CHILD_NEEDS_REVIEW")
        if group.id in group_reasons:
            # Group children are never independently selectable, but keeping
            # their status in sync prevents another path from grading them.
            for item in group.items:
                child = by_id.get(item.question_id)
                if child is not None and child.status == QuestionStatus.APPROVED:
                    question_reasons[child.id].add("GROUP_NEEDS_REVIEW")

    q_changes = tuple(StatusChange(str(q.id), q.source_reference, q.status.value,
                                   QuestionStatus.REVIEW.value, tuple(sorted(question_reasons[q.id])),
                                   q.content_hash)
                      for q in sorted(questions, key=lambda row: str(row.id)) if q.id in question_reasons)
    g_changes = tuple(StatusChange(str(g.id), g.source_reference, g.status.value,
                                   QuestionStatus.REVIEW.value, tuple(sorted(group_reasons[g.id])))
                      for g in sorted(groups, key=lambda row: str(row.id)) if g.id in group_reasons)
    return ReconciliationPlan(q_changes, g_changes)


def apply_plan(session: Session, plan: ReconciliationPlan, *, backup_path: Path) -> None:
    """Write backup first; update only exact still-APPROVED rows; commit once."""
    if get_settings().app_env not in {"development", "test"}:
        raise ValueError("Question data reconciliation is development/test only.")
    if backup_path.exists():
        raise ValueError("Backup file already exists; choose a new path.")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup = {"created_at": datetime.now(timezone.utc).isoformat(),
              "questions": [asdict(row) for row in plan.questions],
              "groups": [asdict(row) for row in plan.groups]}
    with backup_path.open("x", encoding="utf-8") as stream:
        json.dump(backup, stream, ensure_ascii=False, indent=2)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    try:
        for row in plan.questions:
            result = session.execute(update(Question).where(
                Question.id == UUID(row.id), Question.status == QuestionStatus.APPROVED,
                Question.content_hash == row.content_hash,
                Question.source_reference == row.source_reference,
            ).values(status=QuestionStatus.REVIEW))
            if result.rowcount != 1:
                raise RuntimeError(f"Question changed since audit: {row.id}")
        for row in plan.groups:
            result = session.execute(update(QuestionGroup).where(
                QuestionGroup.id == UUID(row.id), QuestionGroup.status == QuestionStatus.APPROVED,
                QuestionGroup.source_reference == row.source_reference,
            ).values(status=QuestionStatus.REVIEW))
            if result.rowcount != 1:
                raise RuntimeError(f"Group changed since audit: {row.id}")
        session.commit()
    except Exception:
        session.rollback()
        raise
