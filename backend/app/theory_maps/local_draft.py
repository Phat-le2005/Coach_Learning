"""Conservative, source-cited outline of a PDF's *headings*.

PDF font encodings can corrupt mathematics. Never turn arbitrary extracted
paragraphs or glyphs into alleged definitions, theorems, or formulas.
"""

import re

from app.core.exceptions import ApplicationError
from app.theory_maps.schemas import NodeKind, TheoryLearningStep, TheoryNode

MAX_DRAFT_NODES = 400

_CHAPTER = re.compile(r"^(?:Chủ đề|Chương|Bài|Phần)\s+(?P<number>\d+|[IVX]+)\.?\s*(?P<name>.+)$", re.I)
_TOPIC = re.compile(r"^Dạng\s+(?P<chapter>\d+)\.(?P<topic>\d+)\.?\s+\S", re.I)
_PART = re.compile(r"^(?P<part>[AB])\.\s+(?:LÝ THUYẾT(?: CHUNG)?|CÁC DẠNG BÀI TẬP)\.?$", re.I)
_THEORY_PREFIX = re.compile(
    r"^(?:Định nghĩa|Định lí|Định lý|Tính chất|Hệ quả|Nhận xét|Chú ý|Ghi nhớ|Lưu ý)"
    r"(?=\s|[.:]|$)", re.I,
)
_THEORY_HEADING = re.compile(
    r"^(?:Định nghĩa|Định lí|Định lý|Tính chất|Hệ quả|Nhận xét|Chú ý|Ghi nhớ|Lưu ý)"
    r"(?:\s+\d+)?[.:]?$", re.I,
)
_EXAMPLE_HEADING = re.compile(r"^Ví dụ(?:\s+\d+(?:\.\d+)*)?[.:]?$", re.I)
_NUMBERED = re.compile(r"^(?P<number>\d+(?:\.\d+)*)[.)]\s+(?P<name>.+)$")
_EQUATION = re.compile(r"^[A-Za-z0-9\\{}()[\]^_+*/=.,:<>|\s'\-]+$")
_DOT_LEADER = re.compile(r"\.{5,}\s*\d*\s*$")
_STEP = re.compile(r"^Bước\s+0?(?P<number>\d{1,2})\s*[.:]\s*(?P<instruction>.+)$", re.I)


def needs_reviewed_body(title: str) -> bool:
    return bool(_THEORY_PREFIX.match(title))


def _clean_line(raw: str) -> str:
    """Remove only decorative leading glyphs; never guess an internal symbol."""
    value = raw.strip()
    while value and (0xE000 <= ord(value[0]) <= 0xF8FF or value[0] in "•●▪"):
        value = value[1:].lstrip()
    return " ".join(value.split())


def _reliable(value: str) -> bool:
    return bool(value) and "\ufffd" not in value and not any(
        0xE000 <= ord(character) <= 0xF8FF for character in value
    )


def _is_contents_page(page: str) -> bool:
    lines = page.splitlines()
    return any(_clean_line(line).casefold() == "mục lục" for line in lines) or sum(
        bool(_DOT_LEADER.search(line)) for line in lines
    ) >= 3


def source_page_outline(page_texts: list[str]) -> list[dict[str, str | int]]:
    """Use only exact, reliable source headings as PDF page links, never as lessons."""
    entries: list[dict[str, str | int]] = []
    seen: set[str] = set()
    for page_number, page in enumerate(page_texts, 1):
        if _is_contents_page(page):
            continue
        for raw in page.splitlines():
            title = _clean_line(raw)
            if not _reliable(title) or len(title) > 160 or _DOT_LEADER.search(title):
                continue
            kind = "CHAPTER" if _CHAPTER.fullmatch(title) else "EXERCISE_TYPE" if _TOPIC.match(title) else None
            if kind is None or title.casefold() in seen:
                continue
            seen.add(title.casefold())
            entries.append({"title": title, "source_page": page_number, "kind": kind})
            if len(entries) >= 80:
                return entries
    return entries


