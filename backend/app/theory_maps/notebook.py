"""A source-faithful math notebook made of visual PDF regions.

The math in this PDF uses custom fonts, so text extraction cannot be trusted to
reconstruct formulas. Cards therefore show pixels rendered from the original
page. Recognized headings only supply navigation and card labels.
"""

from collections import OrderedDict
import copy
from hashlib import sha256
from io import BytesIO
import logging
import re
import threading

from app.core.exceptions import ApplicationError
from app.theory_maps.local_draft import (
    _CHAPTER_NUMBER_SOLO,
    _CHAPTER_SOLO,
    _clean_line,
    _dedup_repeated_banner,
    _is_uppercase_vietnamese_heading,
    parse_roman_topic_heading,
)
from app.theory_maps.pdf_extraction import MAX_PAGES

logger = logging.getLogger(__name__)

# Process-level thread lock for PDFium operations because the underlying
# PDFium C library maintains global state that is not thread-safe.
_PDFIUM_LOCK = threading.Lock()

# Thread-safe LRU cache for notebook index dictionaries keyed by SHA-256 hash.
_NOTEBOOK_INDEX_CACHE: OrderedDict[str, dict] = OrderedDict()
_MAX_CACHE_ENTRIES = 32
_CACHE_LOCK = threading.Lock()

# Thread-safe LRU cache for rendered block card images keyed by (sha256, page, ordinal).
_NOTEBOOK_IMAGE_CACHE: OrderedDict[tuple[str, int, int], bytes] = OrderedDict()
_MAX_IMAGE_CACHE_ENTRIES = 256
_IMAGE_CACHE_LOCK = threading.Lock()


_ANCHOR = re.compile(
    r"(?im)^[ \t\uf000-\uf8ff]*(?P<title>"
    r"A\.\s+LÝ THUYẾT CHUNG\.?|"
    r"Dạng\s+\d+\.\d+\.?[^\r\n]{0,150}|"
    r"(?:(?:\d+\.\s+)?Bài toán\s+\d+\b[^\r\n]{0,100})|"
    r"Bước[ \t]+\d{1,2}\.?|"
    r"Ví dụ\s+\d+(?:\.\d+)*\.?[^\r\n]{0,100}|"
    r"(?:Định nghĩa|Định l[ýí]|Tính chất|Hệ quả|Nhận xét|Chú ý|Ghi nhớ|Lưu ý|Ý nghĩa)(?:[ \t]*\.?[ \t]*\d+)?\.?|"
    r"(?:Example|Theorem|Definition)(?:[ \t]+\d+)?\.?|"
    r"[IVX]+\.\s+[^\r\n]{2,100}|"
    r"\d+(?:\.\d+)*[.)]\s+[A-ZÀ-Ỹa-zà-ỹ][^\r\n]{2,100}"
    r")",
)
_CHAPTER = re.compile(r"(?:Chủ đề|Chương)\s+(\d+)\.?\s*([^\r\n.]{2,100})", re.I)
_METHOD_NUMBER = re.compile(r"Dạng\s+(\d+)\.\d+", re.I)
_DOT_LEADER = re.compile(r"\.{5,}")


def _pdf(content: bytes):
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise ApplicationError(503, "PDF_RENDERER_UNAVAILABLE", "Install pypdfium2 to display notebook pages.") from exc
    try:
        document = pdfium.PdfDocument(content)
        if not 1 <= len(document) <= MAX_PAGES:
            raise ApplicationError(422, "PDF_PAGE_LIMIT", "Invalid notebook page count.")
        return document
    except ApplicationError:
        raise
    except Exception as exc:
        raise ApplicationError(422, "PDF_RENDER_FAILED", "Could not open the original PDF.") from exc


