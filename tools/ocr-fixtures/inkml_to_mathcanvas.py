#!/usr/bin/env python3
"""Convert selected online-ink InkML examples to local-only MathCanvas stroke fixtures.

No external dependencies, no network access, no dataset redistribution. Not a
semantic segmentation ground truth generator. Keep the outputs under .tmp/.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_inkml(data: bytes) -> tuple[list[list[tuple[float, float]]], str | None]:
    # stdlib ElementTree does not resolve external entities.
    root = ET.fromstring(data)
    traces: list[list[tuple[float, float]]] = []
    label: str | None = None
    for node in root.iter():
        name = local_name(node.tag)
        if name == "annotation" and node.attrib.get("type") in ("normalizedLabel", "truth"):
            label = (node.text or "").strip() or label
        if name != "trace":
            continue
        points = []
        for raw in (node.text or "").split(","):
            parts = raw.strip().split()
            if len(parts) < 2:
                continue
            try:
                x, y = float(parts[0]), float(parts[1])
            except ValueError:
                continue
            if math.isfinite(x) and math.isfinite(y):
                points.append((x, y))
        if points:
            traces.append(points)
    if not traces:
        raise ValueError("InkML contains no supported XY traces")
    return traces, label


def to_mathcanvas(traces: list[list[tuple[float, float]]]) -> list[dict]:
    flat = [p for trace in traces for p in trace]
    x0, x1 = min(x for x, _ in flat), max(x for x, _ in flat)
    y0, y1 = min(y for _, y in flat), max(y for _, y in flat)
    # Preserve the physical aspect ratio under the current A4 canvas geometry.
    # This normalization does NOT preserve original device size or pressure.
    scale = min((0.8 * 794) / max(x1 - x0, 1e-6),
                (0.6 * 1123) / max(y1 - y0, 1e-6))
    strokes = []
    for i, trace in enumerate(traces):
        points = [
            {"x": round(0.1 + (x - x0) * scale / 794, 7),
             "y": round(0.1 + (y - y0) * scale / 1123, 7),
             "pressure": 0.5}
            for x, y in trace
        ]
        strokes.append({"id": f"inkml-{i}", "tool": "PEN",
                        "color": "#000000", "width": 2, "points": points})
    return strokes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path, help="MathWriting excerpt .tgz or directory of InkML files")
    ap.add_argument("--output", type=Path, default=Path(".tmp/tri-ocr-external-fixtures"))
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()
    if not (1 <= args.limit <= 100):
        ap.error("--limit must be between 1 and 100")

    members: list[tuple[str, bytes]] = []
    if args.source.is_dir():
        for p in args.source.rglob("*.inkml"):
            if "synthetic" not in p.parts and "symbols" not in p.parts:
                members.append((str(p.relative_to(args.source)), p.read_bytes()))
    else:
        with tarfile.open(args.source, "r:gz") as tar:
            for item in tar:
                name = item.name
                parts = Path(name).parts
                if not item.isfile() or not name.lower().endswith(".inkml"):
                    continue
                if "synthetic" in parts or "symbols" in parts:
                    continue
                if item.size > 2_000_000:
                    continue
                file = tar.extractfile(item)
                if file:
                    members.append((name, file.read()))
    members.sort(key=lambda entry: entry[0])
    random.Random(args.seed).shuffle(members)
    args.output.mkdir(parents=True, exist_ok=True)
    written = 0
    for source_name, source_bytes in members:
        if written >= args.limit:
            break
        try:
            traces, label = read_inkml(source_bytes)
        except (ET.ParseError, ValueError):
            continue
        lower_parts = [s.lower() for s in Path(source_name).parts]
        split = next((s for s in ("train", "valid", "test") if s in lower_parts), None)
        fixture = {
            "schemaVersion": 1,
            "sourceKind": "INKML_EXTERNAL",
            "sourcePath": source_name,
            "originSplit": split,
            "humanWrittenProvenance": "DATASET_SPLIT" if split else "UNVERIFIED",
            "isComposedMultiStepSolution": False,
            "transcriptionLabel": label,
            "strokes": to_mathcanvas(traces),
        }
        target = args.output / f"inkml_{written + 1:03d}.json"
        target.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
        written += 1
    print(f"Converted {written} samples into {args.output}")
    if written < args.limit:
        print("Fewer supported InkML samples were present than requested; no samples were invented.")


if __name__ == "__main__":
    main()
