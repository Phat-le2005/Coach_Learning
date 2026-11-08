"""Prepare review-only metadata for the direct OCR grouped-statistics draft.

This does not rewrite the OCR source, publish curriculum, or import questions.
Image-backed table cells remain untranscribed until verified against the PDF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdfmeta.direct_pdf_regions import detect_tables


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "backend/data/ocr-direct-grouped_statistics"
CURRICULUM = ROOT / "backend/data/curriculum/math/grade12/gdpt2018"
TAXONOMY = CURRICULUM / "staging/grouped_data_dispersion_v0_1"
IMAGE_LINK = re.compile(r"!\[[^]]*\]\([^)]*\)")
SUBPART = re.compile(r"(?:^|\s)[a-d]\)\s", re.IGNORECASE)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def plain(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
    return "".join(c for c in value if unicodedata.category(c) != "Mn")


def prompt_text(markdown: str) -> str:
    # Headings copied from the PDF are unreliable; use the question body only.
    return plain(IMAGE_LINK.sub(" ", markdown))


def substantive_solution(markdown: str) -> bool:
    body = re.sub(r"(?is)^\s*lời\s+giải\s*[:.]?\s*", "", markdown).strip()
    return bool(body)


def measures(text: str) -> list[str]:
    found = []
    if re.search(r"khoang bien thien|\bR\b", text, re.I):
        found.append("range")
    if re.search(r"khoang tu phan vi|\bIQR\b", text, re.I):
        found.append("iqr")
    if "phuong sai" in text:
        found.append("variance")
    if "do lech chuan" in text:
        found.append("sd")
    return found


def classify(markdown: str, solution: str, problem_types: dict) -> dict:
    text = prompt_text(markdown)
    observed = measures(text)
    inference_source = "QUESTION_EXPLICIT"
    if not observed and "hieu so" in text and "khong vuot qua" in text:
        observed = ["range"]
        inference_source = "QUESTION_SEMANTIC_RANGE_BOUND"
    if not observed and "q_1" in text and "q_3" in text and "50%" in text:
        observed = ["iqr"]
        inference_source = "QUESTION_IMPLIED_MIDDLE_50_PERCENT"
    if not observed and "cac so dac trung do muc do phan tan" in text:
        observed = ["range", "iqr", "variance", "sd"]
        inference_source = "QUESTION_BROAD_DISPERSION_REQUEST"
    if not observed and ("phan tan" in text or "bien doi nhieu hon" in text):
        observed = measures(prompt_text(solution))
        inference_source = "UNVERIFIED_SOLUTION_DISAMBIGUATION" if observed else "NO_MEASURE_FOUND"
    compare = any(word in text for word in (
        "so sanh", "on dinh", "dong deu", "bien dong", "deu hon",
        "phan tan hon", "bien doi nhieu hon",
    ))
    explain = any(word in text for word in ("giai thich", "nhan xet", "dung hay sai", "ket luan", "y kien"))
    multipart = len(SUBPART.findall(text)) >= 2
    has_answer_blank = "tra loi:" in text or "tra loi :" in text
    question_type = "SHORT_ANSWER" if has_answer_blank and not multipart and not compare and not explain else "OPEN_RESPONSE"

    codes = []
    if observed and "dung hay sai" in text and "giai thich" in text:
        codes.append("CONCLUDE_FROM_GROUPED_DISPERSION")
    if len(observed) >= 2 and {"range", "iqr"} & set(observed) and {"variance", "sd"} & set(observed):
        codes.append("MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS")
    elif len(observed) >= 2 and not compare:
        # Two calculations belong to a multi-step task; keep the individual skills too.
        codes.append("MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS")
    if compare:
        if "on dinh" in text or "dong deu" in text or "deu hon" in text:
            codes.append("IDENTIFY_MORE_STABLE_GROUPED_DATA")
        elif "iqr" in observed:
            codes.append("COMPARE_GROUPED_IQR")
        elif "variance" in observed or "sd" in observed:
            codes.append("COMPARE_GROUPED_VARIANCE_SD")
        elif "range" in observed:
            codes.append("COMPARE_GROUPED_RANGE")
    individual = {
        "range": "CALCULATE_GROUPED_RANGE",
        "iqr": "CALCULATE_GROUPED_IQR",
        "variance": "CALCULATE_GROUPED_VARIANCE",
        "sd": "CALCULATE_GROUPED_STANDARD_DEVIATION",
    }
    codes.extend(individual[measure] for measure in observed)
    codes = list(dict.fromkeys(codes))
    if not codes and explain and "do phan tan" in text:
        codes = ["INTERPRET_GROUPED_DISPERSION_MEASURE"]
    if not codes and "trung binh" in text:
        scope = "OUT_OF_SCOPE_OR_PREREQUISITE"
    elif not codes:
        scope = "MANUAL_SCOPE_REVIEW"
    else:
        scope = "GROUPED_DISPERSION_CANDIDATE"
    for code in codes:
        if code not in problem_types:
            raise ValueError(f"Unknown problem type: {code}")
    return {
        "question_type_candidate": question_type,
        "type_evidence": "ANSWER_BLANK_SINGLE_RESULT" if question_type == "SHORT_ANSWER" else "EXPLANATION_COMPARISON_OR_MULTIPART",
        "observed_measures": observed,
        "measure_inference_source": inference_source,
        "scope_status": scope,
        "classification_confidence": "LOW" if not codes or len(codes) > 2 or inference_source != "QUESTION_EXPLICIT" else "MEDIUM",
        "problem_type_codes": codes,
        "primary_problem_type_code": codes[0] if codes else None,
        "topic_codes": list(dict.fromkeys(problem_types[code]["topic_code"] for code in codes)),
        "difficulty_candidate": max((problem_types[code]["default_difficulty"] for code in codes), default=None),
        "review_flags": (["MULTIPLE_SKILLS_MANUAL_PRIMARY_REVIEW"] if len(codes) > 1 else [])
        + (["INFERRED_MEASURE_REVIEW"] if inference_source != "QUESTION_EXPLICIT" else [])
        + (["SCOPE_REVIEW"] if scope != "GROUPED_DISPERSION_CANDIDATE" else []),
    }


def aggregate_concepts(codes: list[str], links: dict[str, list[dict]]) -> list[dict]:
    if not codes:
        return []
    weights = defaultdict(float)
    for code in codes:
        for link in links[code]:
            weights[link["concept_code"]] += link["weight"] / len(codes)
    total = sum(weights.values())
    ordered = sorted(weights.items(), key=lambda item: -item[1])
    rounded = [round(weight / total, 6) for _, weight in ordered[:-1]]
    rounded.append(round(1.0 - sum(rounded), 6))
    return [{"code": code, "weight_candidate": weight}
            for (code, _), weight in zip(ordered, rounded)]


def table_descriptor(asset: dict, data: Path) -> dict:
    relative = Path(asset["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe asset path: {relative}")
    path = data / relative
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_hash != asset["sha256"]:
        raise ValueError(f"Asset hash mismatch: {relative}")
    with Image.open(path) as image:
        width, height = image.size
        grids = detect_tables(image)
    # Tiny decorative rules can look like a 2x2 grid to the line detector.
    valid = (height >= 80 and len(grids) == 1
             and all(cell["bbox"][2] - cell["bbox"][0] >= 20
                     and cell["bbox"][3] - cell["bbox"][1] >= 20
                     for cell in grids[0]["cells"]))
    suspected_decoration = height <= 40 and width >= height * 20
    return {
        "asset_id": asset["id"], "source_image": relative.as_posix(),
        "source_sha256": actual_hash, "source_page": asset["page_number"],
        "source_bbox_pdf_points": asset["bbox"], "image_size_px": [width, height],
        "structure_status": (
            "GRID_GEOMETRY_CANDIDATE" if valid else
            "SUSPECTED_NON_TABLE_DECORATION" if suspected_decoration else
            "IMAGE_ONLY_REVIEW_REQUIRED"
        ),
        "cell_values_status": "UNTRANSCRIBED",
        "rows": grids[0]["rows"] if valid else None,
        "columns": grids[0]["columns"] if valid else None,
        "cells": [{"row": cell["row"], "column": cell["column"],
                   "bbox_image_px": cell["bbox"], "text": None, "value": None}
                  for cell in grids[0]["cells"]] if valid else [],
        "review_required": True,
    }


def build(data: Path) -> tuple[list[dict], dict]:
    manifest = read_json(CURRICULUM / "manifest.json")
    taxonomy = read_json(TAXONOMY / "taxonomy_metadata.json")
    source_summary = read_json(data / "summary.json")
    if taxonomy["status"] != "REVIEW_CANDIDATE":
        raise ValueError("Taxonomy review status changed; recheck promotion policy")
    problem_types = {item["code"]: item for item in read_json(TAXONOMY / "problem_types.json")}
    links = defaultdict(list)
    for link in read_json(TAXONOMY / "problem_type_concepts.json"):
        links[link["problem_type_code"]].append(link)
    known_concepts = {item["code"] for item in read_json(TAXONOMY / "concepts.json")}
    for code, rows in links.items():
        if code not in problem_types or any(row["concept_code"] not in known_concepts for row in rows):
            raise ValueError(f"Invalid taxonomy links for {code}")
    if set(problem_types) != set(links):
        raise ValueError("Every candidate problem type needs concept links")
    source_bytes = (data / "content.draft.jsonl").read_bytes()
    records = [json.loads(line) for line in source_bytes.decode("utf-8").splitlines() if line.strip()]
    seen = set()
    output = []
    skipped = []
    status_counts = Counter()
    table_counts = Counter()
    for record in records:
        qid = record["question_id"]
        if record["source"]["sha256"] != source_summary["input_sha256"]:
            raise ValueError(f"Source PDF hash mismatch for {qid}")
        if qid in seen:
            raise ValueError(f"Duplicate question ID: {qid}")
        seen.add(qid)
        question = record["question"]["markdown"].strip()
        if re.match(r"^BÀI\s+[12]\s*\n", question, re.IGNORECASE) and not record["solution"]["markdown"].strip():
            skipped.append({"question_id": qid, "collection_number": record["collection_number"], "reason": "SECTION_HEADING_NOT_QUESTION"})
            continue
        candidate = classify(question, record["solution"]["markdown"], problem_types)
        codes = candidate["problem_type_codes"]
        candidate["concepts"] = aggregate_concepts(codes, links)
        candidate["difficulty_source"] = "REVIEW_CANDIDATE_TAXONOMY_DEFAULT"
        candidate["exam_weight_candidate"] = None
        candidate["exam_weight_status"] = "NEEDS_ASSESSMENT_BLUEPRINT"
        solution_present = substantive_solution(record["solution"]["markdown"])
        answer_present = bool(record["answer"]["markdown"].strip())
        candidate["answer_status"] = (
            "OCR_ANSWER_UNVERIFIED" if answer_present else
            "SOLUTION_ONLY_ANSWER_REVIEW_REQUIRED" if solution_present else
            "NO_SUBSTANTIVE_SOLUTION_OR_ANSWER"
        )
        candidate["source_answer_text"] = record["answer"]["markdown"].strip() or None
        candidate["source_solution_present"] = solution_present
        candidate["solution_status"] = "OCR_SUBSTANTIVE_UNVERIFIED" if solution_present else "HEADING_ONLY_OR_EMPTY"
        candidate["source_academic_review"] = record["academic_review"]
        candidate["publishable"] = False
        candidate["import_ready"] = False
        candidate["table_assets"] = [table_descriptor(asset, data) for asset in record["visual_assets"] if asset["kind"] == "TABLE"]
        candidate["graph_assets"] = [asset["path"] for asset in record["visual_assets"] if asset["kind"] == "GRAPH"]
        candidate["review_flags"].append("OCR_TEXT_AND_MATH_UNVERIFIED")
        if candidate["table_assets"]:
            candidate["review_flags"].append("TABLE_VALUES_UNTRANSCRIBED")
        if candidate["question_type_candidate"] == "SHORT_ANSWER":
            candidate["review_flags"].append("CORRECT_ANSWER_REQUIRED_BEFORE_IMPORT")
        for table in candidate["table_assets"]:
            table_counts[table["structure_status"]] += 1
        status_counts[candidate["scope_status"]] += 1
        output.append({
            "question_id": qid,
            "collection_number": record["collection_number"],
            "source_pdf_sha256": record["source"]["sha256"],
            "source_pages": sorted({span["page_number"] for span in record["question"]["source_spans"]}),
            "subject_code": manifest["subject_code"], "grade_level": manifest["grade_level"],
            "curriculum_code": manifest["curriculum_code"],
            "curriculum_version_code": manifest["curriculum_version_code"],
            "chapter_code_candidate": taxonomy["chapter_code"],
            "taxonomy_code": taxonomy["taxonomy_code"],
            "taxonomy_status": taxonomy["status"],
            "metadata": candidate,
        })
    report = {
        "status": "REVIEW_ONLY_NOT_IMPORT_READY",
        "ocr_input_jsonl_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "ocr_source_status": source_summary["status"],
        "ocr_failed_regions": source_summary["failed_regions"],
        "ocr_mathematical_accuracy_established": source_summary["mathematical_accuracy_established"],
        "source_pdf_available_locally": Path(source_summary["input_pdf"]).is_file(),
        "source_record_count": len(records), "question_candidate_count": len(output),
        "excluded_headings": skipped,
        "scope_counts": dict(status_counts),
        "question_type_counts": dict(Counter(row["metadata"]["question_type_candidate"] for row in output)),
        "measure_inference_counts": dict(Counter(row["metadata"]["measure_inference_source"] for row in output)),
        "table_structure_counts": dict(table_counts),
        "question_table_asset_count": sum(len(row["metadata"]["table_assets"]) for row in output),
        "graph_asset_count": sum(len(row["metadata"]["graph_assets"]) for row in output),
        "separate_ocr_answer_count": sum(row["metadata"]["source_answer_text"] is not None for row in output),
        "substantive_ocr_solution_count": sum(row["metadata"]["source_solution_present"] for row in output),
        "heading_only_or_empty_solution_count": sum(not row["metadata"]["source_solution_present"] for row in output),
        "exam_weight_policy": "Unset; source PDF has no exam blueprint and importer requires a reviewed value.",
        "table_policy": "Grid coordinates only when detected; no inferred cell text or numbers.",
        "promotion_policy": taxonomy["merge_policy"],
        "unclassified_question_ids": [row["question_id"] for row in output if row["metadata"]["scope_status"] != "GROUPED_DISPERSION_CANDIDATE"],
    }
    assigned = {asset["asset_id"] for row in output for asset in row["metadata"]["table_assets"]}
    assigned.update(asset["id"] for record in records for asset in record["visual_assets"] if asset["kind"] == "GRAPH")
    unassigned = [asset for asset in read_json(data / "visual-assets.json") if asset["id"] not in assigned]
    report["unassigned_visual_assets"] = []
    for asset in unassigned:
        item = {"asset_id": asset["id"], "kind": asset["kind"], "path": asset["path"], "page": asset["page_number"]}
        if asset["kind"] == "TABLE":
            item["table_descriptor"] = table_descriptor(asset, data)
            table_counts[item["table_descriptor"]["structure_status"]] += 1
        report["unassigned_visual_assets"].append(item)
    report["table_structure_counts"] = dict(table_counts)
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()
    data = args.data.resolve()
    rows, report = build(data)
    (data / "metadata.review.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    (data / "metadata.review.report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