def _page_blocks(page, page_number: int) -> list[dict]:
    textpage = None
    try:
        height = page.get_height()
        textpage = page.get_textpage()
        char_count = textpage.count_chars()
        text = textpage.get_text_range(0, char_count) if char_count > 0 else ""

        anchors: list[tuple[float, str, str]] = []
        for raw in text.splitlines():
            line = _clean_line(raw)
            if not line or "\ufffd" in line or _DOT_LEADER.search(line) or any(0xE000 <= ord(c) <= 0xF8FF for c in line):
                continue
            rt = parse_roman_topic_heading(line)
            title = None
            kind = None
            if rt:
                title = rt[1]
                kind = "TOPIC"
            else:
                match = _ANCHOR.match(line)
                if match:
                    matched_title = " ".join(match.group("title").split()).strip(" .")
                    clean_full = " ".join(line.split()).strip(" .")
                    if len(clean_full) > len(matched_title) and matched_title.casefold() in (
                        "nhận xét", "chú ý", "ghi nhớ", "lưu ý", "ý nghĩa", "định nghĩa", "định lý", "định lí", "tính chất", "hệ quả"
                    ):
                        title = clean_full[:120].strip(" .")
                    else:
                        title = matched_title
                    lower = title.casefold()
                    kind = (
                        "METHOD" if lower.startswith(("dạng ", "bài toán ")) else
                        "EXAMPLE" if lower.startswith(("ví dụ", "example")) else
                        "STEP" if lower.startswith("bước ") else
                        "NOTE" if lower.startswith(("nhận xét", "chú ý", "ghi nhớ", "lưu ý", "ý nghĩa")) else
                        "SECTION" if re.match(r"^\d+(?:\.\d+)*[.)]", title) else "THEORY"
                    )
            if not title or not kind:
                continue

            try:
                pos = text.find(raw.strip())
                if pos < 0:
                    continue
                top = height - textpage.get_charbox(pos)[3]
            except Exception:
                continue

            # Some math PDFs put the heading number in a separate text object on
            # the same baseline ("Định lý.\r\n01"). Preserve that source number.
            trailing_number = re.match(r"[ \t]*\r?\n[ \t]*(\d{1,3})[ \t]*(?=\r?\n|$)", text[pos + len(raw.strip()):])
            if trailing_number and not re.search(r"\d", title):
                number_at = pos + len(raw.strip()) + trailing_number.start(1)
                try:
                    number_top = height - textpage.get_charbox(number_at)[3]
                    if abs(number_top - top) < 12:
                        title = f"{title.rstrip('.')} {trailing_number.group(1)}"
                except Exception:
                    pass

            if not 48 <= top <= height - 52:
                continue
            anchors.append((top, title, kind))
        # Detect multiline chapter headings (e.g. "CHƯƠNG\n4\nCÔNG THỨC NGUYÊN HÀM")
        page_lines = [_clean_line(r) for r in text.splitlines() if _clean_line(r)]
        for i, l in enumerate(page_lines):
            if _CHAPTER_SOLO.fullmatch(l) and i + 2 < len(page_lines):
                num_line = page_lines[i + 1]
                title_line = page_lines[i + 2]
                if _CHAPTER_NUMBER_SOLO.fullmatch(num_line) and _is_uppercase_vietnamese_heading(title_line):
                    name = _dedup_repeated_banner(title_line)
                    if i + 3 < len(page_lines) and _is_uppercase_vietnamese_heading(page_lines[i + 3]):
                        extra = _dedup_repeated_banner(page_lines[i + 3])
                        if extra != name:
                            name = f"{name} - {extra}"
                    chap_full_title = f"Chương {num_line} · {name}"
                    pos = text.find(l)
                    top_y = 60.0
                    if pos >= 0:
                        try:
                            top_y = height - textpage.get_charbox(pos)[3]
                        except Exception:
                            pass
                    anchors.append((top_y, chap_full_title, "CHAPTER"))
                    break

        anchors.sort(key=lambda entry: entry[0])
        # PDF text-stream order need not match vertical reading order.
        distinct: list[tuple[float, str, str]] = []
        for anchor in anchors:
            if not distinct or anchor[0] - distinct[-1][0] >= 12:
                distinct.append(anchor)
        anchors = distinct
        blocks: list[dict] = []
        content_top, content_bottom = 50.0, height - 48.0
        if not anchors:
            if char_count < 300:
                return [
                    {"id": f"p{page_number}-b0", "page": page_number, "ordinal": 0,
                     "kind": "CONTINUATION", "title": f"Trang {page_number}", "top": content_top, "bottom": content_bottom}
                ]
            mid_y = round(content_top + (content_bottom - content_top) * 0.52, 2)
            return [
                {"id": f"p{page_number}-b0", "page": page_number, "ordinal": 0,
                 "kind": "CONTINUATION", "title": f"Trang {page_number} - Phần 1", "top": content_top, "bottom": mid_y},
                {"id": f"p{page_number}-b1", "page": page_number, "ordinal": 1,
                 "kind": "CONTINUATION", "title": f"Trang {page_number} - Phần 2", "top": mid_y, "bottom": content_bottom},
            ]
        prefix_text = textpage.get_text_bounded(
            left=0, bottom=height - (anchors[0][0] - 2),
            right=page.get_width(), top=height - content_top,
        ).strip() if anchors[0][0] - content_top > 24 else ""
        clean_pref = _clean_line(prefix_text)
        is_banner = _is_uppercase_vietnamese_heading(clean_pref) or len(clean_pref.split()) <= 6 or any(kw in clean_pref.casefold() for kw in ("ứng dụng", "chương", "chủ đề", "toán"))
        if prefix_text and not is_banner and anchors[0][0] > 220:
            blocks.append({"id": f"p{page_number}-b0", "page": page_number, "ordinal": 0,
                           "kind": "CONTINUATION", "title": "Tiếp theo", "top": content_top,
                           "bottom": round(anchors[0][0] - 2, 2)})
        for index, (top, title, kind) in enumerate(anchors):
            start = content_top if (index == 0 and not blocks) else max(content_top, top - 2)
            end = anchors[index + 1][0] - 2 if index + 1 < len(anchors) else content_bottom
            if end - start < 18:
                continue
            blocks.append({"id": f"p{page_number}-b{len(blocks)}", "page": page_number,
                           "ordinal": len(blocks), "kind": kind, "title": title,
                           "top": round(start, 2), "bottom": round(min(end, content_bottom), 2)})
        return blocks or [{"id": f"p{page_number}-b0", "page": page_number, "ordinal": 0,
                           "kind": "CONTINUATION", "title": "Nội dung trang", "top": content_top, "bottom": content_bottom}]
    except Exception as exc:
        logger.warning("Error getting textpage for page %d: %s", page_number, exc)
        return [{"id": f"p{page_number}-b0", "page": page_number, "ordinal": 0,
                 "kind": "CONTINUATION", "title": "Nội dung trang", "top": 50.0, "bottom": 750.0}]
    finally:
        if textpage is not None:
            try:
                textpage.close()
            except Exception:
                pass