def prefill_source_steps(nodes: list[TheoryNode], page_texts: list[str]) -> list[TheoryNode]:
    """Copy unambiguous numbered steps; mark broken text for teacher correction.

    Broken math is never guessed. A dangling phrase gets a visible placeholder
    and cannot be published until a teacher fixes it. A restarted numbering
    sequence is ambiguous, so it is not copied. Teacher content is preserved.
    """
    topics = {(node.source_page, node.title): node for node in nodes if _TOPIC.match(node.title)}
    candidates: dict[str, list[tuple[int, TheoryLearningStep] | None]] = {}
    active: TheoryNode | None = None
    for page_number, page in enumerate(page_texts, 1):
        if _is_contents_page(page):
            continue
        for raw in page.splitlines():
            line = _clean_line(raw)
            if _TOPIC.match(line):
                active = topics.get((page_number, line))
                continue
            if _CHAPTER.fullmatch(line) or _PART.fullmatch(line) or _EXAMPLE_HEADING.fullmatch(line):
                active = None
                continue
            if active is None:
                continue
            match = _STEP.fullmatch(line)
            if not match:
                continue
            number = int(match.group("number"))
            instruction = match.group("instruction").strip()
            # A colon, dangling phrase or private-use math glyph usually means
            # that the rest of the instruction lives on another PDF text line.
            complete = (
                _reliable(instruction) and 8 <= len(instruction) <= 500
                and instruction.endswith((".", "!", "?"))
                and not instruction.endswith(("...", ".."))
            )
            if not complete:
                prefix = instruction.split(next((char for char in instruction
                    if 0xE000 <= ord(char) <= 0xF8FF), "\ufffd"), 1)[0]
                prefix = prefix.rstrip(" .:;,!?-").strip()
                instruction = f"{prefix} □" if 4 <= len(prefix) <= 498 and _reliable(prefix) else ""
            candidates.setdefault(active.id, []).append((number, TheoryLearningStep(
                instruction=instruction, source_page=page_number,
                source_quote=raw.strip()[:500],
            )) if instruction else None)

    for node in nodes:
        if node.reviewed or node.learning_steps:
            continue
        entries = candidates.get(node.id, [])
        if not entries or len(entries) > 12 or any(entry is None for entry in entries):
            continue
        numbered = [entry for entry in entries if entry is not None]
        if [number for number, _ in numbered] != list(range(1, len(numbered) + 1)):
            continue
        node.learning_steps = [step for _, step in numbered]
    return nodes


