"""A source-faithful math notebook made of visual PDF regions.

The math in this PDF uses custom fonts, so text extraction cannot be trusted to
reconstruct formulas. Cards therefore show pixels rendered from the original
page. Recognized headings only supply navigation and card labels.
"""

from io import BytesIO
import re

from app.core.exceptions import ApplicationError
from app.theory_maps.pdf_extraction import MAX_PAGES

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
    height = page.get_height()
    textpage = page.get_textpage()
    text = textpage.get_text_range(0, textpage.count_chars())
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
    document = _pdf(content)
    blocks: list[dict] = []
    for index in range(len(document)):
        # A contents page is navigation, not a learning card.
        source_text = page_texts[index] if index < len(page_texts) else ""
        if "mục lục" in source_text.casefold() or source_text.count("......") >= 3:
            continue
        if index == 0 and len(source_text.strip()) < 400 and len(document) > 1:
            continue
        blocks.extend(_page_blocks(document[index], index + 1))
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
    return {"sections": sections, "total_blocks": len(blocks), "page_count": len(document)}


def notebook_image(content: bytes, page_number: int, ordinal: int) -> bytes:
    document = _pdf(content)
    if not 1 <= page_number <= len(document):
        raise ApplicationError(404, "NOTEBOOK_BLOCK_NOT_FOUND", "Notebook page was not found.")
    page = document[page_number - 1]
    blocks = _page_blocks(page, page_number)
    if not 0 <= ordinal < len(blocks):
        raise ApplicationError(404, "NOTEBOOK_BLOCK_NOT_FOUND", "Notebook card was not found.")
    block = blocks[ordinal]
    scale = min(1.8, 1800 / page.get_width(), 2200 / page.get_height())
    image = page.render(scale=scale, optimize_mode="lcd").to_pil().convert("RGB")
    left = round(20 * scale)
    right = round((page.get_width() - 20) * scale)
    upper = round(block["top"] * scale)
    lower = round(block["bottom"] * scale)
    region = image.crop((left, upper, right, lower))
    output = BytesIO()
    region.save(output, format="PNG", optimize=True)
    return output.getvalue()
