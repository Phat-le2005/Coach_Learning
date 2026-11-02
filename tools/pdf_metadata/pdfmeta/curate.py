"""Create a typed, source-grounded authoring batch; never a production import."""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator

from .storage import file_hash, read_json, write_json, write_jsonl
from .text_cleanup import clean_steps, is_suspicious


def decimal_value(text: str, *, source_punctuation: bool = False) -> str | None:
    text = text.strip().replace("−", "-").replace("", "-")
    if source_punctuation:
        text = re.sub(r"\s*\.\s*$", "", text)
    if len(text) > 128 or not re.fullmatch(r"[+-]?\d+(?:[,.]\d+)?", text):
        return None
    try:
        value = Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return "0" if value == 0 else result.lstrip("+")


def build_batch(pilot: Path, state: dict | None = None) -> dict:
    manifest = read_json(pilot / "manifest.json")
    config = read_json(Path(__file__).parents[1] / "fixtures" / "pilot20-editorial.json")
    if config["source_sha256"] != manifest["source_sha256"]:
        raise ValueError("This editorial configuration belongs to a different source PDF")
    path = pilot / "questions.enriched.candidates.jsonl"
    generation = file_hash(path)
    items = {i["source_number"]: i for i in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}
    if state is None:
        from .review_store import ReviewStore
        state = ReviewStore(pilot).snapshot()
    records = []
    pages = {page["page_number"]: page for page in
             (read_json(path) for path in (pilot / "pages").glob("*.json"))}
    raw_evidence = []
    for spec in config["items"]:
        source = items[spec["number"]]
        source_answer = decimal_value(source["answer"]["text_raw"], source_punctuation=True)
        if source_answer != spec["expected_source_answer"]:
            raise ValueError(f"Source answer differs from visually checked fixture: q{spec['number']}")
        saved = state.get("reviews", {}).get(source["question_id"])
        stale = bool(saved and saved["base_generation"] != generation)
        edits = saved["fields"] if saved and not stale else {}
        answer_text = edits.get("answer_text", source["answer"]["text_raw"])
        expected = decimal_value(answer_text, source_punctuation=not bool(edits))
        issues = spec["issues"]
        record = {
            "schema_version": "assessment-authoring/v2", "question_id": source["question_id"],
            "source_number": spec["number"], "topic_label_candidate": spec["topic"],
            "source": {"sha256": manifest["source_sha256"], "candidate_generation": generation,
                       "stem_spans": source["stem"]["source_spans"], "answer_spans": source["answer"]["source_spans"],
                       "solution_spans": source["solution"]["source_spans"]},
            "student_view": {"content_markdown": edits.get("stem_markdown", spec["stem_markdown"]),
                             "assets": [s["asset_path"] for s in source["stem"]["source_spans"]],
                             "visual_required": spec.get("visual_required", False)},
            "answer_spec": {"kind": "NUMBER" if expected is not None else "UNRESOLVED", "expected_decimal": expected,
                            "source_answer_raw": source["answer"]["text_raw"], "editorial_answer": answer_text,
                            "comparison_policy_candidate": "EXACT_DECIMAL_COMMA_OR_DOT",
                            "rounding_instruction": spec.get("rounding_instruction"), "unit": spec["unit"], "status": "DRAFT"},
            "math_spec": {"expression_latex": spec["expression_latex"], "variable_names": spec["variables"],
                          "domain_latex": spec["domain_latex"], "status": "DRAFT_NEEDS_ACADEMIC_REVIEW"},
            "reference_solution": {"editorial_markdown": edits.get("solution_markdown", ""),
                                   "step_candidates": clean_steps(source, pages, edits.get("formula_corrections", [])),
                                   "status": "NOT_ACADEMICALLY_REVIEWED"},
            "editorial_formula_corrections": edits.get("formula_corrections", []),
            "review": {"source_status": saved["status"] if saved and not stale else "PREPARED_FOR_REVIEW",
                       "revision": saved["revision"] if saved else 0, "stale": stale,
                       "stem_answer_visual_check": "CODEX_SOURCE_COMPARISON", "source_issues": issues,
                       "field_checks": saved["field_checks"] if saved and not stale else {}},
            "academic_review": "PENDING", "grading_support": "NOT_ASSESSED", "publishable": False,
        }
        if any(is_suspicious(char) for char in json.dumps(record, ensure_ascii=False)):
            raise ValueError(f"Unnormalized glyph in authored fields of q{spec['number']}; review the editorial input")
        records.append(record)
        raw_evidence.append({"question_id": source["question_id"], "source_number": spec["number"],
                             "source_sha256": manifest["source_sha256"], "purpose": "RAW_EVIDENCE_NOT_FOR_GRADING",
                             "step_candidates_raw": source["reference_steps"]})
    schema = read_json(Path(__file__).parents[1] / "schemas" / "assessment-authoring.v2.schema.json")
    validator = Draft202012Validator(schema)
    for record in records:
        validator.validate(record)
    directory = pilot / "exports"
    write_jsonl(directory / "pilot20.authoring.jsonl", records)
    write_json(directory / "pilot20.authoring.pretty.json", records)
    write_jsonl(directory / "pilot20.raw-evidence.jsonl", raw_evidence)
    readable = ["# Bộ 20 bài - bản biên soạn\n", "Đề và đáp án đã đối chiếu nguồn. Lời giải và công thức nhận dạng vẫn là ứng viên; chưa dùng chấm.\n"]
    for record in records:
        readable += [f"## Câu {record['source_number']}\n", record["student_view"]["content_markdown"] + "\n",
                     f"**Đáp án ghi trong nguồn:** {record['answer_spec']['source_answer_raw']}\n"]
        for issue in record["review"]["source_issues"]:
            readable.append(f"> Cần duyệt: {issue['note']}\n")
        readable.append("### Các đoạn lời giải ứng viên\n")
        for index, step in enumerate(record["reference_solution"]["step_candidates"], 1):
            readable.append(f"**Đoạn {index} - chữ nguồn đã đổi font, còn mất bố cục toán:**\n\n```text\n{step['text_candidate']}\n```\n")
            for candidate in step["latex_candidates"]:
                readable.append(f"LaTeX ứng viên ({candidate['parser_id']}, trang {candidate['page_number']}):\n\n$${candidate['latex'].strip().strip('$')}$$\n")
    (directory / "pilot20.readable.md").write_text("\n".join(readable), encoding="utf-8")
    # Student preview carries source stem assets only. It intentionally contains no answer/spec/solution fields.
    student = [{"question_id": r["question_id"], "source_number": r["source_number"], **r["student_view"],
                "preview_only": True} for r in records]
    write_json(directory / "pilot20.student-preview.json", student)
    report = {"schema_version": "authoring-export-report/v1", "source_sha256": manifest["source_sha256"],
              "candidate_generation": generation, "document_revision": state.get("document_revision", 0),
              "batch_size": len(records), "numeric_answer_candidates": sum(r["answer_spec"]["kind"] == "NUMBER" for r in records),
              "source_issue_items": [r["source_number"] for r in records if r["review"]["source_issues"]],
              "source_verified_items": [r["source_number"] for r in records if r["review"]["source_status"] == "SOURCE_VERIFIED"],
              "authoring_schema": "assessment-authoring/v2",
              "private_use_or_replacement_characters_in_clean_export": 0,
              "normalized_symbol_glyphs": sum(s["normalization"]["mapped_glyph_count"] for r in records for s in r["reference_solution"]["step_candidates"]),
              "unresolved_font_glyphs": sum(s["normalization"]["unresolved_glyph_count"] for r in records for s in r["reference_solution"]["step_candidates"]),
              "academic_approved_count": 0, "grading_ready_count": 0, "publishable_count": 0}
    write_json(directory / "pilot20.report.json", report)
    write_json(pilot / "curation.json", {"source_sha256": manifest["source_sha256"], "items": config["items"]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_batch(args.pilot), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
