"""Measure real RapidLaTeXOCR ONNX inference on consented formula images.

This script never substitutes a mock predictor and never downloads checkpoints.
Run from backend/ with an isolated environment and a local, gitignored dataset.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.util import find_spec
import json
import platform
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.exceptions import ApplicationError
from app.math_ocr.local_rapid_adapter import inspect_cpu_model_files, load_cpu_model


@dataclass(frozen=True)
class FormulaSample:
    sample_id: str
    group: str
    image_path: Path
    reference_latex: str
    source: str


def _safe_image_path(manifest_dir: Path, name: str) -> Path:
    if not name or Path(name).is_absolute():
        raise ValueError("Image paths must be relative to the manifest.")
    candidate = (manifest_dir / name).resolve()
    if not candidate.is_relative_to(manifest_dir.resolve()) or candidate.suffix.lower() != ".png":
        raise ValueError("Image path must name a PNG under the manifest directory.")
    if not candidate.is_file() or candidate.stat().st_size == 0:
        raise ValueError(f"Missing or empty image: {name}")
    return candidate


def load_manifest(path: Path) -> list[FormulaSample]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("samples"), list):
        raise ValueError("Manifest must contain a samples array.")
    samples: list[FormulaSample] = []
    seen: set[str] = set()
    handwritten_hashes: set[str] = set()
    for item in raw["samples"]:
        if not isinstance(item, dict):
            raise ValueError("Each sample must be an object.")
        sample_id = item.get("id")
        group = item.get("group")
        reference = item.get("reference_latex")
        source = item.get("source")
        if not isinstance(sample_id, str) or not sample_id.strip() or sample_id in seen:
            raise ValueError("Each sample needs a unique nonempty ID.")
        if group not in {"SMOKE", "HANDWRITTEN"}:
            raise ValueError(f"Sample {sample_id} has an unknown group.")
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError(f"Sample {sample_id} needs verified reference_latex.")
        if item.get("reference_verified") is not True:
            raise ValueError(f"Sample {sample_id} needs reference_verified=true.")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"Sample {sample_id} needs an image provenance source.")
        if group == "HANDWRITTEN" and item.get("usage_allowed") is not True:
            raise ValueError(f"Sample {sample_id} requires explicit usage_allowed=true.")
        image_name = item.get("image")
        if not isinstance(image_name, str):
            raise ValueError(f"Sample {sample_id} needs a PNG image path.")
        image_path = _safe_image_path(path.parent, image_name)
        if group == "HANDWRITTEN":
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            if digest in handwritten_hashes:
                raise ValueError("HANDWRITTEN samples must have distinct image contents.")
            handwritten_hashes.add(digest)
        seen.add(sample_id)
        samples.append(FormulaSample(sample_id, group, image_path, reference.strip(), source))
    return samples


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Literal LaTeX character edit distance divided by reference length."""
    if not reference:
        raise ValueError("Reference must not be empty.")
    previous = list(range(len(hypothesis) + 1))
    for row, ref_char in enumerate(reference, start=1):
        current = [row]
        for col, got_char in enumerate(hypothesis, start=1):
            current.append(min(
                current[col - 1] + 1,
                previous[col] + 1,
                previous[col - 1] + (ref_char != got_char),
            ))
        previous = current
    return previous[-1] / len(reference)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class PeakMemory:
    """Sample RSS during model initialization and each sequential inference."""

    def __init__(self, process: Any) -> None:
        self.process = process
        self.peak_bytes = process.memory_info().rss
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self._stop.wait(0.01):
            try:
                self.peak_bytes = max(self.peak_bytes, self.process.memory_info().rss)
            except Exception:
                break

    def __enter__(self) -> "PeakMemory":
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=1)
        self.peak_bytes = max(self.peak_bytes, self.process.memory_info().rss)


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    times = [r["seconds"] for r in rows]
    successes = [r for r in rows if r["recognized"]]
    return {
        "samples": len(rows),
        "recognized": len(successes),
        "success_rate": len(successes) / len(rows) if rows else None,
        "exact_matches": sum(r["exact_match"] for r in rows),
        "exact_match_rate": sum(r["exact_match"] for r in rows) / len(rows) if rows else None,
        "mean_cer": statistics.mean(r["cer"] for r in rows) if rows else None,
        "mean_seconds": statistics.mean(times) if times else None,
        "p95_seconds": percentile(times, 0.95),
        "exact_mismatch_count": sum(not r["exact_match"] for r in rows),
        "actual_human_correction_count": None,
    }


