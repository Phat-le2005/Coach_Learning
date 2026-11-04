"""Spatial and typography layout engine for educational mathematics PDFs.

Analyzes 2D visual layout (coordinates, heights, font styles) and repetition
across pages to filter headers/footers, recognize multi-column layouts,
and reconstruct reading order.
"""

from collections import Counter
from dataclasses import dataclass, field
import re
from typing import Any

_DOT_LEADER = re.compile(r"\.{5,}")
_PAGE_NUMBER = re.compile(r"^(?:trang\s*)?\d+(?:\s*/\s*\d+)?$", re.I)
_LEADING_DECORATION = "•●▪▫◦‣⁃→⇒➔➜➡»«➢➣➤▸▶☞❖✦✧★☆"


def clean_line_text(raw: str) -> str:
    """Strip decorative bullets and private-use glyphs at line boundaries."""
    value = raw.strip()
    while value and (0xE000 <= ord(value[0]) <= 0xF8FF or value[0] in _LEADING_DECORATION):
        value = value[1:].lstrip()
    return " ".join(value.split())


def is_reliable_text(value: str) -> bool:
    """True if text has no replacement or unmapped Unicode PUA glyphs."""
    return bool(value) and "\ufffd" not in value and not any(
        0xE000 <= ord(c) <= 0xF8FF for c in value
    )


@dataclass
class TextLine:
    page: int
    text: str
    raw_text: str
    top: float
    bottom: float
    left: float
    right: float
    height: float
    is_repeated_header_or_footer: bool = False
    is_contents_item: bool = False


@dataclass
class DocumentProfile:
    page_count: int
    page_dimensions: dict[int, tuple[float, float]]  # page -> (width, height)
    repeated_marginal_texts: set[str] = field(default_factory=set)
    contents_pages: set[int] = field(default_factory=set)
    contents_outline: list[dict[str, Any]] = field(default_factory=list)
    median_text_height: float = 10.0


class DocumentProfiler:
    """Detects global characteristics: repetitive banners, table of contents, and margins."""

    def __init__(self, page_texts: list[str], content: bytes | None = None) -> None:
        self.page_texts = page_texts
        self.content = content
        self.profile = DocumentProfile(
            page_count=len(page_texts),
            page_dimensions={},
        )
        self._analyze()

    def _analyze(self) -> None:
        # Detect contents pages and repetitive header/footer lines across pages
        line_occurrences: Counter[str] = Counter()
        for page_idx, page_str in enumerate(self.page_texts, 1):
            lines = [clean_line_text(l) for l in page_str.splitlines() if l.strip()]
            if not lines:
                continue

            # Check if page is a Table of Contents (Mục lục)
            has_muc_luc = any(l.casefold() in ("mục lục", "table of contents") for l in lines)
            dot_leaders = sum(bool(_DOT_LEADER.search(l)) for l in lines)
            if has_muc_luc or dot_leaders >= 3:
                self.profile.contents_pages.add(page_idx)
                # Parse contents outline if possible
                for l in lines:
                    if _DOT_LEADER.search(l):
                        title_part = _DOT_LEADER.split(l)[0].strip()
                        if title_part and is_reliable_text(title_part):
                            self.profile.contents_outline.append({
                                "title": title_part,
                                "source_page": page_idx,
                            })

            # Check top 3 lines and bottom 3 lines for repetition (headers / footers)
            marginal_candidates = lines[:3] + lines[-3:]
            for cand in marginal_candidates:
                if len(cand) >= 3 and not _DOT_LEADER.search(cand):
                    # Normalize numbers so "Trang 1", "Trang 2" are recognized as page numbers
                    normalized_cand = re.sub(r"\d+", "#", cand.casefold())
                    line_occurrences[normalized_cand] += 1

        # Any line appearing in the margins across >= 3 pages (or >= 40% of small docs) is repetitive
        threshold = max(3, int(len(self.page_texts) * 0.25))
        for cand, count in line_occurrences.items():
            if count >= threshold:
                self.profile.repeated_marginal_texts.add(cand)

    def is_marginal_noise(self, line_text: str, top: float, page_height: float) -> bool:
        """Filter out running headers, footers, website URLs, and page numbers."""
        cleaned = clean_line_text(line_text)
        if not cleaned:
            return True
        # Check standard page numbers
        if _PAGE_NUMBER.match(cleaned):
            return True
        # Check if in extreme margins
        if top < 35.0 or top > page_height - 35.0:
            if "mapstudy" in cleaned.casefold() or "trang" in cleaned.casefold() or len(cleaned.split()) <= 4:
                return True
        norm = re.sub(r"\d+", "#", cleaned.casefold())
        return norm in self.profile.repeated_marginal_texts


