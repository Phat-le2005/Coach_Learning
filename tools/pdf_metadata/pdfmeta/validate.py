from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA = json.loads((Path(__file__).parents[1] / "schemas" / "question-candidate.v1.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


def validate_candidates(items: list[dict], pages: list[dict], output: Path | None = None) -> dict:
    errors = []
    lookup = {page["page_number"]: page for page in pages}
    ids = [item["question_id"] for item in items]
    if len(set(ids)) != len(ids):
        errors.append("DUPLICATE_QUESTION_IDS")
    for item in items:
        errors.extend(f"SCHEMA:{item.get('question_id')}:{error.json_path}:{error.message}"
                      for error in VALIDATOR.iter_errors(item))
        if item["publishable"] is not False or item["academic_review"] != "PENDING" or item["grading_support"] != "NOT_ASSESSED":
            errors.append(f"UNREVIEWED_PROMOTION:{item['question_id']}")
        for part in (item["stem"], item["answer"], item["solution"], *item["reference_steps"]):
            for source in part["source_spans"]:
                page = lookup.get(source["page_number"])
                if page is None:
                    errors.append(f"UNKNOWN_PAGE:{item['question_id']}")
                    continue
                x0, y0, x1, y1 = source["bbox"]
                if not (0 <= x0 < x1 <= page["width"] + 0.01 and 0 <= y0 < y1 <= page["height"] + 0.01):
                    errors.append(f"INVALID_BBOX:{item['question_id']}:{source}")
                valid_ids = {block["block_id"] for block in page["blocks"]}
                if not set(source["block_ids"]).issubset(valid_ids):
                    errors.append(f"UNKNOWN_BLOCK:{item['question_id']}")
                if output and source.get("asset_path") and not (output / source["asset_path"]).is_file():
                    errors.append(f"MISSING_ASSET:{source['asset_path']}")
        stem_ids = {b for s in item["stem"]["source_spans"] for b in s["block_ids"]}
        private_ids = {b for name in ("answer", "solution") for s in item[name]["source_spans"] for b in s["block_ids"]}
        if stem_ids & private_ids:
            errors.append(f"STEM_PRIVATE_SOURCE_OVERLAP:{item['question_id']}")
        for public in item["stem"]["source_spans"]:
            for private in item["answer"]["source_spans"] + item["solution"]["source_spans"]:
                if public["page_number"] != private["page_number"]:
                    continue
                a, b = public["bbox"], private["bbox"]
                if min(a[2], b[2]) - max(a[0], b[0]) > 1 and min(a[3], b[3]) - max(a[1], b[1]) > 1:
                    errors.append(f"STEM_PRIVATE_CROP_OVERLAP:{item['question_id']}")
        for block in item.get("ocr_evidence", []):
            page = lookup.get(block["page_number"])
            x0, y0, x1, y1 = block["bbox"]
            if page is None or not (0 <= x0 < x1 <= page["width"] + 0.01 and 0 <= y0 < y1 <= page["height"] + 0.01):
                errors.append(f"INVALID_OCR_SOURCE_BBOX:{item['question_id']}:{block['block_id']}")
        source_text = item["solution"]["text_raw"]
        if any(step["text_raw"] not in source_text for step in item["reference_steps"]):
            errors.append(f"UNGROUNDED_STEP:{item['question_id']}")
    numbers = [item["source_number"] for item in items]
    flags = Counter(flag for item in items for flag in item["review_flags"])
    return {
        "schema_version": "pdf-pilot-report/v1", "page_count": len(pages),
        "candidate_count": len(items), "source_number_min": min(numbers, default=None),
        "source_number_max": max(numbers, default=None),
        "duplicate_source_numbers": [key for key, count in Counter(numbers).items() if count > 1],
        "answers_found": sum(bool(item["answer"]["text_raw"]) for item in items),
        "solutions_found": sum(bool(item["solution"]["text_raw"].strip()) for item in items),
        "reference_step_candidate_count": sum(len(item["reference_steps"]) for item in items),
        "cross_page_items": [item["source_number"] for item in items
                             if len({s["page_number"] for s in item["source_regions"]}) > 1],
        "review_flag_counts": dict(flags), "structural_errors": errors,
        "structural_status": "PASS" if not errors and items else "NEEDS_REVIEW",
        "academic_status": "NOT_VERIFIED", "grading_ready_count": 0,
    }