def build_local_draft(title: str, page_texts: list[str]) -> list[TheoryNode]:
    if not page_texts or not any(page.strip() for page in page_texts):
        raise ApplicationError(422, "PDF_TEXT_REQUIRED", "A local draft needs source text.")

    # A contents page may name chapters that decorative PDF fonts omit on
    # content pages. It can supply chapter titles, never theorem content.
    contents_pages = {index for index, page in enumerate(page_texts, 1) if _is_contents_page(page)}
    chapter_sources: dict[int, tuple[str, int]] = {}
    chapter_order: list[int] = []
    for page_number in sorted(contents_pages):
        for raw in page_texts[page_number - 1].splitlines():
            line = _clean_line(raw)
            match = _CHAPTER.fullmatch(line)
            if match and _reliable(line) and match.group("number").isdigit():
                number = int(match.group("number"))
                if number not in chapter_sources:
                    chapter_sources[number] = (line, page_number)
                    chapter_order.append(number)

    first_source = next(
        ((line, page_number) for page_number, page in enumerate(page_texts, 1)
         for raw in page.splitlines() if (line := _clean_line(raw)) and _reliable(line)
         and not _DOT_LEADER.search(line) and len(line) <= 250),
        None,
    )
    if first_source is None:
        raise ApplicationError(422, "LOCAL_MAP_NO_RELIABLE_TEXT",
                               "No reliable text heading was found; check the original PDF.")
    if chapter_order:
        first_source = chapter_sources[chapter_order[0]]
    root_quote, root_page = first_source
    nodes = [TheoryNode(id="n0", kind=NodeKind.ROOT, title=title,
                        source_page=root_page, source_quote=root_quote[:500])]
    chapter_ids: dict[int, str] = {}
    chapter_cursor = 0
    current_chapter = "n0"
    current_part = "n0"
    part_kind: str | None = None
    numbered_sections: dict[int, tuple[str, str]] = {}

    def append(kind: NodeKind, heading: str, page: int, parent: str,
               latex: str | None = None, quote: str | None = None) -> str:
        if len(nodes) >= MAX_DRAFT_NODES:
            raise ApplicationError(422, "LOCAL_MAP_TOO_LARGE",
                                   "The PDF has too many headings for one draft; split it into smaller PDFs.")
        node_id = f"n{len(nodes)}"
        nodes.append(TheoryNode(id=node_id, parent_id=parent, kind=kind,
                                title=heading[:250], source_page=page,
                                source_quote=(quote or heading)[:500], latex=latex, reviewed=False))
        return node_id

    def use_chapter(number: int, fallback: tuple[str, int] | None = None) -> str:
        source = chapter_sources.get(number, fallback)
        if source is None:
            return "n0"  # Do not invent a chapter absent from source text.
        if number not in chapter_ids:
            chapter_ids[number] = append(NodeKind.SECTION, source[0], source[1], "n0")
        return chapter_ids[number]

    for page_number, page in enumerate(page_texts, 1):
        if page_number in contents_pages:
            continue
        page_has_font_glyphs = any(0xE000 <= ord(char) <= 0xF8FF for char in page)
        lines = page.splitlines()
        for position, raw in enumerate(lines):
            line = _clean_line(raw)
            if not _reliable(line) or len(line) > 250:
                continue

            chapter = _CHAPTER.fullmatch(line)
            if chapter and len(line) <= 160:
                if part_kind == "B" and line.casefold().startswith("bài "):
                    continue  # An exercise is not a new chapter.
                number = chapter.group("number")
                if number.isdigit():
                    current_chapter = use_chapter(int(number), (line, page_number))
                    if int(number) in chapter_order:
                        chapter_cursor = max(chapter_cursor, chapter_order.index(int(number)) + 1)
                else:
                    current_chapter = append(NodeKind.SECTION, line, page_number, "n0")
                current_part, part_kind = current_chapter, None
                numbered_sections.clear()
                continue

            part = _PART.fullmatch(line)
            if part:
                kind = part.group("part").upper()
                if kind == "A" and chapter_cursor < len(chapter_order):
                    current_chapter = use_chapter(chapter_order[chapter_cursor])
                    chapter_cursor += 1
                current_part = append(NodeKind.SECTION, line, page_number, current_chapter)
                part_kind = kind
                numbered_sections.clear()
                continue

            topic = _TOPIC.match(line)
            if topic and len(line) <= 160:
                chapter_number = int(topic.group("chapter"))
                if chapter_number in chapter_sources:
                    current_chapter = use_chapter(chapter_number)
                parent = current_part if part_kind == "B" and current_part != "n0" else current_chapter
                append(NodeKind.SECTION, line, page_number, parent)
                # A PDF may draw the B heading as shapes and omit it from its
                # text layer. A numbered exercise type still ends theory mode.
                part_kind = "B"
                current_part = parent
                continue

            # Definitions and theorems are siblings. Never attach following
            # paragraphs, examples, or answer choices as their content.
            if part_kind != "B" and _THEORY_HEADING.fullmatch(line) and len(line) <= 100:
                parent = numbered_sections[max(numbered_sections)][1] if numbered_sections else current_part
                next_line = _clean_line(lines[position + 1]) if position + 1 < len(lines) else ""
                if line.endswith(".") and next_line.isdigit() and len(next_line) <= 3:
                    append(NodeKind.SECTION, f"{line[:-1]} {next_line}", page_number, parent,
                           quote=f"{line} {next_line}")
                else:
                    append(NodeKind.SECTION, line, page_number, parent)
                continue

            numbered = _NUMBERED.fullmatch(line)
            if part_kind != "B" and numbered and len(line) <= 100 and len(numbered.group("name").split()) <= 8:
                section_number = numbered.group("number")
                depth = section_number.count(".") + 1
                parent = current_part
                for ancestor_depth in range(depth - 1, 0, -1):
                    ancestor = numbered_sections.get(ancestor_depth)
                    if ancestor and section_number.startswith(ancestor[0] + "."):
                        parent = ancestor[1]
                        break
                numbered_sections[depth] = (section_number, append(NodeKind.SECTION, line, page_number, parent))
                for deeper in list(numbered_sections):
                    if deeper > depth:
                        del numbered_sections[deeper]
                continue

            if part_kind != "B" and _EXAMPLE_HEADING.fullmatch(line) and len(line) <= 100:
                parent = numbered_sections[max(numbered_sections)][1] if numbered_sections else current_part
                append(NodeKind.EXAMPLE, line, page_number, parent)
                continue

            # A formula is only copied when the *whole page* has no PDF font
            # glyphs and the source line is already plain TeX-compatible text.
            if part_kind != "B" and not page_has_font_glyphs and len(line) <= 120 and "=" in line and _EQUATION.fullmatch(line):
                append(NodeKind.FORMULA, line, page_number, current_part, latex=line)

    if len(nodes) == 1:
        # A plain short note has no headings; keep one cited text line so the
        # teacher can still create the map, without inventing content.
        line, page_number = first_source
        append(NodeKind.CONCEPT, line[:120], page_number, "n0")
    return prefill_source_steps(nodes, page_texts)