def extract_page_lines_2d(
    page: Any,
    page_number: int,
    profiler: DocumentProfiler,
) -> list[TextLine]:
    """Extract lines sorted by reading order with precise 2D geometry."""
    height = page.get_height()
    width = page.get_width()
    tp = page.get_textpage()
    char_count = tp.count_chars()
    if char_count == 0:
        tp.close()
        return []

    full_text = tp.get_text_range(0, char_count)
    lines: list[TextLine] = []

    # Map raw text lines to bounding boxes
    offset = 0
    for raw in full_text.splitlines(True):
        cleaned = clean_line_text(raw)
        s_raw = raw.strip()
        if s_raw and is_reliable_text(cleaned):
            first_char_idx = offset + raw.index(s_raw[0])
            last_char_idx = offset + raw.index(s_raw[-1])
            try:
                box_first = tp.get_charbox(first_char_idx)
                box_last = tp.get_charbox(last_char_idx)
                # pypdfium2: (left, bottom, right, top) from bottom-left origin
                # Convert to top-down coordinates:
                top_coord = round(height - max(box_first[3], box_last[3]), 2)
                bottom_coord = round(height - min(box_first[1], box_last[1]), 2)
                left_coord = round(min(box_first[0], box_last[0]), 2)
                right_coord = round(max(box_first[2], box_last[2]), 2)
                line_height = round(bottom_coord - top_coord, 2)

                is_noise = profiler.is_marginal_noise(cleaned, top_coord, height)
                lines.append(TextLine(
                    page=page_number,
                    text=cleaned,
                    raw_text=s_raw,
                    top=top_coord,
                    bottom=bottom_coord,
                    left=left_coord,
                    right=right_coord,
                    height=line_height,
                    is_repeated_header_or_footer=is_noise,
                ))
            except Exception:
                pass
        offset += len(raw)

    tp.close()

    # Detect multi-column vs single-column reading order:
    # A true 2-column page has balanced columns across the middle gutter,
    # OR contains an isolated callout box on the right (⚠️ Chú ý, Nhận xét).
    mid_x = width / 2.0
    left_col = [l for l in lines if not l.is_repeated_header_or_footer and l.right < mid_x + 10]
    right_col = [l for l in lines if not l.is_repeated_header_or_footer and l.left > mid_x - 10]
    min_col_count = min(len(left_col), len(right_col))
    max_col_count = max(len(left_col), len(right_col), 1)
    is_two_column = (
        len(left_col) >= 8
        and len(right_col) >= 8
        and (min_col_count / max_col_count) >= 0.45
        and (len(left_col) + len(right_col)) >= len(lines) * 0.75
    )
    has_side_callout = (
        len(right_col) >= 2
        and len(left_col) >= 3
        and any(
            any(kw in l.text.casefold() for kw in ("chú ý", "nhận xét", "lưu ý", "ghi nhớ", "⚠️"))
            for l in right_col
        )
    )

    if is_two_column or has_side_callout:
        # Sort left column top-to-bottom, then right column top-to-bottom
        left_sorted = sorted(left_col, key=lambda l: l.top)
        right_sorted = sorted(right_col, key=lambda l: l.top)
        other = sorted([l for l in lines if l not in left_col and l not in right_col], key=lambda l: l.top)
        # Banners across top span first, then columns, then footers
        min_top = min(left_sorted[0].top, right_sorted[0].top) if left_sorted and right_sorted else 100.0
        top_spans = [l for l in other if l.top < min_top]
        bottom_spans = [l for l in other if l not in top_spans]
        lines = top_spans + left_sorted + right_sorted + bottom_spans
    else:
        # Standard top-to-bottom sorting
        lines.sort(key=lambda l: l.top)

    return lines
