"""Portable, private release of reviewed PA2 records and their bound rubrics."""
from types import SimpleNamespace

from app.math_solutions.grading_context import _validate_rubric
from app.math_solutions.grading_profile import OCR_SOURCE, verify_reference
from app.questions.import_schemas import QuestionImportRecord
from app.questions.models import QuestionType
from app.questions.ocr_curated import CuratedItem, PreparedOCR, digest, presentation_errors


def build_release(prepared_batches: list[PreparedOCR], *, expected_count: int = 345) -> dict:
    items = {}
    for batch in prepared_batches:
        for item in batch.items:
            if item.source_id in items:
                raise ValueError(f"Repeated release source: {item.source_id}")
            items[item.source_id] = {"source_id": item.source_id,
                                     "question": item.record.model_dump(mode="json"), "rubric": item.rubric}
    if len(items) != expected_count:
        raise ValueError(f"Expected {expected_count} release questions, got {len(items)}")
    release = {"format": "ocr-pa2-release-v1", "expected_count": expected_count,
               "items": [items[k] for k in sorted(items)]}
    return {**release, "sha256": digest(release)}


def prepare_release(release: dict) -> PreparedOCR:
    payload = {key: value for key, value in release.items() if key != "sha256"}
    if release.get("format") != "ocr-pa2-release-v1" or digest(payload) != release.get("sha256"):
        raise ValueError("Invalid release format or checksum")
    if len(release["items"]) != release["expected_count"] or release["expected_count"] != 345:
        raise ValueError("This milestone must contain exactly 345 reviewed questions")
    seen, items = set(), []
    for row in release["items"]:
        record = QuestionImportRecord.model_validate(row["question"])
        if (record.source != OCR_SOURCE or record.question_type != QuestionType.OPEN_RESPONSE
                or record.source_reference != row["source_id"] or row["source_id"] in seen
                or not record.explanation or not record.problem_types or not record.learning_outcomes):
            raise ValueError("Invalid or repeated curated question identity")
        seen.add(row["source_id"])
        rubric = row["rubric"]
        profile = verify_reference(SimpleNamespace(criteria=rubric), SimpleNamespace(
            source_type=record.source, content=record.content, correct_answer=record.correct_answer,
            explanation=record.explanation))
        _validate_rubric(SimpleNamespace(criteria=rubric, max_score=1.0))
        if profile["concept_weights"] != {c.code: c.weight for c in record.concepts}:
            raise ValueError("Release rubric concept weights do not match the question")
        if {c.code for c in record.concepts} != {code for c in profile["criteria"] for code in c["concept_codes"]}:
            raise ValueError("Release rubric must assess exactly the mapped concepts")
        provenance = profile["provenance"]
        if (f"{provenance['dataset']}:{provenance['source_id']}" != row["source_id"]
                or provenance["review"].get("status") != "VERIFIED"
                or not provenance["review"].get("notes") or not provenance["review"].get("reviewer")):
            raise ValueError("Release requires the original explicit curation provenance")
        for value in [record.content, record.correct_answer or "", record.explanation]:
            if presentation_errors(value):
                raise ValueError("Release presentation failed structural validation")
        items.append(CuratedItem(row["source_id"], record, rubric))
    return PreparedOCR(tuple(items), {"release_sha256": release["sha256"], "ready": len(items),
                                      "not_selected": 0, "version": 1})
