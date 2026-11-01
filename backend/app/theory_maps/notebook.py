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
from app.theory_maps.pdf_extraction import MAX_PAGES

logger = logging.getLogger(__name__)

# Process-level thread lock for PDFium operations because the underlying
# PDFium C library maintains global state that is not thread-safe.
_PDFIUM_LOCK = threading.Lock()

# Thread-safe LRU cache for notebook index dictionaries keyed by SHA-256 hash.
_NOTEBOOK_INDEX_CACHE: OrderedDict[str, dict] = OrderedDict()
_MAX_CACHE_ENTRIES = 32
_CACHE_LOCK = threading.Lock()


_ANCHOR = re.compile(
    r"(?im)^[ \t\uf000-\uf8ff]*(?P<title>"
    r"A\.\s+LÝ THUYẾT CHUNG\.?|"
    r"Dạng\s+\d+\.\d+\.?[^\r\n]{0,150}|"
    r"Bước\s+\d{1,2}\.?|"
    r"Ví dụ\s+\d+(?:\.\d+)*\.?[^\r\n]{0,100}|"
    r"(?:Định nghĩa|Định l[ýí]|Tính chất|Hệ quả|Nhận xét|Chú ý|Ghi nhớ|Lưu ý)\s*\d*\.?|"
    r"(?:Example|Theorem|Definition)\s*\d*\.?"
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
    try:
        height = page.get_height()
        textpage = page.get_textpage()
        char_count = textpage.count_chars()
        text = textpage.get_text_range(0, char_count) if char_count > 0 else ""
    except Exception as exc:
        logger.warning("Error getting textpage for page %d: %s", page_number, exc)
        return [{"id": f"p{page_number}-b0", "page": page_number, "ordinal": 0,
                 "kind": "CONTINUATION", "title": "Nội dung trang", "top": 50.0, "bottom": 750.0}]

    anchors: list[tuple[float, str, str]] = []
    for match in _ANCHOR.finditer(text):
        title = " ".join(match.group("title").split()).strip(" .")
        if not title or "\ufffd" in title or _DOT_LEADER.search(title) or any(0xE000 <= ord(c) <= 0xF8FF for c in title):
            continue
        try:
            top = height - textpage.get_charbox(match.start("title"))[3]
        except Exception:
            continue
        if not 48 <= top <= height - 52:
            continue
        lower = title.casefold()
        kind = ("METHOD" if lower.startswith("dạng ") else
                "EXAMPLE" if lower.startswith(("ví dụ", "example")) else
                "STEP" if lower.startswith("bước ") else
                "NOTE" if lower.startswith(("nhận xét", "chú ý", "ghi nhớ", "lưu ý")) else "THEORY")
        if anchors and top - anchors[-1][0] < 18:
            continue
        anchors.append((top, title, kind))
    anchors.sort(key=lambda entry: entry[0])
    blocks: list[dict] = []
    content_top, content_bottom = 50.0, height - 48.0
    if not anchors:
        return [{"id": f"p{page_number}-b0", "page": page_number, "ordinal": 0,
                 "kind": "CONTINUATION", "title": "Nội dung trang", "top": content_top, "bottom": content_bottom}]
    if anchors[0][0] > 195:
        blocks.append({"id": f"p{page_number}-b0", "page": page_number, "ordinal": 0,
                       "kind": "CONTINUATION", "title": "Tiếp theo", "top": content_top,
                       "bottom": anchors[0][0] + 2})
    for index, (top, title, kind) in enumerate(anchors):
        start = content_top if index == 0 and not blocks else max(content_top, top - (4 if kind == "STEP" else 12))
        end = (anchors[index + 1][0] - (4 if kind == "STEP" else -2)) if index + 1 < len(anchors) else content_bottom
        if end - start < 18:
            continue
        blocks.append({"id": f"p{page_number}-b{len(blocks)}", "page": page_number,
                       "ordinal": len(blocks), "kind": kind, "title": title,
                       "top": round(start, 2), "bottom": round(min(end, content_bottom), 2)})
    return blocks or [{"id": f"p{page_number}-b0", "page": page_number, "ordinal": 0,
                       "kind": "CONTINUATION", "title": "Nội dung trang", "top": content_top, "bottom": content_bottom}]


def _chapters(page_texts: list[str]) -> dict[int, str]:
    names: dict[int, str] = {}
    for page in page_texts:
        for raw in page.splitlines():
            line = " ".join(raw.split()).lstrip("\uf026\uf050 ")
            match = _CHAPTER.match(line)
            if match and not any(0xE000 <= ord(c) <= 0xF8FF for c in match.group(2)):
                names.setdefault(int(match.group(1)), f"Chủ đề {int(match.group(1)):02d} · {match.group(2).strip()}")
    return names


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
                    blocks.extend(_page_blocks(page, index + 1))
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
    sections: list[dict] = []
    current: dict | None = None
    theory_chapter = 0
    for block in blocks:
        new_theory = block["title"].casefold().startswith("a. lý thuyết chung")
        if new_theory:
            theory_chapter += 1
        if block["kind"] == "METHOD" or new_theory or current is None:
            current = {"id": f"section-{len(sections) + 1}",
                       "title": block["title"] if block["kind"] == "METHOD" else "Lý thuyết và ghi nhớ",
                       "chapter_number": theory_chapter if new_theory else None, "blocks": []}
            if block["kind"] == "METHOD":
                match = _METHOD_NUMBER.match(block["title"])
                if match:
                    current["chapter_number"] = int(match.group(1))
            sections.append(current)
        current["blocks"].append({key: block[key] for key in ("id", "page", "ordinal", "kind", "title")})
    # Theory before each first exercise type belongs to that source-numbered topic.
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

    result = {"sections": sections, "total_blocks": len(blocks), "page_count": page_count}

    with _CACHE_LOCK:
        _NOTEBOOK_INDEX_CACHE[digest] = result
        if len(_NOTEBOOK_INDEX_CACHE) > _MAX_CACHE_ENTRIES:
            _NOTEBOOK_INDEX_CACHE.popitem(last=False)

    return copy.deepcopy(result)


def notebook_image(content: bytes, page_number: int, ordinal: int) -> bytes:
    with _PDFIUM_LOCK:
        document = _pdf(content)
        try:
            if not 1 <= page_number <= len(document):
                raise ApplicationError(404, "NOTEBOOK_BLOCK_NOT_FOUND", "Notebook page was not found.")
            page = document[page_number - 1]
            blocks = _page_blocks(page, page_number)
            if not 0 <= ordinal < len(blocks):
                raise ApplicationError(404, "NOTEBOOK_BLOCK_NOT_FOUND", "Notebook card was not found.")
            block = blocks[ordinal]
            page_width = max(1.0, page.get_width())
            page_height = max(1.0, page.get_height())
            scale = min(1.8, 1800 / page_width, 2200 / page_height)
            image = page.render(scale=scale, optimize_mode="lcd").to_pil().convert("RGB")
            left = max(0, round(20 * scale))
            right = min(image.width, round((page_width - 20) * scale))
            upper = max(0, min(image.height - 10, round(block["top"] * scale)))
            lower = max(upper + 10, min(image.height, round(block["bottom"] * scale)))
            region = image.crop((left, upper, right, lower))
            output = BytesIO()
            region.save(output, format="PNG", optimize=True)
            return output.getvalue()
        except ApplicationError:
            raise
        except Exception as exc:
            raise ApplicationError(422, "NOTEBOOK_RENDER_FAILED", "Failed to render card image.") from exc
        finally:
            try:
                document.close()
            except Exception:
                pass