def benchmark(samples: list[FormulaSample], model_dir: Path, warmup: int = 1) -> dict[str, Any]:
    """Load the real ONNX model once and run all images sequentially."""
    if not samples:
        raise ValueError("No image samples are available for inference.")
    import psutil  # optional dependency installed only in the OCR CPU environment
    from importlib.metadata import version

    process = psutil.Process()
    model_dir, model_sizes = inspect_cpu_model_files(model_dir)
    rss_before = process.memory_info().rss
    with PeakMemory(process) as peak_init:
        started = time.perf_counter()
        model = load_cpu_model(model_dir)
        init_seconds = time.perf_counter() - started
    rss_after = process.memory_info().rss
    for _ in range(warmup):
        try:
            model(samples[0].image_path.read_bytes())
        except Exception as exc:
            raise RuntimeError("Real ONNX warmup failed; no benchmark measurements were taken.") from exc

    rows: list[dict[str, Any]] = []
    for sample in samples:
        image_bytes = sample.image_path.read_bytes()
        before = process.memory_info().rss
        predicted = ""
        error_code: str | None = None
        with PeakMemory(process) as peak_sample:
            started = time.perf_counter()
            try:
                output = model(image_bytes)
                if not isinstance(output, tuple) or len(output) != 2 or not isinstance(output[0], str):
                    error_code = "MALFORMED_MODEL_RESULT"
                else:
                    predicted = output[0].strip()
                    if not predicted:
                        error_code = "EMPTY_MODEL_RESULT"
            except Exception:
                error_code = "MODEL_INFERENCE_ERROR"
            seconds = time.perf_counter() - started
        rows.append({
            "id": sample.sample_id,
            "group": sample.group,
            "source": sample.source,
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "reference_latex": sample.reference_latex,
            "predicted_latex": predicted,
            "recognized": bool(predicted),
            "exact_match": predicted == sample.reference_latex,
            "cer": character_error_rate(sample.reference_latex, predicted),
            "seconds": seconds,
            "rss_before_bytes": before,
            "rss_after_bytes": process.memory_info().rss,
            "peak_rss_bytes": peak_sample.peak_bytes,
            "error_code": error_code,
        })
    groups = {name: _summarize([row for row in rows if row["group"] == name])
              for name in ("SMOKE", "HANDWRITTEN")}
    return {
        "status": "NOT_TESTED",
        "reason": ("At least 20 permitted handwritten samples are required."
                   if groups["HANDWRITTEN"]["samples"] < 20
                   else "Agreed accuracy and p95 latency thresholds are required."),
        "environment": {
            "os": platform.platform(), "cpu": platform.processor(),
            "python": platform.python_version(),
            "physical_ram_bytes": psutil.virtual_memory().total,
            "available_ram_bytes_at_end": psutil.virtual_memory().available,
            "rapid_latex_ocr": version("rapid-latex-ocr"),
            "onnxruntime": version("onnxruntime"),
            "pillow": version("Pillow"),
            "psutil": version("psutil"),
        },
        "model": {"directory": str(model_dir), "file_sizes_bytes": model_sizes,
                  "cpu_provider": "CPUExecutionProvider"},
        "model_init_seconds": init_seconds,
        "rss_before_init_bytes": rss_before,
        "rss_after_init_bytes": rss_after,
        "peak_init_rss_bytes": peak_init.peak_bytes,
        "warmup_calls": warmup,
        "summary": groups,
        "peak_inference_rss_bytes": max(row["peak_rss_bytes"] for row in rows),
        "rss_first_after_bytes": rows[0]["rss_after_bytes"],
        "rss_last_after_bytes": rows[-1]["rss_after_bytes"],
        "samples": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, help="Pre-provisioned checkpoint directory; defaults to package models/")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--min-handwritten-exact-rate", type=float)
    parser.add_argument("--max-handwritten-p95-seconds", type=float)
    args = parser.parse_args(argv)
    if args.warmup < 0 or args.warmup > 5:
        parser.error("--warmup must be between 0 and 5")
    if args.min_handwritten_exact_rate is not None and not 0 <= args.min_handwritten_exact_rate <= 1:
        parser.error("--min-handwritten-exact-rate must be between 0 and 1")
    if args.max_handwritten_p95_seconds is not None and args.max_handwritten_p95_seconds <= 0:
        parser.error("--max-handwritten-p95-seconds must be positive")
    try:
        samples = load_manifest(args.manifest)
        if not samples:
            raise ValueError("Manifest contains no image samples.")
        model_dir = args.model_dir
        if model_dir is None:
            spec = find_spec("rapid_latex_ocr")
            if spec is None or spec.origin is None:
                raise ValueError("RapidLaTeXOCR is not installed in this environment.")
            model_dir = Path(spec.origin).resolve().parent / "models"
        report = benchmark(samples, model_dir, args.warmup)
        handwritten = report["summary"]["HANDWRITTEN"]
        if (handwritten["samples"] >= 20
                and args.min_handwritten_exact_rate is not None
                and args.max_handwritten_p95_seconds is not None):
            acceptable = (handwritten["exact_match_rate"] >= args.min_handwritten_exact_rate
                          and handwritten["p95_seconds"] <= args.max_handwritten_p95_seconds)
            report["status"] = "PASS" if acceptable else "FAIL"
            report["reason"] = None if acceptable else "Handwritten accuracy or p95 latency missed the agreed threshold."
            report["acceptance_thresholds"] = {
                "min_handwritten_exact_rate": args.min_handwritten_exact_rate,
                "max_handwritten_p95_seconds": args.max_handwritten_p95_seconds,
            }
    except (ApplicationError, ImportError, ValueError, FileNotFoundError, RuntimeError) as exc:
        report = {
            "status": "NOT_TESTED", "reason": str(exc), "samples": [],
            "summary": {"SMOKE": _summarize([]), "HANDWRITTEN": _summarize([])},
        }
    report["run_at_utc"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OCR CPU benchmark: {report['status']}; report: {args.output}")
    if report["status"] == "NOT_TESTED":
        print(f"Reason: {report['reason']}")
        return 2
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
