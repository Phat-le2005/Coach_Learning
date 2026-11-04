"""Bounded local PaddleOCR-VL experiment; preserves native candidates unchanged."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import threading
import time
import traceback

from .storage import configure_storage, file_hash, inference_versions, read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--pages", default="1")
    parser.add_argument("--threads", type=int, default=3)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--device", default="cpu", help="cpu locally, or gpu:0 in a compatible GPU environment")
    args = parser.parse_args()
    storage = configure_storage(args.runtime)
    output = args.pilot / "paddle-vl"
    output.mkdir(exist_ok=True)
    manifest = read_json(args.pilot / "manifest.json")
    page_numbers = (list(range(1, manifest["page_count"] + 1)) if args.pages == "all"
                    else list(dict.fromkeys(int(x) for x in args.pages.split(","))))
    for number in page_numbers:
        if not 1 <= number <= manifest["page_count"]:
            parser.error(f"Page {number} is outside the source document")
    report = {
        "schema_version": "parser-experiment/v1", "status": "INITIALIZING",
        "pipeline": "PaddleOCR-VL-1.6", "device": args.device, "threads": args.threads,
        "batch_size": 1, "max_new_tokens_per_block": args.max_new_tokens,
        "source_sha256": manifest["source_sha256"], "python": platform.python_version(),
        "packages": inference_versions(),
        "storage": storage, "pages": [], "academic_status": "NOT_VERIFIED",
    }
    write_json(output / "experiment.json", report)
    started = time.perf_counter()
    try:
        import psutil
        from paddleocr import PaddleOCRVL
        from paddlex.inference import load_pipeline_config

        config = load_pipeline_config("PaddleOCR-VL-1.6")
        config["batch_size"] = 1
        config["use_queues"] = False
        config["SubModules"]["LayoutDetection"]["batch_size"] = 1
        config["SubModules"]["VLRecognition"]["batch_size"] = 1
        pipeline = PaddleOCRVL(
            pipeline_version="v1.6", paddlex_config=config, device=args.device,
            cpu_threads=args.threads, enable_mkldnn=False,
            use_doc_orientation_classify=False, use_doc_unwarping=False,
            use_queues=False,
        )
        report["initialization_seconds"] = round(time.perf_counter() - started, 3)
        pipeline.export_paddlex_config_to_yaml(str(output / "resolved-config.yaml"))
        report["config_sha256"] = file_hash(output / "resolved-config.yaml")
        weight_path = Path(storage["PADDLE_PDX_CACHE_HOME"]) / "official_models" / "PaddleOCR-VL-1.6" / "model.safetensors"
        report["model_weights_sha256"] = file_hash(weight_path) if weight_path.is_file() else None
        report["status"] = "INFERENCING"
        write_json(output / "experiment.json", report)
        for number in page_numbers:
            page = read_json(args.pilot / "pages" / f"page-{number:03}.json")
            image = args.pilot / page["image_path"]
            image_hash = file_hash(image)
            cached_path = output / f"page-{number:03}.blocks.json"
            cached = read_json(cached_path) if cached_path.exists() else None
            cache_key = {"image_sha256": image_hash, "config_sha256": report["config_sha256"],
                         "model_weights_sha256": report["model_weights_sha256"],
                         "packages": report["packages"], "device": args.device,
                         "max_new_tokens": args.max_new_tokens}
            if cached and cached.get("cache_key") == cache_key:
                report["pages"].append({key: value for key, value in cached.items() if key != "blocks"})
                print(f"Paddle page {number}: reused matching checkpoint", flush=True)
                continue
            raw_dir = output / f"page-{number:03}"
            raw_dir.mkdir(exist_ok=True)
            page_started = time.perf_counter()
            peak = [psutil.Process().memory_info().rss]
            stop = threading.Event()
            def sample() -> None:
                while not stop.wait(0.25):
                    peak[0] = max(peak[0], psutil.Process().memory_info().rss)
            sampler = threading.Thread(target=sample, daemon=True)
            sampler.start()
            try:
                results = list(pipeline.predict(str(image), max_new_tokens=args.max_new_tokens))
                normalized = []
                for result in results:
                    result.save_to_json(str(raw_dir))
                    result.save_to_markdown(str(raw_dir))
                    raw = result.json
                    if isinstance(raw, str):
                        raw = json.loads(raw)
                    raw = raw.get("res", raw)
                    for block in raw.get("parsing_res_list", []):
                        bbox = block.get("block_bbox", [])
                        from PIL import Image
                        with Image.open(image) as im:
                            width, height = im.size
                        normalized.append({
                            "block_id": f"p{number:03}-vl-{len(normalized):04}",
                            "block_type": block.get("block_label"),
                            "text_raw": block.get("block_content", ""),
                            "bbox": [round(bbox[0] * page["width"] / width, 3),
                                     round(bbox[1] * page["height"] / height, 3),
                                     round(bbox[2] * page["width"] / width, 3),
                                     round(bbox[3] * page["height"] / height, 3)] if len(bbox) == 4 else None,
                            "reading_order": block.get("block_order"),
                        })
                entry = {"page_number": number, "status": "INFERRED_NOT_REVIEWED",
                         "cache_key": cache_key,
                         "image_sha256": image_hash, "seconds": round(time.perf_counter() - page_started, 3),
                         "peak_process_rss_mb": round(peak[0] / 1024**2, 1),
                         "blocks": normalized}
                write_json(output / f"page-{number:03}.blocks.json", entry)
                report["pages"].append({key: value for key, value in entry.items() if key != "blocks"})
                write_json(output / "experiment.json", report)
                print(f"Paddle page {number}: {entry['seconds']}s, {len(normalized)} blocks", flush=True)
            finally:
                stop.set()
                sampler.join()
        pipeline.close()
        report["status"] = "INFERRED_NOT_REVIEWED"
    except Exception as error:
        report["status"] = "FAILED"
        report["error"] = f"{type(error).__name__}: {error}"
        (output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        write_json(output / "experiment.json", report)


if __name__ == "__main__":
    main()
