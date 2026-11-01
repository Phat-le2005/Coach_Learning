"""InkML to MathCanvas InkStroke Converter.

Converts MathWriting InkML files into MathCanvas-compatible InkStroke[] JSON fixtures.
Preserves stroke provenance, drawing order, point geometry, and aspect ratio.
Does NOT fabricate or mutate mathematical content.
"""

from __future__ import annotations

import argparse
import json
import os
import tarfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

INKML_NS = "{http://www.w3.org/2003/InkML}"

# Standard MathCanvas A4 target layout: centered in working canvas with margins
DEFAULT_TARGET_BBOX = {
    "left": 0.10,
    "top": 0.15,
    "max_width": 0.75,
    "max_height": 0.65,
}


def parse_inkml_content(xml_text: str) -> Dict[str, Any]:
    """Parses raw InkML XML text and extracts annotations and raw traces."""
    root = ET.fromstring(xml_text)

    # Extract metadata annotations
    annotations: Dict[str, str] = {}
    for ann in root.findall(f"{INKML_NS}annotation"):
        ann_type = ann.attrib.get("type", "")
        if ann_type:
            annotations[ann_type] = ann.text or ""

    # Parse trace format to identify channels
    channels = ["X", "Y"]
    trace_format = root.find(f"{INKML_NS}traceFormat")
    if trace_format is not None:
        found_channels = []
        for ch in trace_format.findall(f"{INKML_NS}channel"):
            found_channels.append(ch.attrib.get("name", "").upper())
        if "X" in found_channels and "Y" in found_channels:
            channels = found_channels

    x_idx = channels.index("X") if "X" in channels else 0
    y_idx = channels.index("Y") if "Y" in channels else 1
    t_idx = channels.index("T") if "T" in channels else -1

    # Extract raw traces
    raw_traces: List[Dict[str, Any]] = []
    for trace_elem in root.findall(f"{INKML_NS}trace"):
        trace_id = trace_elem.attrib.get("id", str(len(raw_traces)))
        text = (trace_elem.text or "").strip()
        if not text:
            continue

        raw_points: List[Tuple[float, float, Optional[float]]] = []
        for pt_str in text.split(","):
            pt_str = pt_str.strip()
            if not pt_str:
                continue
            parts = pt_str.split()
            if len(parts) < 2:
                continue
            try:
                x = float(parts[x_idx])
                y = float(parts[y_idx])
                t = float(parts[t_idx]) if (t_idx >= 0 and len(parts) > t_idx) else None
                raw_points.append((x, y, t))
            except ValueError:
                continue

        if raw_points:
            raw_traces.append({"id": trace_id, "points": raw_points})

    return {
        "annotations": annotations,
        "channels": channels,
        "raw_traces": raw_traces,
    }


