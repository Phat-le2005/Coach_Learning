"""Run a second formula recognizer only on regions flagged by the first pass."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import time

from .quality import compare_transcriptions, nearby_native_text
from .storage import configure_storage, file_hash, read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--max-regions", type=int, default=80)
    args = parser.parse_args()
    configure_storage(args.runtime)
    manifest = read_json(args.pilot / "manifest.json")
    quality = read_json(args.pilot / "enrichment-report.json")
    all_blocks = {}
    for directory in ("paddle-vl", "fast-hybrid"):
        for path in (args.pilot / directory).glob("page-*.blocks.json"):
            result = read_json(path)
            for block in result["blocks"]:
                if block["block_type"] in ("inline_formula", "display_formula", "formula"):
                    all_blocks[(result["page_number"], block["block_id"])] = block
    selected = []
    seen = set()
    for finding in quality["ocr_quality_findings"]:
        key = (finding["page_number"], finding["block_id"])
        if key in all_blocks and key not in seen:
            seen.add(key)
            selected.append((key, all_blocks[key], finding["flags"]))
    if len(selected) > args.max_regions:
        raise SystemExit(f"{len(selected)} regions exceed the explicit limit {args.max_regions}; split the job")
    import pdfplumber
    from paddleocr import FormulaRecognition

    output = args.pilot / "formula-fallback"
    output.mkdir(exist_ok=True)
    model = FormulaRecognition(model_name="PP-FormulaNet_plus-M", device="cpu", cpu_threads=3, enable_mkldnn=False)
    model_hash = file_hash(args.runtime / "paddlex" / "official_models" / "PP-FormulaNet_plus-M" / "inference.pdiparams")
    pages = defaultdict(list)
    observations = []
    started = time.perf_counter()
    with pdfplumber.open(manifest["source_path"]) as pdf:
        for (number, block_id), block, before_flags in selected:
            native = read_json(args.pilot / "pages" / f"page-{number:03}.json")
            x0, y0, x1, y1 = block["bbox"]
            bbox = [max(0, x0 - 2), max(0, y0 - 2), min(native["width"], x1 + 2), min(native["height"], y1 + 2)]
            image = output / f"{block_id}.png"
            pdf.pages[number - 1].crop(tuple(bbox)).to_image(resolution=240).save(image)
            tick = time.perf_counter()
            result = list(model.predict(str(image), batch_size=1))[0].json
            text = result.get("res", result).get("rec_formula", "")
            pages[number].append({**block, "block_id": block_id + "-fallback-M", "text_raw": text})
            after = compare_transcriptions(nearby_native_text(native, block["bbox"]), text)
            observations.append({"page_number": number, "source_block_id": block_id,
                                 "before_flags": before_flags, "after_flags": after["flags"],
                                 "latex_candidate": text, "seconds": round(time.perf_counter() - tick, 3)})
            write_json(output / f"page-{number:03}.blocks.json", {
                "page_number": number, "source_sha256": manifest["source_sha256"],
                "parser_id": "PP-FormulaNet_plus-M", "model_weights_sha256": model_hash,
                "status": "INFERRED_NOT_REVIEWED", "blocks": pages[number]})
            write_json(output / "report.json", {"status": "RUNNING", "regions": observations})
            print(f"Fallback {block_id}: {before_flags} -> {after['flags']}", flush=True)
    report = {"status": "INFERRED_NOT_REVIEWED", "source_sha256": manifest["source_sha256"],
              "model_weights_sha256": model_hash, "regions": observations,
              "elapsed_inference_seconds": round(time.perf_counter() - started, 3),
              "regions_without_detected_discrepancy_after_fallback": sum(not r["after_flags"] for r in observations),
              "note": "Clearing a discrepancy rule is not source transcription approval or academic validation."}
    write_json(output / "report.json", report)


if __name__ == "__main__":
    main()
