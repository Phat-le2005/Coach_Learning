"""Offline OCR curation and atomic promotion through the existing importer.

The overlay is deliberate editorial data, never an automatic approval of OCR.
Source files, overlays and generated reports belong in ignored private storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.math_solutions.cubic_monotonicity import CubicModel
from app.math_solutions.grading_context import _validate_rubric
from app.math_solutions.grading_profile import OCR_SOURCE, PROFILE, reference_digest
from app.math_solutions.models import SolutionRubric
from app.math_solutions.validator import DeterministicMathValidator
from app.math_solutions.numeric_reference import NUMERIC_PROFILE, NumericReferenceValidator
from app.questions.fingerprint import question_content_hash
from app.questions.import_schemas import QuestionImportRecord
from app.questions.import_service import QuestionImportService
from app.questions.models import ImportRowStatus, Question, QuestionStatus, QuestionType
from app.users.models import Role, User


def digest(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def presentation_errors(text: str) -> list[str]:
    """Structural checks supplement editorial review; they do not prove mathematics."""
    errors = []
    depth = 0
    for char in re.sub(r"\\[{}]", "", text):
        depth += (char == "{") - (char == "}")
        if depth < 0:
            break
    if depth != 0:
        errors.append("UNBALANCED_LATEX_BRACES")
    if len(re.findall(r"(?<!\\)\$", text)) % 2:
        errors.append("UNBALANCED_MATH_DELIMITERS")
    outside_math = re.sub(r"\$\$.*?\$\$|(?<!\\)\$(?:\\.|[^$])*?(?<!\\)\$|\\\(.*?\\\)|\\\[.*?\\\]", "", text, flags=re.S)
    if re.search(r"\\[A-Za-z]+|[A-Za-z]_\{", outside_math):
        errors.append("TEX_OUTSIDE_MATH_DELIMITERS")
    if any(delimiter in outside_math for delimiter in (r"\(", r"\)", r"\[", r"\]")):
        errors.append("UNBALANCED_MATH_DELIMITERS")
    if re.search(r"_\{[^}]*[;…]|\\(?:input|include|href|html|url)\b", text):
        errors.append("LATEX_REVIEW_REQUIRED")
    if re.search(r"!\[|<\s*(?:img|script|iframe)\b", text, re.I):
        errors.append("MEDIA_OUTSIDE_INITIAL_CAPABILITY")
    return errors


@dataclass(frozen=True)
class CuratedItem:
    source_id: str
    record: QuestionImportRecord
    rubric: dict


@dataclass(frozen=True)
class PreparedOCR:
    items: tuple[CuratedItem, ...]
    report: dict


def prepare_overlay(overlay: dict, source_paths: dict[str, Path]) -> PreparedOCR:
    """Pure read-only preparation. No Session is accepted or created."""
    if overlay.get("version") != 1 or not isinstance(overlay.get("items"), list) or not overlay["items"]:
        raise ValueError("Expected a non-empty version 1 curated overlay")
    sources = {}
    for name, spec in overlay.get("sources", {}).items():
        path = source_paths[name]
        if path.name != "content.draft.pretty.json":
            raise ValueError("Only content.draft.pretty.json is authoritative")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != spec["sha256"]:
            raise ValueError(f"Source digest changed: {name}")
        rows = json.loads(raw)
        sources[name] = {row["question_id"]: row for row in rows}
        if len(rows) != len(sources[name]):
            raise ValueError("Source IDs must be unique")
    items, report_rows, seen_ids, seen_content = [], [], set(), set()
    for item in overlay["items"]:
        name, identifier = item["dataset"], item["source_id"]
        source_key = f"{name}:{identifier}"
        raw = sources[name][identifier]
        if source_key in seen_ids or digest(raw) != item["source_record_sha256"]:
            raise ValueError(f"Duplicate or changed source record: {source_key}")
        seen_ids.add(source_key)
        review = item.get("review", {})
        if review.get("status") != "VERIFIED" or not review.get("reviewer") or not review.get("notes"):
            raise ValueError(f"Explicit review required: {source_key}")
        record = QuestionImportRecord.model_validate(item["question"])
        if record.source != OCR_SOURCE or record.source_reference != source_key:
            raise ValueError("Curated source identity must be stable and explicit")
        if record.question_type != QuestionType.OPEN_RESPONSE or not record.explanation:
            raise ValueError("Initial capability requires a written problem and reviewed solution")
        if not record.problem_types or not record.learning_outcomes or not item.get("difficulty_basis"):
            raise ValueError("Explicit curriculum mapping and difficulty basis required")
        # Every edited presentation field is acknowledged, including image-to-text references.
        for field, original in (("content", raw["question"]["markdown"]),
                                ("explanation", raw["solution"]["markdown"]),
                                ("correct_answer", raw["answer"]["markdown"] or None)):
            replacement = getattr(record, field)
            if replacement != original:
                correction = next((c for c in item.get("corrections", []) if c.get("field") == field), None)
                if (not correction or correction.get("before_sha256") != digest(original)
                        or correction.get("after_sha256") != digest(replacement) or not correction.get("reason")):
                    raise ValueError(f"Unacknowledged editorial change: {source_key}:{field}")
        for field in ("content", "explanation", "correct_answer"):
            errors = presentation_errors(getattr(record, field) or "")
            if errors:
                raise ValueError(f"{source_key}:{field}: {','.join(errors)}")
        fingerprint = question_content_hash(record.content)
        if fingerprint in seen_content:
            raise ValueError("Duplicate curated content")
        seen_content.add(fingerprint)
        numeric = item.get("grading_profile") == NUMERIC_PROFILE
        model = None
        if not numeric:
            validator = DeterministicMathValidator(record.content)
            model = CubicModel.from_expression(validator._target_expr, validator.x)
            if model is None or len(re.findall(r"(?:y|f\(x\))\s*=", record.content)) != 1:
                raise ValueError("Only one supported cubic target is permitted")
        rubric = {"grading_profile": item.get("grading_profile", PROFILE), "task": item["task"],
                  "reference_sha256": reference_digest(record.content, record.correct_answer, record.explanation),
                  "concept_weights": {c.code: c.weight for c in record.concepts},
                  "criteria": item["criteria"], "provenance": {
                      "dataset": name, "source_id": identifier, "source_sha256": overlay["sources"][name]["sha256"],
                      "source_record_sha256": digest(raw), "review": review,
                      "corrections": item.get("corrections", []), "difficulty_basis": item["difficulty_basis"],
                      "delivery_adaptation": item.get("delivery_adaptation"),
                      "source_spans": raw["question"].get("source_spans", [])}}
        _validate_rubric(SimpleNamespace(criteria=rubric, max_score=1.0))
        mapped = {c.code for c in record.concepts}
        assessed = {code for criterion in item["criteria"] for code in criterion["concept_codes"]}
        if mapped != assessed:
            raise ValueError("Concept links must exactly match assessed rubric concepts")
        if numeric:
            status = NumericReferenceValidator(rubric).validate_step("CONCLUSION", record.correct_answer).validity.value
        elif item["task"] == "all_intervals":
            status, _ = model.check_conclusion(record.correct_answer or "", complete=True)
        else:
            status, _ = model.check_numeric_conclusion(record.correct_answer or "", "", item["task"])
        if status != "VALID":
            raise ValueError("Reviewed final answer disagrees with the mathematical target")
        items.append(CuratedItem(source_key, record, rubric))
        report_rows.append({"source_id": source_key, "status": "READY", "task": item["task"], "content_hash": fingerprint})
    counts = {name: len(rows) for name, rows in sources.items()}
    return PreparedOCR(tuple(items), {"version": 1, "overlay_sha256": digest(overlay), "source_counts": counts,
                                     "ready": len(items), "not_selected": sum(counts.values()) - len(items), "rows": report_rows})


class CuratedOCRImportService:
    def __init__(self, session: Session):
        self.session = session

    def apply(self, prepared: PreparedOCR, actor: User) -> dict:
        """All-or-nothing creation of questions, mapping, rubric and publication.

        Does not commit: the caller owns the transaction, including report handling.
        Existing questions are never silently edited or taken over.
        """
        if actor.role != Role.ADMIN or not actor.is_active:
            raise ApplicationError(403, "CURATED_IMPORT_ADMIN_REQUIRED", "An active admin must publish reviewed OCR.")
        importer = QuestionImportService(self.session)
        importer._lock_imports()
        validated = importer._validate_rows([(i, item.record.model_dump(mode="json"))
                                             for i, item in enumerate(prepared.items, 1)])
        if any(row.status != ImportRowStatus.VALID for row in validated):
            raise ValueError(f"Catalog validation rejected: {[(r.row_number, r.errors) for r in validated if r.errors]}")
        pending, result = [], []
        for item, validated_row in zip(prepared.items, validated):
            existing = list(self.session.scalars(select(Question).where(
                Question.source_type == OCR_SOURCE, Question.source_reference == item.source_id)))
            if existing:
                question = existing[0]
                rubrics = list(self.session.scalars(select(SolutionRubric).where(SolutionRubric.question_id == question.id)))
                if (len(existing) != 1 or question.status != QuestionStatus.APPROVED
                        or reference_digest(question.content, question.correct_answer, question.explanation) != item.rubric["reference_sha256"]
                        or not any(r.status == "APPROVED" and r.criteria == item.rubric for r in rubrics)
                        or question.difficulty != item.record.difficulty
                        or not _mappings_unchanged(question, validated_row.normalized_data)
                        or question.question_type != item.record.question_type or question.exam_weight != item.record.exam_weight):
                    raise ValueError(f"Existing curated question changed: {item.source_id}")
                result.append({"source_id": item.source_id, "status": "UNCHANGED", "question_id": str(question.id)})
            else:
                pending.append(item)
        if pending:
            preview = importer.preview(actor, file_name="reviewed-ocr.json", content=json.dumps(
                [item.record.model_dump(mode="json") for item in pending], ensure_ascii=False).encode("utf-8"), commit=False)
            if preview.report.valid != len(pending):
                raise ValueError(f"Import rejected: {[(r.row_number, r.status.value, r.errors) for r in preview.rows]}")
            confirmed = importer.confirm(actor, preview.batch_id, commit=False)
            if confirmed.report.imported != len(pending):
                raise ValueError("Reference or duplicate changed during import")
            for item, row in zip(pending, confirmed.rows):
                question = self.session.get(Question, row.imported_question_id)
                title = "Tiêu chí theo từng đại lượng từ nguồn OCR đã kiểm tra" if item.rubric["grading_profile"] == NUMERIC_PROFILE else "Tiêu chí đơn điệu từ nguồn OCR đã kiểm tra"
                rubric = SolutionRubric(question_id=question.id, title=title,
                                        criteria=item.rubric, status="APPROVED", max_score=1.0,
                                        approved_by=actor.id, approved_at=datetime.now(timezone.utc))
                self.session.add(rubric)
                question.status = QuestionStatus.APPROVED
                result.append({"source_id": item.source_id, "status": "IMPORTED", "question_id": str(question.id)})
        self.session.flush()
        return {**prepared.report, "applied_rows": result}


def _mappings_unchanged(question: Question, normalized: dict) -> bool:
    if str(question.subject_id) != normalized["subject_id"]:
        return False
    return (
        {str(link.concept_id): link.weight for link in question.concept_links}
        == {item["concept_id"]: item["weight"] for item in normalized["concepts"]}
        and {str(link.problem_type_id): (link.weight, link.is_primary) for link in question.problem_type_links}
        == {item["problem_type_id"]: (item["weight"], item["is_primary"]) for item in normalized["problem_types"]}
        and {str(link.learning_outcome_id): link.weight for link in question.learning_outcome_links}
        == {item["learning_outcome_id"]: item["weight"] for item in normalized["learning_outcomes"]}
    )