def heading_key(title: str) -> str:
    """Normalize punctuation and numbering without conflating different headings."""
    parts = re.findall(r"[^\W_]+", title.casefold())
    return " ".join(str(int(part)) if part.isdecimal() else part for part in parts)


def find_heading_block(blocks: list[dict], page: int, title: str) -> dict | None:
    matches = [block for block in blocks
               if block["page"] == page and heading_key(block["title"]) == heading_key(title)]
    # Missing/ambiguous matches must never silently become the first card.
    return matches[0] if len(matches) == 1 else None


def _chapters(page_texts: list[str]) -> dict[int, str]:
    names: dict[int, str] = {}
    for page in page_texts:
        for raw in page.splitlines():
            line = " ".join(raw.split()).lstrip("\uf026\uf050 ")
            match = _CHAPTER.match(line)
            if match and not any(0xE000 <= ord(c) <= 0xF8FF for c in match.group(2)):
                names.setdefault(int(match.group(1)), f"Chủ đề {int(match.group(1)):02d} · {match.group(2).strip()}")
    return names


def _detect_chapters_by_page(page_texts: list[str]) -> dict[int, str]:
    page_chapters: dict[int, str] = {}
    current_chapter = "Lý thuyết"
    for page_idx, page in enumerate(page_texts, 1):
        lines = [_clean_line(l) for l in page.splitlines() if l.strip()]
        for i, l in enumerate(lines):
            if _CHAPTER_SOLO.fullmatch(l) and i + 2 < len(lines):
                num_line = lines[i + 1]
                title_line = lines[i + 2]
                if _CHAPTER_NUMBER_SOLO.fullmatch(num_line) and _is_uppercase_vietnamese_heading(title_line):
                    name = _dedup_repeated_banner(title_line)
                    if i + 3 < len(lines) and _is_uppercase_vietnamese_heading(lines[i + 3]):
                        extra = _dedup_repeated_banner(lines[i + 3])
                        if extra != name:
                            name = f"{name} - {extra}"
                    current_chapter = f"Chương {num_line} · {name}"
                    break
            m = re.match(r"^(?:Chủ đề|Chương)\s+(\d+|[IVX]+)\.?\s*(.+)$", l, re.I)
            if m and len(l) <= 120 and not any(0xE000 <= ord(c) <= 0xF8FF for c in l):
                current_chapter = f"Chủ đề {int(m.group(1)):02d} · {m.group(2).strip()}" if m.group(1).isdigit() else l
                break
            rt = parse_roman_topic_heading(l)
            if rt and rt[0] == "I":
                banner = [lines[j] for j in range(max(0, i - 2), i) if _is_uppercase_vietnamese_heading(lines[j])]
                if banner:
                    current_chapter = " ".join(banner)
                    break
        page_chapters[page_idx] = current_chapter
    return page_chapters


