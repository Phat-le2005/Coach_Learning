"""Attach OCR evidence by source geometry without overwriting native/source data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .review import build_review
from .quality import compare_transcriptions, nearby_native_text
from .storage import read_json, write_json, write_jsonl
from .validate import validate_candidates


def attach_evidence(items: list[dict], experiments: list[dict], pages: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    ambiguous = []
    findings = []
    page_lookup = {page["page_number"]: page for page in pages or []}
    for result in experiments:
        number = result["page_number"]
        for block in result["blocks"]:
            bbox = block.get("bbox")
            if not bbox or block["block_type"] in ("header", "footer", "number"):
                continue
            x0, y0, x1, y1 = bbox
            if x1 <= x0 or y1 <= y0:
                ambiguous.append({"page_number": number, "block_id": block["block_id"], "reason": "INVALID_OCR_BBOX"})
                continue
            owners = []
            for item in items:
                for region in item["source_regions"]:
                    if region["page_number"] != number:
                        continue
                    rx0, ry0, rx1, ry1 = region["bbox"]
                    overlap = max(0, min(x1, rx1) - max(x0, rx0)) * max(0, min(y1, ry1) - max(y0, ry0))
                    if overlap / ((x1 - x0) * (y1 - y0)) >= 0.9:
                        owners.append(item)
            if len(owners) == 1:
                owners[0].setdefault("ocr_evidence", []).append({
                    "page_number": number, "parser_id": result.get("parser_id", "PaddleOCR-VL-1.6"),
                    "status": "INFERRED_NOT_REVIEWED", **block,
                })
                if number in page_lookup:
                    native = nearby_native_text(page_lookup[number], bbox)
                    finding = compare_transcriptions(native, block["text_raw"])
                    if finding["flags"]:
                        owners[0]["review_flags"] = sorted(set(owners[0]["review_flags"] + finding["flags"]))
                        findings.append({"question_id": owners[0]["question_id"], "page_number": number,
                                         "block_id": block["block_id"], **finding})
            else:
                ambiguous.append({"page_number": number, "block_id": block["block_id"],
                                  "reason": "NO_UNAMBIGUOUS_ITEM_OWNER"})
    return ambiguous, findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    args = parser.parse_args()
    manifest = read_json(args.pilot / "manifest.json")
    experiment_path = args.pilot / "paddle-vl" / "experiment.json"
    if experiment_path.exists():
        experiment = read_json(experiment_path)
        if experiment["source_sha256"] != manifest["source_sha256"]:
            raise SystemExit("OCR and native source hashes differ")
    items = [json.loads(line) for line in (args.pilot / "questions.candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    pages = [read_json(path) for path in sorted((args.pilot / "pages").glob("*.json"))]
    results = [read_json(path) for path in sorted((args.pilot / "paddle-vl").glob("page-*.blocks.json"))]
    fast_results = [read_json(path) for path in sorted((args.pilot / "fast-hybrid").glob("page-*.blocks.json"))]
    if any(r["source_sha256"] != manifest["source_sha256"] for r in fast_results):
        raise SystemExit("Hybrid and native source hashes differ")
    results.extend(fast_results)
    fallback_results = [read_json(path) for path in sorted((args.pilot / "formula-fallback").glob("page-*.blocks.json"))]
    if any(r["source_sha256"] != manifest["source_sha256"] for r in fallback_results):
        raise SystemExit("Fallback and native source hashes differ")
    results.extend(fallback_results)
    control_path = args.pilot / "formula-probe" / "PP-FormulaNet_plus-M" / "result.json"
    if control_path.exists():
        control = read_json(control_path)
        if control["source_sha256"] != manifest["source_sha256"]:
            raise SystemExit("Control experiment source hash differs")
        for region in control["regions"]:
            results.append({"page_number": region["page_number"], "parser_id": "PP-FormulaNet_plus-M",
                            "blocks": [{"block_id": region["id"] + "-control-M", "block_type": "formula",
                                        "text_raw": region["latex_candidate"], "bbox": region["bbox"], "reading_order": None}]})
    if not results:
        raise SystemExit("No OCR checkpoints found; run hybrid or ocr first")
    ambiguous, findings = attach_evidence(items, results, pages)
    report = validate_candidates(items, pages, args.pilot)
    report["ocr_pages"] = sorted({r["page_number"] for r in results})
    report["ocr_enriched_item_count"] = sum(bool(i.get("ocr_evidence")) for i in items)
    report["ambiguous_ocr_block_count"] = len(ambiguous)
    report["ocr_quality_findings"] = findings
    report["ocr_quality_status"] = "REVIEW_REQUIRED" if findings else "NOT_YET_VALIDATED"
    write_jsonl(args.pilot / "questions.enriched.candidates.jsonl", items)
    write_jsonl(args.pilot / "paddle-vl" / "unassigned-blocks.jsonl", ambiguous)
    write_json(args.pilot / "enrichment-report.json", report)
    build_review(items, report, args.pilot)
    print(json.dumps({k: report[k] for k in ("ocr_pages", "ocr_enriched_item_count", "ambiguous_ocr_block_count", "structural_status")}, ensure_ascii=False))
    if report["structural_errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
