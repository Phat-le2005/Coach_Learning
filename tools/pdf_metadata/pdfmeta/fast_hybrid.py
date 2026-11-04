"""Native text + layout detection + cropped formula OCR, checkpointed per page."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import time

from .storage import configure_storage, file_hash, inference_versions, read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--pages", default="all")
    args = parser.parse_args()
    configure_storage(args.runtime)
    manifest = read_json(args.pilot / "manifest.json")
    numbers = (list(range(1, manifest["page_count"] + 1)) if args.pages == "all"
               else list(dict.fromkeys(int(n) for n in args.pages.split(","))))
    if any(n < 1 or n > manifest["page_count"] for n in numbers):
        parser.error("Requested page outside source document")
    output = args.pilot / "fast-hybrid"
    output.mkdir(exist_ok=True)
    started = time.perf_counter()
    import pdfplumber
    import psutil
    from PIL import Image
    from paddleocr import FormulaRecognition, LayoutDetection

    detector = LayoutDetection(model_name="PP-DocLayoutV3", device="cpu", cpu_threads=3, enable_mkldnn=False)
    recognizer = FormulaRecognition(model_name="PP-FormulaNet_plus-S", device="cpu", cpu_threads=3, enable_mkldnn=False)
    model_root = args.runtime / "paddlex" / "official_models"
    model_files = [model_root / "PP-DocLayoutV3" / "inference.pdiparams",
                   model_root / "PP-FormulaNet_plus-S" / "inference.pdiparams"]
    model_hashes = {str(p.relative_to(model_root)): file_hash(p) for p in model_files}
    report = {"schema_version": "fast-hybrid-experiment/v1", "status": "RUNNING",
              "source_sha256": manifest["source_sha256"], "device": "cpu", "threads": 3,
              "packages": inference_versions(),
              "model_weights_sha256": model_hashes,
              "initialization_seconds": round(time.perf_counter() - started, 3),
              "pages": [], "academic_status": "NOT_VERIFIED"}
    write_json(output / "experiment.json", report)
    try:
        with pdfplumber.open(manifest["source_path"]) as pdf:
            for number in numbers:
                before = time.perf_counter()
                native = read_json(args.pilot / "pages" / f"page-{number:03}.json")
                image_path = args.pilot / native["image_path"]
                cache_key = {"image_sha256": file_hash(image_path), "model_weights_sha256": model_hashes,
                             "packages": report["packages"], "formula_dpi": 240, "threshold": 0.4,
                             "adapter_version": "fast-hybrid/v1"}
                target = output / f"page-{number:03}.blocks.json"
                cached = read_json(target) if target.exists() else None
                if cached and cached.get("cache_key") == cache_key:
                    report["pages"].append({k: v for k, v in cached.items() if k not in ("blocks", "layout_boxes")})
                    print(f"Hybrid page {number}: reused checkpoint", flush=True)
                    continue
                with Image.open(image_path) as image:
                    width, height = image.size
                layout = list(detector.predict(str(image_path), batch_size=1, threshold=0.4))[0].json
                layout = layout.get("res", layout)
                raw_boxes = layout.get("boxes", [])
                counts = Counter(box["label"] for box in raw_boxes)
                formula_boxes = sorted([b for b in raw_boxes if b["label"] in ("display_formula", "inline_formula", "formula")],
                                       key=lambda box: (box["coordinate"][1], box["coordinate"][0]))
                blocks = []
                for index, box in enumerate(formula_boxes):
                    x0, y0, x1, y1 = box["coordinate"]
                    bbox = [max(0, x0 * native["width"] / width - 2),
                            max(0, y0 * native["height"] / height - 2),
                            min(native["width"], x1 * native["width"] / width + 2),
                            min(native["height"], y1 * native["height"] / height + 2)]
                    if bbox[2] - bbox[0] < 2 or bbox[3] - bbox[1] < 2:
                        continue
                    crop = output / f"p{number:03}-formula-{index:03}.png"
                    pdf.pages[number - 1].crop(tuple(bbox)).to_image(resolution=240).save(crop)
                    formula = list(recognizer.predict(str(crop), batch_size=1))[0].json
                    formula = formula.get("res", formula)
                    blocks.append({"block_id": f"p{number:03}-formula-{index:03}",
                                   "block_type": box["label"], "text_raw": formula.get("rec_formula", ""),
                                   "bbox": [round(value, 3) for value in bbox], "reading_order": index})
                result = {"page_number": number, "source_sha256": manifest["source_sha256"],
                          "parser_id": "PP-FormulaNet_plus-S", "status": "INFERRED_NOT_REVIEWED",
                          "cache_key": cache_key, "layout_label_counts": dict(counts),
                          "layout_boxes": raw_boxes, "blocks": blocks,
                          "seconds": round(time.perf_counter() - before, 3),
                          "process_rss_mb_after_page": round(psutil.Process().memory_info().rss / 1024**2, 1)}
                write_json(target, result)
                report["pages"].append({k: v for k, v in result.items() if k not in ("blocks", "layout_boxes")})
                write_json(output / "experiment.json", report)
                print(f"Hybrid page {number}: {len(blocks)} formula crops, {result['seconds']}s", flush=True)
        report["status"] = "INFERRED_NOT_REVIEWED"
    except Exception as error:
        report["status"] = "FAILED"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        write_json(output / "experiment.json", report)


if __name__ == "__main__":
    main()