def normalize_traces_to_mathcanvas(
    raw_traces: List[Dict[str, Any]],
    target_bbox: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Normalizes raw ink traces to [0, 1] MathCanvas InkStroke format.

    Preserves:
    1. Exact stroke count and stroke order.
    2. Point count per stroke.
    3. Geometric aspect ratio (isotropic scaling).
    """
    if not raw_traces:
        return []

    target = target_bbox or DEFAULT_TARGET_BBOX
    t_left = target["left"]
    t_top = target["top"]
    t_max_w = target["max_width"]
    t_max_h = target["max_height"]

    # Compute global bounding box of all points
    all_xs = [pt[0] for t in raw_traces for pt in t["points"]]
    all_ys = [pt[1] for t in raw_traces for pt in t["points"]]

    if not all_xs or not all_ys:
        return []

    min_x, max_x = min(all_xs), max(all_xs)
    min_y, max_y = min(all_ys), max(all_ys)

    span_x = max(1e-6, max_x - min_x)
    span_y = max(1e-6, max_y - min_y)

    # Uniform scale factor preserving exact aspect ratio
    scale = min(t_max_w / span_x, t_max_h / span_y)

    strokes: List[Dict[str, Any]] = []
    for s_idx, trace in enumerate(raw_traces):
        stroke_id = f"s_{s_idx}_{trace['id']}"
        points = []
        for pt in trace["points"]:
            norm_x = t_left + (pt[0] - min_x) * scale
            norm_y = t_top + (pt[1] - min_y) * scale
            # Clamp strictly to [0, 1]
            norm_x = max(0.0, min(1.0, round(norm_x, 6)))
            norm_y = max(0.0, min(1.0, round(norm_y, 6)))
            points.append({
                "x": norm_x,
                "y": norm_y,
                "pressure": 0.5,  # Standard fallback pressure for converted external ink
            })

        strokes.append({
            "id": stroke_id,
            "tool": "PEN",
            "color": "#000000",
            "width": 2,
            "points": points,
        })

    return strokes


def convert_inkml_to_fixture(
    xml_text: str,
    source_path: str,
    sample_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Converts an InkML sample into a standardized INKML_EXTERNAL fixture."""
    parsed = parse_inkml_content(xml_text)
    annotations = parsed["annotations"]
    raw_traces = parsed["raw_traces"]

    resolved_sample_id = (
        sample_id
        or annotations.get("sampleId")
        or os.path.splitext(os.path.basename(source_path))[0]
    )

    strokes = normalize_traces_to_mathcanvas(raw_traces)

    total_raw_points = sum(len(t["points"]) for t in raw_traces)
    total_conv_points = sum(len(s["points"]) for s in strokes)

    return {
        "fixtureKind": "INKML_EXTERNAL",
        "schemaVersion": 1,
        "sourceDataset": "MathWriting-2024-excerpt",
        "sampleId": resolved_sample_id,
        "sourcePath": source_path,
        "provenance": {
            "inkCreationMethod": annotations.get("inkCreationMethod", "unknown"),
            "split": annotations.get("splitTagOriginal", ""),
            "label": annotations.get("label", ""),
            "normalizedLabel": annotations.get("normalizedLabel", ""),
        },
        "stats": {
            "numSourceStrokes": len(raw_traces),
            "numConvertedStrokes": len(strokes),
            "numSourcePoints": total_raw_points,
            "numConvertedPoints": total_conv_points,
        },
        "strokes": strokes,
    }


def convert_archive_samples(
    archive_path: str,
    selected_paths: List[str],
    output_dir: str,
) -> List[Dict[str, Any]]:
    """Extracts and converts specified InkML paths from a tar.gz archive."""
    os.makedirs(output_dir, exist_ok=True)
    manifest = []

    with tarfile.open(archive_path, "r:gz") as tar:
        for path in selected_paths:
            try:
                member = tar.getmember(path)
                f = tar.extractfile(member)
                if f is None:
                    continue
                xml_text = f.read().decode("utf-8")
                sample_id = os.path.splitext(os.path.basename(path))[0]
                fixture = convert_inkml_to_fixture(xml_text, source_path=path, sample_id=sample_id)

                out_filename = f"{sample_id}.json"
                out_path = os.path.join(output_dir, out_filename)
                with open(out_path, "w", encoding="utf-8") as out_f:
                    json.dump(fixture, out_f, indent=2, ensure_ascii=False)

                manifest.append({
                    "sampleId": sample_id,
                    "sourcePath": path,
                    "fixturePath": out_path,
                    "strokes": fixture["stats"]["numConvertedStrokes"],
                    "points": fixture["stats"]["numConvertedPoints"],
                    "label": fixture["provenance"]["normalizedLabel"],
                    "creationMethod": fixture["provenance"]["inkCreationMethod"],
                })
            except Exception as e:
                manifest.append({
                    "sampleId": os.path.splitext(os.path.basename(path))[0],
                    "sourcePath": path,
                    "error": str(e),
                })

    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert InkML samples to MathCanvas InkStroke fixtures.")
    parser.add_argument("archive", help="Path to mathwriting-excerpt.tgz")
    parser.add_argument("--output", default=".tmp/tri-ocr-external-fixtures", help="Output directory")
    parser.add_argument("--limit", type=int, default=15, help="Number of samples to convert")
    args = parser.parse_args()

    print(f"Reading {args.archive} -> {args.output} (limit={args.limit})")
