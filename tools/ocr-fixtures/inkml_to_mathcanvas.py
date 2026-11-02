"""InkML to MathCanvas InkStroke Converter.

Converts MathWriting InkML files into MathCanvas-compatible InkStroke[] JSON fixtures.
Preserves stroke provenance, drawing order, point geometry, and physical A4 aspect ratio.
Does NOT fabricate or mutate mathematical content.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

INKML_NS = "{http://www.w3.org/2003/InkML}"

# Standard MathCanvas A4 reference dimensions
A4_WIDTH = 794.0
A4_HEIGHT = 1123.0

# Target normalized bounding box in MathCanvas A4 space
DEFAULT_TARGET_BBOX = {
    "left": 0.10,
    "top": 0.15,
    "max_width": 0.75,
    "max_height": 0.65,
}


def parse_inkml_content(xml_text: str) -> Dict[str, Any]:
    """Parses raw InkML XML text and extracts annotations, channels, and raw traces."""
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
    a4_width: float = A4_WIDTH,
    a4_height: float = A4_HEIGHT,
) -> List[Dict[str, Any]]:
    """Normalizes raw ink traces to [0, 1] MathCanvas InkStroke format while strictly
    preserving physical aspect ratio on an A4 canvas (794 x 1123).

    Physical Aspect Ratio Formula:
    Let W = 794, H = 1123.
    scale = min(target_max_w * W / raw_width, target_max_h * H / raw_height)
    rendered_w = (raw_width * scale) / W
    rendered_h = (raw_height * scale) / H
    offset_x = target_left + (target_max_w - rendered_w) / 2
    offset_y = target_top  + (target_max_h - rendered_h) / 2
    norm_x = offset_x + (x - min_x) * scale / W
    norm_y = offset_y + (y - min_y) * scale / H

    This ensures:
    renderedAspectRatio = (delta_norm_x * W) / (delta_norm_y * H)
                        = (delta_raw_x * scale) / (delta_raw_y * scale)
                        = delta_raw_x / delta_raw_y = sourceAspectRatio
    """
    if not raw_traces:
        return []

    target = target_bbox or DEFAULT_TARGET_BBOX
    t_left = target["left"]
    t_top = target["top"]
    t_max_w = target["max_width"]
    t_max_h = target["max_height"]

    # Compute global bounding box of all raw points
    all_xs = [pt[0] for t in raw_traces for pt in t["points"]]
    all_ys = [pt[1] for t in raw_traces for pt in t["points"]]

    if not all_xs or not all_ys:
        return []

    min_x, max_x = min(all_xs), max(all_xs)
    min_y, max_y = min(all_ys), max(all_ys)

    raw_w = max_x - min_x
    raw_h = max_y - min_y

    # Handle degenerate cases gracefully
    if raw_w <= 0.0 and raw_h <= 0.0:
        # Single isolated point
        center_x = t_left + t_max_w / 2.0
        center_y = t_top + t_max_h / 2.0
        strokes = []
        for s_idx, trace in enumerate(raw_traces):
            stroke_id = f"s_{s_idx}_{trace['id']}"
            points = [{"x": round(center_x, 6), "y": round(center_y, 6), "pressure": 0.5} for _ in trace["points"]]
            strokes.append({
                "id": stroke_id,
                "tool": "PEN",
                "color": "#000000",
                "width": 2,
                "points": points,
            })
        return strokes

    if raw_w <= 0.0 and raw_h > 0.0:
        # Perfectly vertical line
        scale = (t_max_h * a4_height) / raw_h
        rendered_h = (raw_h * scale) / a4_height
        offset_x = t_left + t_max_w / 2.0
        offset_y = t_top + (t_max_h - rendered_h) / 2.0
        strokes = []
        for s_idx, trace in enumerate(raw_traces):
            stroke_id = f"s_{s_idx}_{trace['id']}"
            points = []
            for pt in trace["points"]:
                norm_x = offset_x
                norm_y = offset_y + (pt[1] - min_y) * scale / a4_height
                points.append({
                    "x": max(0.0, min(1.0, round(norm_x, 6))),
                    "y": max(0.0, min(1.0, round(norm_y, 6))),
                    "pressure": 0.5,
                })
            strokes.append({
                "id": stroke_id,
                "tool": "PEN",
                "color": "#000000",
                "width": 2,
                "points": points,
            })
        return strokes

    if raw_h <= 0.0 and raw_w > 0.0:
        # Perfectly horizontal line
        scale = (t_max_w * a4_width) / raw_w
        rendered_w = (raw_w * scale) / a4_width
        offset_x = t_left + (t_max_w - rendered_w) / 2.0
        offset_y = t_top + t_max_h / 2.0
        strokes = []
        for s_idx, trace in enumerate(raw_traces):
            stroke_id = f"s_{s_idx}_{trace['id']}"
            points = []
            for pt in trace["points"]:
                norm_x = offset_x + (pt[0] - min_x) * scale / a4_width
                norm_y = offset_y
                points.append({
                    "x": max(0.0, min(1.0, round(norm_x, 6))),
                    "y": max(0.0, min(1.0, round(norm_y, 6))),
                    "pressure": 0.5,
                })
            strokes.append({
                "id": stroke_id,
                "tool": "PEN",
                "color": "#000000",
                "width": 2,
                "points": points,
            })
        return strokes

    # Non-degenerate case: calculate physical uniform scaling factor
    scale = min(
        (t_max_w * a4_width) / raw_w,
        (t_max_h * a4_height) / raw_h,
    )

    rendered_w = (raw_w * scale) / a4_width
    rendered_h = (raw_h * scale) / a4_height

    # Center ink within target bounding box
    offset_x = t_left + (t_max_w - rendered_w) / 2.0
    offset_y = t_top + (t_max_h - rendered_h) / 2.0

    strokes = []
    for s_idx, trace in enumerate(raw_traces):
        stroke_id = f"s_{s_idx}_{trace['id']}"
        points = []
        for pt in trace["points"]:
            norm_x = offset_x + (pt[0] - min_x) * scale / a4_width
            norm_y = offset_y + (pt[1] - min_y) * scale / a4_height
            # Coordinates are strictly validated to be finite and within [0, 1]
            norm_x = max(0.0, min(1.0, round(norm_x, 6)))
            norm_y = max(0.0, min(1.0, round(norm_y, 6)))
            points.append({
                "x": norm_x,
                "y": norm_y,
                "pressure": 0.5,
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
    """Extracts and converts specified InkML paths from a tar.gz archive.

    Returns manifest of converted fixtures.
    """
    if not os.path.exists(archive_path):
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    os.makedirs(output_dir, exist_ok=True)
    manifest = []

    with tarfile.open(archive_path, "r:gz") as tar:
        for path in selected_paths:
            try:
                member = tar.getmember(path)
                f = tar.extractfile(member)
                if f is None:
                    raise IOError(f"Could not extract member: {path}")
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
                    "status": "SUCCESS",
                })
            except Exception as e:
                manifest.append({
                    "sampleId": os.path.splitext(os.path.basename(path))[0],
                    "sourcePath": path,
                    "error": str(e),
                    "status": "FAILED",
                })

    return manifest


def main() -> int:
    """CLI Entrypoint for InkML conversion."""
    parser = argparse.ArgumentParser(
        description="Convert InkML samples from MathWriting archive to MathCanvas InkStroke fixtures."
    )
    parser.add_argument("archive", help="Path to mathwriting-excerpt.tgz")
    parser.add_argument(
        "--manifest",
        help="Path to selection manifest JSON (list of paths or sample objects).",
        default=None,
    )
    parser.add_argument(
        "--output",
        default=".tmp/tri-ocr-external-fixtures",
        help="Output directory for JSON fixtures",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Number of samples to convert if manifest is not provided",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.archive):
        print(f"ERROR: Archive not found: {args.archive}", file=sys.stderr)
        return 1

    selected_paths: List[str] = []

    if args.manifest:
        if not os.path.isfile(args.manifest):
            print(f"ERROR: Manifest file not found: {args.manifest}", file=sys.stderr)
            return 1
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        if isinstance(manifest_data, list):
            for item in manifest_data:
                if isinstance(item, str):
                    selected_paths.append(item)
                elif isinstance(item, dict):
                    p = item.get("archivePath") or item.get("sourcePath") or item.get("path")
                    if p:
                        selected_paths.append(p)
        elif isinstance(manifest_data, dict):
            samples = manifest_data.get("samples") or manifest_data.get("selectedSamples") or []
            for item in samples:
                p = item.get("archivePath") or item.get("sourcePath") or item.get("path")
                if p:
                    selected_paths.append(p)

    if not selected_paths:
        # Discover up to limit human samples from train/valid/test
        print(f"No manifest provided; discovering up to {args.limit} human samples from archive...")
        with tarfile.open(args.archive, "r:gz") as tar:
            for m in tar.getmembers():
                if m.name.endswith(".inkml"):
                    parts = m.name.split("/")
                    if len(parts) >= 2 and parts[1] in ("train", "valid", "test"):
                        selected_paths.append(m.name)
                        if len(selected_paths) >= args.limit:
                            break

    print(f"Converting {len(selected_paths)} samples to {args.output}...")
    try:
        manifest = convert_archive_samples(args.archive, selected_paths, args.output)
    except Exception as e:
        print(f"ERROR during conversion: {e}", file=sys.stderr)
        return 2

    # Write converted manifest
    manifest_out = os.path.join(args.output, "converted_manifest.json")
    with open(manifest_out, "w", encoding="utf-8") as f:
        json.dump({
            "totalProcessed": len(manifest),
            "successful": sum(1 for m in manifest if m.get("status") == "SUCCESS"),
            "failed": sum(1 for m in manifest if m.get("status") == "FAILED"),
            "fixtures": manifest,
        }, f, indent=2, ensure_ascii=False)

    failures = [m for m in manifest if m.get("status") == "FAILED"]
    if failures:
        print(f"WARNING: {len(failures)} samples failed conversion.", file=sys.stderr)
        return 3

    print(f"SUCCESS: Converted {len(manifest)} samples. Manifest written to {manifest_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