def notebook_index(content: bytes, page_texts: list[str]) -> dict:
    digest = sha256(content).hexdigest()
    with _CACHE_LOCK:
        if digest in _NOTEBOOK_INDEX_CACHE:
            _NOTEBOOK_INDEX_CACHE.move_to_end(digest)
            return copy.deepcopy(_NOTEBOOK_INDEX_CACHE[digest])

    with _PDFIUM_LOCK:
        document = _pdf(content)
        try:
            page_count = len(document)
            blocks: list[dict] = []
            for index in range(page_count):
                # A contents page is navigation, not a learning card.
                source_text = page_texts[index] if index < len(page_texts) else ""
                if "mục lục" in source_text.casefold() or source_text.count("......") >= 3:
                    continue
                if index == 0 and len(source_text.strip()) < 400 and page_count > 1:
                    continue
                try:
                    page = document[index]
                    try:
                        blocks.extend(_page_blocks(page, index + 1))
                    finally:
                        try:
                            page.close()
                        except Exception:
                            pass
                except Exception as exc:
                    logger.warning("Error processing page %d for notebook: %s", index + 1, exc)
                    blocks.append({
                        "id": f"p{index + 1}-b0",
                        "page": index + 1,
                        "ordinal": 0,
                        "kind": "CONTINUATION",
                        "title": f"Trang {index + 1}",
                        "top": 50.0,
                        "bottom": 750.0,
                    })
        finally:
            try:
                document.close()
            except Exception:
                pass

    if not blocks:
        raise ApplicationError(422, "NOTEBOOK_EMPTY", "No readable notebook pages were found.")

    chapter_names = _chapters(page_texts)
    page_chapters = _detect_chapters_by_page(page_texts)
    has_methods = any(b["kind"] == "METHOD" for b in blocks)

    sections: list[dict] = []
    current: dict | None = None
    theory_chapter = 0
    for block in blocks:
        new_theory = block["title"].casefold().startswith("a. lý thuyết chung")
        if new_theory:
            theory_chapter += 1
        is_boundary = (
            block["kind"] in ("METHOD", "CHAPTER")
            or (not has_methods and block["kind"] in ("TOPIC", "CHAPTER"))
            or new_theory
            or current is None
        )
        if is_boundary:
            sec_title = block["title"] if block["kind"] in ("METHOD", "TOPIC", "CHAPTER") else "Lý thuyết và ghi nhớ"
            current = {"id": f"section-{len(sections) + 1}",
                       "title": sec_title,
                       "chapter_number": theory_chapter if new_theory else None,
                       "page": block["page"], "blocks": []}
            if block["kind"] == "METHOD":
                match = _METHOD_NUMBER.match(block["title"])
                if match:
                    current["chapter_number"] = int(match.group(1))
            sections.append(current)
        current["blocks"].append({key: block[key] for key in ("id", "page", "ordinal", "kind", "title", "top", "bottom")})

    if has_methods:
        next_number: int | None = None
        for section in reversed(sections):
            if section["chapter_number"] is not None:
                next_number = section["chapter_number"]
            else:
                section["chapter_number"] = next_number
        previous: int | None = None
        for section in sections:
            number = section["chapter_number"] or previous
            section["chapter_number"] = number
            section["chapter_title"] = chapter_names.get(number, f"Chủ đề {number:02d}" if number else "Lý thuyết")
            previous = number
    else:
        for section in sections:
            sec_page = section["blocks"][0]["page"] if section["blocks"] else section.get("page", 1)
            section["chapter_title"] = page_chapters.get(sec_page, "Lý thuyết")

    result = {"sections": sections, "total_blocks": len(blocks), "page_count": page_count}

    with _CACHE_LOCK:
        _NOTEBOOK_INDEX_CACHE[digest] = result
        if len(_NOTEBOOK_INDEX_CACHE) > _MAX_CACHE_ENTRIES:
            _NOTEBOOK_INDEX_CACHE.popitem(last=False)

    return copy.deepcopy(result)


