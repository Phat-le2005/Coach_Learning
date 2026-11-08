from __future__ import annotations

from collections import Counter
import importlib.metadata
from pathlib import Path
import re
import time

import pdfplumber

from .storage import file_hash, read_json, write_json


NATIVE_VERSION = "native-lines/v1"


def box(obj: dict) -> list[float]:
    return [round(float(obj[key]), 3) for key in ("x0", "top", "x1", "bottom")]


def is_private_use(text: str) -> bool:
    return any(0xE000 <= ord(char) <= 0xF8FF for char in text)


def margin_key(text: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", text)).strip()


def mark_margins(pages: list[dict]) -> None:
    """Only suppress repeated text at the outer edges; preserve all raw blocks."""
    positions = {}
    protected = re.compile(r'^(?:Câu|Bài|Ví dụ|Dạng|Chủ đề|Chương|Lời giải|Giải|Phần|Tìm|Tính|Ứng dụng|[IVX]+[.)])\b', re.I)
    def edge(line, page):
        if line['bbox'][1] < min(60, page['height'] * .15):return 'header'
        if line['bbox'][3] > page['height'] - min(90, page['height'] * .30):return 'footer'
        return None
    for page in pages:
        for line in page['blocks']:
            side = edge(line, page)
            if side:
                distance = line['bbox'][1] if side == 'header' else page['height'] - line['bbox'][3]
                positions.setdefault((side, margin_key(line['text_raw'])), []).append((page['page_number'], distance))
    threshold = 2 if len(pages) <= 5 else 3
    # A cropped title strip changes relative edge distances. Reuse only an
    # exact running-header signature already established on multiple pages.
    header_templates = set()
    for (side, key), samples in positions.items():
        if (side == 'header' and not protected.match(key)
                and len(re.findall(r'[^\W\d_]', key)) >= 12
                and not re.search(r'[=∩∪<>]|\bP\s*\(', key)
                and any(len({pn for pn, d in samples if abs(d-anchor) <= 5}) >= threshold
                        for _, anchor in samples)):
            header_templates.add(key)
    for page in pages:
        for line in page["blocks"]:
            side = edge(line, page)
            key = margin_key(line["text_raw"])
            learned_header = (line is page['blocks'][0] and key in header_templates
                              and line['bbox'][1] < 60)
            if learned_header:side = 'header'
            text = line['text_raw'].strip()
            distance = line['bbox'][1] if side == 'header' else page['height'] - line['bbox'][3]
            repeats = len({pn for pn, d in positions.get((side, key), []) if abs(d-distance) <= 5})
            footer = side == 'footer' and bool(re.search(
                r'https?://|^(?:Page|Trang|T\s*r\s*a\s*n\s*g)\s*\d+\s*$|^Sưu tầm và biên soạn\s*$', text, re.I))
            repeated = (side and repeats >= threshold and not protected.match(text)
                        and len(re.findall(r'[^\W\d_]', text)) >= 12
                        and not re.search(r'[=∩∪<>]|\bP\s*\(', text))
            line['is_margin'] = bool(footer or repeated or learned_header)
            line['margin_role'] = side if line['is_margin'] else None
        content = [line for line in page["blocks"] if not line["is_margin"]]
        page["content_bounds"] = [
            0.0,
            max([line["bbox"][3] + 3 for line in page["blocks"]
                 if line["is_margin"] and line["bbox"][1] < page["height"] / 2] or [0.0]),
            page["width"],
            min([line["bbox"][1] - 3 for line in page["blocks"]
                 if line["is_margin"] and line["bbox"][1] > page["height"] / 2]
                or [page["height"]]),
        ]
        page["content_block_count"] = len(content)
        if content:
            page["content_bounds"][1] = min(page["content_bounds"][1], min(b["bbox"][1] for b in content))


def extract_native(pdf: Path, output: Path, *, dpi: int = 120, progress=None) -> tuple[dict, list[dict]]:
    started = time.perf_counter()
    source_hash = file_hash(pdf)
    output.mkdir(parents=True, exist_ok=True)
    previous_manifest = output / "manifest.json"
    if previous_manifest.exists() and read_json(previous_manifest)["source_sha256"] != source_hash:
        raise ValueError("Output belongs to another source PDF. Use a new --output directory.")
    (output / "pages").mkdir(exist_ok=True)
    pages: list[dict] = []
    with pdfplumber.open(pdf) as document:
        for index, page in enumerate(document.pages, 1):
            cache = output / "pages" / f"page-{index:03}.json"
            page_image = output / "pages" / f"page-{index:03}.png"
            record = read_json(cache) if cache.exists() else None
            reuse = bool(record and (record.get("source_sha256"), record.get("parser_version"), record.get("library_version"))
                         == (source_hash, NATIVE_VERSION, importlib.metadata.version("pdfplumber")))
            if not reuse:
                page_start = time.perf_counter()
                lines = page.extract_text_lines(x_tolerance=2, y_tolerance=3, return_chars=True)
                blocks = []
                for line_index, line in enumerate(lines):
                    chars = line["chars"]
                    blocks.append({
                        "block_id": f"p{index:03}-l{line_index:04}",
                        "block_type": "native_line",
                        "bbox": box(line),
                        "reading_order": line_index,
                        "text_raw": line["text"],
                        "glyphs": [{"text": char["text"], "bbox": box(char),
                                    "font": char["fontname"], "size": round(char["size"], 3),
                                    "color": char.get("non_stroking_color")}
                                   for char in chars],
                        "review_flags": ["PRIVATE_USE_GLYPHS"] if is_private_use(line["text"]) else [],
                    })
                record = {
                    "schema_version": "page-document/v1", "source_sha256": source_hash,
                    "parser_id": "pdfplumber-native", "parser_version": NATIVE_VERSION,
                    "library_version": importlib.metadata.version("pdfplumber"),
                    "page_number": index, "width": page.width, "height": page.height,
                    "rotation": page.rotation, "coordinate_origin": "top-left",
                    "coordinate_unit": "pdf_point", "blocks": blocks,
                    "images": [{"bbox": box(image)} for image in page.images],
                    "vectors": [{"kind": kind, "bbox": box(vector)}
                                for kind, vectors in (("line", page.lines), ("rect", page.rects), ("curve", page.curves))
                                for vector in vectors],
                    "image_path": f"pages/page-{index:03}.png", "image_dpi": dpi,
                    "extraction_status": "NATIVE_EXTRACTED" if blocks else "OCR_REQUIRED",
                    "seconds": round(time.perf_counter() - page_start, 4),
                }
            if not reuse or not page_image.exists() or record.get("image_dpi") != dpi:
                page.to_image(resolution=dpi).save(page_image)
                record["image_dpi"] = dpi
            pages.append(record)
            if progress:progress(index,len(document.pages))
            if index % 10 == 0 or index == len(document.pages):
                print(f"native pages {index}/{len(document.pages)}", flush=True)
    mark_margins(pages)
    for page in pages:
        write_json(output / "pages" / f"page-{page['page_number']:03}.json", page)
    manifest = {
        "schema_version": "pdf-manifest/v1", "source_path": str(pdf.resolve()),
        "source_sha256": source_hash, "source_bytes": pdf.stat().st_size,
        "page_count": len(pages), "parser_version": NATIVE_VERSION,
        "render_dpi": dpi, "seconds": round(time.perf_counter() - started, 3),
        "pages_requiring_ocr": [p["page_number"] for p in pages if not p["blocks"]],
        "pages_with_private_use_glyphs": [p["page_number"] for p in pages
                                        if any(b["review_flags"] for b in p["blocks"])],
    }
    write_json(output / "manifest.json", manifest)
    return manifest, pages
