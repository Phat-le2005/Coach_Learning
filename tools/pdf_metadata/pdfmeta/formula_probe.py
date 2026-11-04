"""Small CPU formula recognizer experiment on explicitly sourced regions."""
from __future__ import annotations

import argparse
from pathlib import Path
import time

from .storage import configure_storage, file_hash, read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--model", choices=["PP-FormulaNet_plus-S", "PP-FormulaNet_plus-M"], default="PP-FormulaNet_plus-S")
    args = parser.parse_args()
    configure_storage(args.runtime)
    manifest = read_json(args.pilot / "manifest.json")
    regions = []
    # Source-specific control case belongs to the fixture, never generic parsing.
    fixture = read_json(Path(__file__).parents[1] / "fixtures" / "pilot-kntt-v1.json")
    if manifest["source_sha256"] != fixture["source_sha256"]:
        raise SystemExit("This experiment's control crop belongs to a different PDF")
    regions.extend(fixture["formula_control_regions"])
    for path in sorted((args.pilot / "paddle-vl").glob("page-*.blocks.json")):
        result = read_json(path)
        regions.extend({"id": block["block_id"], "page_number": result["page_number"], "bbox": block["bbox"]}
                       for block in result["blocks"] if block["block_type"] == "display_formula")
    import pdfplumber
    from paddleocr import FormulaRecognition

    output = args.pilot / "formula-probe"
    if args.model != "PP-FormulaNet_plus-S":
        output = output / args.model
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    model = FormulaRecognition(model_name=args.model, device="cpu", cpu_threads=3, enable_mkldnn=False)
    initialization_seconds = time.perf_counter() - started
    records = []
    with pdfplumber.open(manifest["source_path"]) as document:
        for region in regions:
            image = output / f"{region['id']}.png"
            page = document.pages[region["page_number"] - 1]
            x0, y0, x1, y1 = region["bbox"]
            bounds = (max(0, x0 - 2), max(0, y0 - 2), min(page.width, x1 + 2), min(page.height, y1 + 2))
            page.crop(bounds).to_image(resolution=240).save(image)
            before = time.perf_counter()
            results = list(model.predict(str(image), batch_size=1))
            value = results[0].json
            value = value.get("res", value)
            text = value.get("rec_formula", value.get("rec_text", ""))
            records.append({**region, "crop_path": str(image.relative_to(args.pilot)).replace("\\", "/"),
                            "image_sha256": file_hash(image), "model": args.model,
                            "latex_candidate": text, "seconds": round(time.perf_counter() - before, 3),
                            "status": "INFERRED_NOT_REVIEWED"})
            write_json(output / "result.json", {"source_sha256": manifest["source_sha256"],
                       "initialization_seconds": round(initialization_seconds, 3), "regions": records})
            print(f"Formula {region['id']}: {text}", flush=True)


if __name__ == "__main__":
    main()