def notebook_image(content: bytes, page_number: int, ordinal: int) -> bytes:
    digest = sha256(content).hexdigest()
    cache_key = (digest, page_number, ordinal)
    with _IMAGE_CACHE_LOCK:
        if cache_key in _NOTEBOOK_IMAGE_CACHE:
            _NOTEBOOK_IMAGE_CACHE.move_to_end(cache_key)
            return _NOTEBOOK_IMAGE_CACHE[cache_key]

    with _PDFIUM_LOCK:
        document = _pdf(content)
        try:
            if not 1 <= page_number <= len(document):
                raise ApplicationError(404, "NOTEBOOK_BLOCK_NOT_FOUND", "Notebook page was not found.")
            page = document[page_number - 1]
            try:
                block = None
                with _CACHE_LOCK:
                    cached_nb = _NOTEBOOK_INDEX_CACHE.get(digest)
                if cached_nb:
                    for sec in cached_nb.get("sections", []):
                        for b in sec.get("blocks", []):
                            if b.get("page") == page_number and b.get("ordinal") == ordinal:
                                block = b
                                break
                        if block:
                            break
                if block is None:
                    blocks = _page_blocks(page, page_number)
                    if 0 <= ordinal < len(blocks):
                        block = blocks[ordinal]
                    else:
                        block = {"top": 50.0, "bottom": page.get_height() - 48.0}
                page_width = max(1.0, page.get_width())
                page_height = max(1.0, page.get_height())
                scale = min(1.8, 1800 / page_width, 2200 / page_height)
                image = page.render(scale=scale, optimize_mode="lcd").to_pil().convert("RGB")
                left = max(0, round(15 * scale))
                right = min(image.width, round((page_width - 15) * scale))
                upper = max(0, min(image.height - 10, round((block["top"] - 8.0) * scale)))
                lower = max(upper + 10, min(image.height, round((block["bottom"] + 4.0) * scale)))
                region = image.crop((left, upper, right, lower))
                output = BytesIO()
                region.save(output, format="PNG")
                image_bytes = output.getvalue()
            finally:
                try:
                    page.close()
                except Exception:
                    pass
        except ApplicationError:
            raise
        except Exception as exc:
            raise ApplicationError(422, "NOTEBOOK_RENDER_FAILED", "Failed to render card image.") from exc
        finally:
            try:
                document.close()
            except Exception:
                pass

    with _IMAGE_CACHE_LOCK:
        _NOTEBOOK_IMAGE_CACHE[cache_key] = image_bytes
        if len(_NOTEBOOK_IMAGE_CACHE) > _MAX_IMAGE_CACHE_ENTRIES:
            _NOTEBOOK_IMAGE_CACHE.popitem(last=False)

    return image_bytes
