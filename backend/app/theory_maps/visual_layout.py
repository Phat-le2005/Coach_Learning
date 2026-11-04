"""Visual layout detection using ONNX models (DocLayout-YOLO / RapidLayout).

Analyzes 2D visual layout of math pages directly from rendered pixels,
detecting tables, section banners, figures, formulas, and text boxes
with exact physical bounding boxes.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
import logging
import re
import threading
from typing import Any

logger = logging.getLogger(__name__)

_ENGINE_LOCK = threading.Lock()
_LAYOUT_ENGINE = None

_CACHE_LOCK = threading.Lock()
_DOC_BLOCKS_CACHE: OrderedDict[str, dict[int, list["VisualBlock"]]] = OrderedDict()
_MAX_DOC_CACHE_ENTRIES = 16


@dataclass
class VisualBlock:
    id: str
    page: int
    ordinal: int
    kind: str  # "TITLE", "TABLE", "FIGURE", "THEORY", "NOTE", "STEP", "FORMULA"
    title: str
    top: float
    bottom: float
    left: float
    right: float
    text: str = ""
    is_table: bool = False
    confidence: float = 1.0


def get_visual_layout_engine():
    """Lazily load and cache the ONNX RapidLayout engine."""
    global _LAYOUT_ENGINE
    if _LAYOUT_ENGINE is not None:
        return _LAYOUT_ENGINE
    with _ENGINE_LOCK:
        if _LAYOUT_ENGINE is not None:
            return _LAYOUT_ENGINE
        try:
            from rapid_layout import RapidLayout
            _LAYOUT_ENGINE = RapidLayout(model_type="doclayout_docstructbench")
            logger.info("RapidLayout doclayout_docstructbench model loaded successfully.")
        except Exception as exc:
            logger.warning("Could not load RapidLayout ONNX engine: %s", exc)
            _LAYOUT_ENGINE = False
        return _LAYOUT_ENGINE


def _clean_block_title(raw_text: str, default_title: str) -> str:
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    if not lines:
        return default_title
    # Check if first line looks like a title or section heading
    first = lines[0]
    while first and (0xE000 <= ord(first[0]) <= 0xF8FF or first[0] in "•●▪▫◦‣⁃→⇒➔➜➡»«➢➣➤▸▶☞❖✦✧★☆"):
        first = first[1:].lstrip()
    if 2 <= len(first) <= 120:
        return first
    return default_title


def detect_page_visual_blocks(page, page_number: int, scale: float = 1.5) -> list[VisualBlock]:
    """Detect visual bounding boxes on a page using DocLayout ONNX model with PDFium fallback."""
    engine = get_visual_layout_engine()
    pw, ph = float(page.get_width()), float(page.get_height())
    textpage = None

    try:
        textpage = page.get_textpage()
    except Exception:
        pass

    if not engine:
        # Fallback to simple full-page block
        content_top, content_bottom = 50.0, ph - 48.0
        return [
            VisualBlock(
                id=f"p{page_number}-b0",
                page=page_number,
                ordinal=0,
                kind="THEORY",
                title=f"Trang {page_number}",
                top=content_top,
                bottom=content_bottom,
                left=20.0,
                right=pw - 20.0,
            )
        ]

    try:
        import numpy as np
        pil_img = page.render(scale=scale).to_pil().convert("RGB")
        img_np = np.array(pil_img)

        with _ENGINE_LOCK:
            out = engine(img_np)

        raw_blocks: list[tuple[float, float, float, float, str, float]] = []
        for b, s, c in zip(out.boxes, out.scores, out.class_names):
            if s < 0.45 or c in ("abandon", "table_footnote"):
                continue
            x0, y0, x1, y1 = [float(v) / scale for v in b]
            # Ignore tiny margin artifacts
            if y1 - y0 < 12 or x1 - x0 < 15:
                continue
            # Ignore headers/footers in extreme top/bottom margins
            if y1 < 45 or y0 > ph - 45:
                continue
            raw_blocks.append((x0, y0, x1, y1, c, float(s)))

        # Sort vertically by y0 (top)
        raw_blocks.sort(key=lambda item: item[1])

        # If no significant blocks detected, provide full page fallback
        if not raw_blocks:
            content_top, content_bottom = 50.0, ph - 48.0
            return [
                VisualBlock(
                    id=f"p{page_number}-b0",
                    page=page_number,
                    ordinal=0,
                    kind="THEORY",
                    title=f"Trang {page_number}",
                    top=content_top,
                    bottom=content_bottom,
                    left=20.0,
                    right=pw - 20.0,
                )
            ]

        visual_blocks: list[VisualBlock] = []
        for idx, (x0, y0, x1, y1, cname, score) in enumerate(raw_blocks):
            # Extract bounded text
            bounded_text = ""
            if textpage is not None:
                try:
                    # PDFium y-axis is inverted: bottom = ph - y1, top = ph - y0
                    bounded_text = textpage.get_text_bounded(
                        left=max(0.0, x0 - 2.0),
                        bottom=max(0.0, ph - (y1 + 2.0)),
                        right=min(pw, x1 + 2.0),
                        top=min(ph, ph - (y0 - 2.0)),
                    ).strip()
                except Exception:
                    pass

            is_table = (cname in ("table", "table_caption"))
            kind = (
                "TABLE" if is_table else
                "TITLE" if cname == "title" else
                "FIGURE" if cname == "figure" else
                "FORMULA" if cname == "isolate_formula" else
                "THEORY"
            )

            # Determine title
            def_title = (
                f"Bảng công thức (Trang {page_number})" if is_table else
                f"Nội dung trọng tâm (Trang {page_number})"
            )
            title = _clean_block_title(bounded_text, def_title)

            # Adjust horizontal margin for nice full-width cards if not a side figure
            left_margin = max(15.0, round(x0, 1))
            right_margin = min(pw - 15.0, round(x1, 1))
            if is_table or cname in ("title", "plain text"):
                left_margin = 20.0
                right_margin = pw - 20.0

            visual_blocks.append(VisualBlock(
                id=f"p{page_number}-b{len(visual_blocks)}",
                page=page_number,
                ordinal=len(visual_blocks),
                kind=kind,
                title=title,
                top=round(max(40.0, y0 - 2.0), 1),
                bottom=round(min(ph - 40.0, y1 + 2.0), 1),
                left=left_margin,
                right=right_margin,
                text=bounded_text,
                is_table=is_table,
                confidence=score,
            ))

        return visual_blocks

    except Exception as exc:
        logger.warning("Error running visual layout detection on page %d: %s", page_number, exc)
        return [
            VisualBlock(
                id=f"p{page_number}-b0",
                page=page_number,
                ordinal=0,
                kind="THEORY",
                title=f"Trang {page_number}",
                top=50.0,
                bottom=ph - 48.0,
                left=20.0,
                right=pw - 20.0,
            )
        ]
    finally:
        if textpage is not None:
            try:
                textpage.close()
            except Exception:
                pass


def detect_document_visual_blocks(content: bytes) -> dict[int, list[VisualBlock]]:
    """Detect visual blocks for all pages of a document with thread-safe SHA256 caching."""
    digest = sha256(content).hexdigest()
    with _CACHE_LOCK:
        if digest in _DOC_BLOCKS_CACHE:
            _DOC_BLOCKS_CACHE.move_to_end(digest)
            return _DOC_BLOCKS_CACHE[digest]

    try:
        import pypdfium2 as pdfium
        document = pdfium.PdfDocument(content)
        result: dict[int, list[VisualBlock]] = {}
        for pno in range(len(document)):
            page = document[pno]
            try:
                blocks = detect_page_visual_blocks(page, pno + 1)
                result[pno + 1] = blocks
            finally:
                try:
                    page.close()
                except Exception:
                    pass
        document.close()

        with _CACHE_LOCK:
            _DOC_BLOCKS_CACHE[digest] = result
            if len(_DOC_BLOCKS_CACHE) > _MAX_DOC_CACHE_ENTRIES:
                _DOC_BLOCKS_CACHE.popitem(last=False)

        return result

    except Exception as exc:
        logger.error("Failed to detect document visual blocks: %s", exc)
        return {}


def is_in_table_region(page: int, top: float, bottom: float, doc_blocks: dict[int, list[VisualBlock]]) -> bool:
    """True if the given vertical line span falls within a detected table box."""
    p_blocks = doc_blocks.get(page, [])
    for b in p_blocks:
        if b.is_table and (b.top - 6.0 <= top <= b.bottom + 6.0 or b.top - 6.0 <= bottom <= b.bottom + 6.0):
            return True
    return False
