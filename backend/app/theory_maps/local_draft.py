"""Conservative, source-cited outline of a PDF's *headings*.

PDF font encodings can corrupt mathematics. Never turn arbitrary extracted
paragraphs or glyphs into alleged definitions, theorems, or formulas.
"""

import re

from app.core.exceptions import ApplicationError
from app.theory_maps.schemas import NodeKind, TheoryLearningStep, TheoryNode

MAX_DRAFT_NODES = 400

_LEADING_DECORATION = "•●▪▫◦‣⁃→⇒➔➜➡»«➢➣➤▸▶☞❖✦✧★☆"
_CHAPTER = re.compile(
    r"^(?:Chủ đề|Chương|Chuyên đề|Bài|Phần)\s+(?P<number>\d+|[IVX]+)(?:[.:]\s*|\s+[·\-]\s*|\s+)(?P<name>.+)$",
    re.I,
)
_CHAPTER_SOLO = re.compile(r"^(?:Chủ đề|Chương|Chuyên đề|Phần)$", re.I)
_CHAPTER_NUMBER_SOLO = re.compile(r"^(?:\d{1,2}|[IVX]{1,5})$")
_TOPIC = re.compile(r"^(?:Dạng\s+(?P<chapter>\d+)\.(?P<topic>\d+)\.?\s+\S|(?:(?P<num>\d+)\.\s+)?Bài toán\s+\d+\b)", re.I)
_PART = re.compile(r"^(?P<part>[AB])\.\s+(?:LÝ THUYẾT(?: CHUNG)?|CÁC DẠNG BÀI TẬP)\.?$", re.I)
_THEORY_PREFIX = re.compile(
    r"^(?:Định nghĩa|Định lí|Định lý|Tính chất|Hệ quả|Nhận xét|Chú ý|Ghi nhớ|Lưu ý)"
    r"(?=\s|[.:]|$)", re.I,
)
_THEORY_HEADING = re.compile(
    r"^(?:Định nghĩa|Định lí|Định lý|Tính chất|Hệ quả|Nhận xét|Chú ý|Ghi nhớ|Lưu ý|Ý nghĩa)"
    r"(?:\s+\d+)?[.:]?$", re.I,
)
_EXAMPLE_HEADING = re.compile(r"^Ví dụ(?:\s+\d+(?:\.\d+)*)?[.:]?$", re.I)
_NUMBERED = re.compile(
    r"^(?P<number>\d+(?:\.\d+)+[.)]?|\d+[.)])\s+(?P<name>[^\W\d_].*)$"
)
_EQUATION = re.compile(r"^[A-Za-z0-9\\{}()[\]^_+*/=.,:<>|\s'\-]+$")
_DOT_LEADER = re.compile(r"\.{5,}\s*\d*\s*$")
_STEP = re.compile(r"^Bước\s+0?(?P<number>\d{1,2})(?:\s*[.:]\s*|\s+)(?P<instruction>.+)$", re.I)

_ROMAN_PREFIX = re.compile(
    r"^(?P<roman>I|II|III|IV|V|VI|VII|VIII|IX|X)(?:[.:)\s]+)\s*(?P<name>.+)$"
)
_ROMAN_SUFFIX_MULTI = re.compile(
    r"^(?P<name>.+?)\s*(?P<roman>II|III|IV|V|VI|VII|VIII|IX|X)$"
)
_ROMAN_SUFFIX_SINGLE_I = re.compile(
    r"^(?P<name>.+[BCDĐGHKLMNPQRSTVXỊÌÍỈĨ\s])(?P<roman>I)$"
)
_IGNORED_UPPER_PREFIXES = (
    "TRANG ",
    "BƯỚC ",
    "CÁCH ",
    "TỔ TOÁN",
    "BẢN ĐỒ",
    "CHƯƠNG",
    "CHỦ ĐỀ",
    "CHUYÊN ĐỀ",
    "PHẦN",
)
_TRIVIAL_GRAPH_LABELS = {
    "y=f(x)",
    "y=g(x)",
    "y=h(x)",
    "y=ƒ(x)",
    "x=x0",
    "y=y0",
    "x=a",
    "x=b",
    "x=c",
    "x=0",
    "y=0",
}


def needs_reviewed_body(title: str) -> bool:
    return bool(_THEORY_PREFIX.match(title))


def _clean_line(raw: str) -> str:
    """Remove only decorative leading glyphs; never guess an internal symbol."""
    value = raw.strip()
    while value and (0xE000 <= ord(value[0]) <= 0xF8FF or value[0] in _LEADING_DECORATION):
        value = value[1:].lstrip()
    return " ".join(value.split())


def _reliable(value: str) -> bool:
    return bool(value) and "\ufffd" not in value and not any(
        0xE000 <= ord(character) <= 0xF8FF for character in value
    )


def _dedup_repeated_banner(text: str) -> str:
    cleaned = " ".join(text.split()).strip()
    half = len(cleaned) // 2
    if len(cleaned) >= 8 and len(cleaned) % 2 == 0 and cleaned[:half] == cleaned[half:]:
        return cleaned[:half].strip()
    return cleaned


def _has_vietnamese_diacritic(text: str) -> bool:
    return any(ord(char) > 127 and char.isalpha() for char in text)


def _is_uppercase_vietnamese_heading(text: str) -> bool:
    cleaned = _dedup_repeated_banner(text)
    if len(cleaned) < 3 or len(cleaned) > 140:
        return False
    if cleaned != cleaned.upper() or not _has_vietnamese_diacritic(cleaned):
        return False
    if any(op in cleaned for op in ("=", "≠", "<", ">", "≤", "≥", "⊂", "∈", "∫", "→")):
        return False
    if cleaned.startswith(_IGNORED_UPPER_PREFIXES) or "|" in cleaned:
        return False
    return True


def parse_roman_topic_heading(line: str) -> tuple[str, str] | None:
    """Detect uppercase topic banners with a leading or trailing Roman numeral."""
    cleaned = _clean_line(line)
    if not _reliable(cleaned) or len(cleaned) > 160:
        return None
    for pattern in (_ROMAN_SUFFIX_MULTI, _ROMAN_SUFFIX_SINGLE_I, _ROMAN_PREFIX):
        match = pattern.fullmatch(cleaned)
        if match:
            roman = match.group("roman").strip()
            name = _dedup_repeated_banner(match.group("name").strip(" .:-"))
            if _is_uppercase_vietnamese_heading(name):
                return roman, f"{roman}. {name}"
    return None


def _clean_numbered_heading(line: str) -> tuple[str, str] | None:
    """Validate and clean a numbered section heading, returning (section_number, clean_title)."""
    match = _NUMBERED.fullmatch(line)
    if not match:
        return None
    section_number = match.group("number").rstrip(".)")
    name = match.group("name").strip()
    # Strip trailing garbled math fragments after a closing parenthesis like "(c ≠ 0)ax by cx d"
    name = re.sub(r"\)[a-zA-Z0-9\s+\-=*/',;]+$", ")", name).strip()
    # Reject inline theory notes or examples disguised as numbered lines
    if name.casefold().startswith(("nhận xét:", "lưu ý:", "chú ý:", "ví dụ")):
        return None
    words = name.split()
    if not words or len(words) > 18:
        return None
    # Reject lines that are pure equations or numeric tables
    if sum(any(ch.isalpha() for ch in w) for w in words) < min(2, len(words)):
        return None
    prefix = f"{section_number}." if not match.group("number").endswith(")") else f"{section_number})"
    return section_number, f"{prefix} {name}"


def _is_meaningful_formula(line: str) -> bool:
    """Filter out graph axis labels, dangling equation fragments, and non-math glyphs."""
    if len(line) > 120 or "=" not in line or not _EQUATION.fullmatch(line):
        return False
    stripped = line.strip()
    if stripped.endswith("=") or stripped.startswith("="):
        return False
    lhs, _, rhs = stripped.partition("=")
    lhs_s, rhs_s = lhs.strip(), rhs.strip()
    if not any(c.isalnum() for c in lhs_s) or not any(c.isalnum() for c in rhs_s):
        return False
    if lhs_s.casefold() in ("dx", "du", "dt", "dy"):
        return False
    if re.search(r"\bS\d+\b", stripped):
        return False
    if stripped.count("=") > 1 and not any(
        tok in stripped for tok in ("lim", "+", "-", "*", "/", "<", ">", "^")
    ):
        return False
    compact = re.sub(r"\s+", "", stripped).casefold()
    if compact in _TRIVIAL_GRAPH_LABELS:
        return False
    if re.fullmatch(r"[xy]=[xyabc01]\d*", compact):
        return False
    # Reject graph curve labels like "H My = f(x)", "y y = f(x)", "y = f(x)y = g(x)"
    if ("f(x)" in compact or "g(x)" in compact) and not any(
        token in stripped for token in ("'", "+", "-", "*", "/", "^", "lim", "sin", "cos", "ln", "log")
    ):
        return False
    # Reject lines with multiple disconnected uppercase point labels before an equation
    if re.match(r"^[A-Z]\s+[A-Z][a-z]\s*=", stripped):
        return False
    return True


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
        lines = [_clean_line(raw) for raw in page.splitlines()]
        idx = 0
        while idx < len(lines):
            title = lines[idx]
            if not _reliable(title) or len(title) > 160 or _DOT_LEADER.search(title):
                idx += 1
                continue
            if (
                _CHAPTER_SOLO.fullmatch(title)
                and idx + 2 < len(lines)
                and _CHAPTER_NUMBER_SOLO.fullmatch(lines[idx + 1])
                and _is_uppercase_vietnamese_heading(lines[idx + 2])
            ):
                num = lines[idx + 1]
                chap_name = _dedup_repeated_banner(lines[idx + 2])
                if idx + 3 < len(lines) and _is_uppercase_vietnamese_heading(lines[idx + 3]):
                    extra = _dedup_repeated_banner(lines[idx + 3])
                    if extra != chap_name:
                        chap_name = f"{chap_name} - {extra}"
                combined = f"Chương {num}. {chap_name}"
                if combined.casefold() not in seen:
                    seen.add(combined.casefold())
                    entries.append({"title": combined, "source_page": page_number, "kind": "CHAPTER"})
                idx += 3
                continue
            roman_topic = parse_roman_topic_heading(title)
            kind = (
                "CHAPTER"
                if _CHAPTER.fullmatch(title) or roman_topic is not None
                else "EXERCISE_TYPE"
                if _TOPIC.match(title)
                else None
            )
            display_title = roman_topic[1] if roman_topic else title
            if kind is not None and display_title.casefold() not in seen:
                seen.add(display_title.casefold())
                entries.append({"title": display_title, "source_page": page_number, "kind": kind})
                if len(entries) >= 80:
                    return entries
            idx += 1
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


def _normalize_heading_key(text: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", text.casefold()))


def _extract_page_events(lines: list[str], current_chapter_title: str) -> list[dict]:
    """Parse raw page lines into structured heading events and fix PDF z-order anomalies."""
    events: list[dict] = []
    consumed: set[int] = set()

    # Pass 1: Look for explicit multi-line chapter cover banners (e.g. "CHƯƠNG\n4\nCÔNG THỨC...")
    for idx, raw in enumerate(lines):
        if idx in consumed:
            continue
        line = _clean_line(raw)
        if not _reliable(line):
            continue
        if _CHAPTER_SOLO.fullmatch(line) and idx + 2 < len(lines):
            num_line = _clean_line(lines[idx + 1])
            title_line = _clean_line(lines[idx + 2])
            if _CHAPTER_NUMBER_SOLO.fullmatch(num_line) and _is_uppercase_vietnamese_heading(title_line):
                consumed.update({idx, idx + 1, idx + 2})
                chap_name = _dedup_repeated_banner(title_line)
                quote = lines[idx + 2].strip()
                if idx + 3 < len(lines):
                    next_title = _clean_line(lines[idx + 3])
                    if (
                        _is_uppercase_vietnamese_heading(next_title)
                        and parse_roman_topic_heading(next_title) is None
                    ):
                        consumed.add(idx + 3)
                        extra = _dedup_repeated_banner(next_title)
                        if extra != chap_name:
                            chap_name = f"{chap_name} - {extra}"
                # Consume any duplicate shadow lines immediately following
                for lookahead in range(idx + 3, min(idx + 7, len(lines))):
                    cand = _dedup_repeated_banner(_clean_line(lines[lookahead]))
                    if cand and cand in chap_name:
                        consumed.add(lookahead)
                events.append({
                    "type": "MULTILINE_CHAPTER",
                    "number": int(num_line) if num_line.isdigit() else None,
                    "title": f"{line.title()} {num_line}. {chap_name}",
                    "quote": quote,
                    "pos": idx,
                })

    # Pass 2: Look for implicit chapter banners on pages that start Roman Topic "I."
    has_roman_one = any(
        idx not in consumed
        and (rt := parse_roman_topic_heading(_clean_line(raw))) is not None
        and rt[0] == "I"
        for idx, raw in enumerate(lines)
    )
    if has_roman_one and not any(e["type"] == "MULTILINE_CHAPTER" for e in events):
        banner_indices: list[int] = []
        banner_parts: list[str] = []
        for idx, raw in enumerate(lines):
            if idx in consumed:
                continue
            line = _clean_line(raw)
            if parse_roman_topic_heading(line) is not None:
                continue
            if _is_uppercase_vietnamese_heading(line):
                dedup = _dedup_repeated_banner(line)
                if dedup not in banner_parts:
                    banner_parts.append(dedup)
                banner_indices.append(idx)
                if len(banner_parts) >= 2:
                    break
        if banner_parts:
            combined_banner = " ".join(banner_parts)
            # If the banner is just a single word prefix of the Roman I topic (e.g. "VECTƠ" before
            # "I. VECTƠ VÀ HỆ TRỤC TỌA ĐỘ TRONG KHÔNG GIAN"), use the Roman I topic name for the chapter.
            roman_one_name = next(
                parse_roman_topic_heading(_clean_line(raw))[1].partition(". ")[2]
                for idx, raw in enumerate(lines)
                if idx not in consumed
                and (rt := parse_roman_topic_heading(_clean_line(raw))) is not None
                and rt[0] == "I"
            )
            if len(combined_banner.split()) <= 2 and roman_one_name.startswith(combined_banner):
                combined_banner = roman_one_name
            consumed.update(banner_indices)
            if _normalize_heading_key(combined_banner) not in _normalize_heading_key(current_chapter_title):
                events.append({
                    "type": "IMPLICIT_CHAPTER",
                    "title": combined_banner,
                    "quote": lines[banner_indices[0]].strip(),
                    "pos": -1,
                })

    # Pass 3: Collect remaining line events
    for idx, raw in enumerate(lines):
        if idx in consumed:
            continue
        line = _clean_line(raw)
        if not _reliable(line) or len(line) > 250:
            continue
        roman_topic = parse_roman_topic_heading(line)
        if roman_topic is not None:
            events.append({
                "type": "ROMAN_TOPIC",
                "roman": roman_topic[0],
                "title": roman_topic[1],
                "quote": raw.strip(),
                "pos": idx,
            })
            continue
        events.append({
            "type": "LINE",
            "line": line,
            "raw": raw,
            "pos": idx,
        })

    # Fix PDF stream z-order anomaly 1: If a ROMAN_TOPIC appears immediately after a "1. ..."
    # numbered heading on the same page, move the ROMAN_TOPIC before that "1. ..." heading.
    first_num_one_idx = next(
        (
            i for i, ev in enumerate(events)
            if ev["type"] == "LINE"
            and (num := _clean_numbered_heading(ev["line"])) is not None
            and num[0] == "1"
        ),
        None,
    )
    roman_idx = next((i for i, ev in enumerate(events) if ev["type"] == "ROMAN_TOPIC"), None)
    if first_num_one_idx is not None and roman_idx is not None and roman_idx > first_num_one_idx:
        roman_ev = events.pop(roman_idx)
        events.insert(first_num_one_idx, roman_ev)

    # Fix PDF stream z-order anomaly 2: Within each topic segment on the same page,
    # ensure numbered headings ("3.", "3.1", "3.2") are ordered by their numeric tuple.
    segment_start = 0
    for idx in range(len(events) + 1):
        is_boundary = idx == len(events) or events[idx]["type"] in (
            "MULTILINE_CHAPTER",
            "IMPLICIT_CHAPTER",
            "ROMAN_TOPIC",
        )
        if is_boundary:
            numbered_positions: list[int] = []
            numbered_items: list[tuple[tuple[int, ...], dict]] = []
            for pos in range(segment_start, idx):
                ev = events[pos]
                if ev["type"] == "LINE":
                    parsed = _clean_numbered_heading(ev["line"])
                    if parsed is not None:
                        num_tuple = tuple(int(p) for p in parsed[0].split("."))
                        numbered_positions.append(pos)
                        numbered_items.append((num_tuple, ev))
            if len(numbered_items) > 1:
                sorted_items = [item[1] for item in sorted(numbered_items, key=lambda x: x[0])]
                for pos, sorted_ev in zip(numbered_positions, sorted_items):
                    events[pos] = sorted_ev
            segment_start = idx + 1

    return events


def build_local_draft(title: str, page_texts: list[str], content: bytes | None = None) -> list[TheoryNode]:
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
                        source_page=root_page, source_quote=root_quote[:500],
                        origin="SOURCE_EXTRACTION")]
    chapter_ids: dict[int, str] = {}
    chapter_cursor = 0
    current_chapter = "n0"
    current_chapter_title = ""
    current_part = "n0"
    part_kind: str | None = None
    numbered_sections: dict[int, tuple[str, str]] = {}
    seen_formulas_in_part: set[str] = set()

    def append(kind: NodeKind, heading: str, page: int, parent: str,
               latex: str | None = None, quote: str | None = None) -> str:
        if len(nodes) >= MAX_DRAFT_NODES:
            raise ApplicationError(422, "LOCAL_MAP_TOO_LARGE",
                                   "The PDF has too many headings for one draft; split it into smaller PDFs.")
        node_id = f"n{len(nodes)}"
        nodes.append(TheoryNode(id=node_id, parent_id=parent, kind=kind,
                                title=heading[:250], source_page=page,
                                source_quote=(quote or heading)[:500], latex=latex, reviewed=False,
                                origin="SOURCE_EXTRACTION"))
        return node_id

    def use_chapter(number: int, fallback: tuple[str, int] | None = None, quote: str | None = None) -> str:
        nonlocal current_chapter_title
        source = chapter_sources.get(number, fallback)
        if source is None:
            return "n0"  # Do not invent a chapter absent from source text.
        if number not in chapter_ids:
            chapter_ids[number] = append(
                NodeKind.SECTION,
                source[0],
                source[1],
                "n0",
                quote=quote if source is fallback else None,
            )
        current_chapter_title = source[0]
        return chapter_ids[number]

    for page_number, page in enumerate(page_texts, 1):
        if page_number in contents_pages:
            continue
        page_has_font_glyphs = any(0xE000 <= ord(char) <= 0xF8FF for char in page)
        lines = page.splitlines()
        events = _extract_page_events(lines, current_chapter_title)

        for ev in events:
            if ev["type"] == "MULTILINE_CHAPTER":
                num = ev["number"]
                if num is not None:
                    current_chapter = use_chapter(num, (ev["title"], page_number), quote=ev["quote"])
                else:
                    current_chapter = append(NodeKind.SECTION, ev["title"], page_number, "n0", quote=ev["quote"])
                    current_chapter_title = ev["title"]
                current_part, part_kind = current_chapter, None
                numbered_sections.clear()
                seen_formulas_in_part.clear()
                continue

            if ev["type"] == "IMPLICIT_CHAPTER":
                current_chapter = append(NodeKind.SECTION, ev["title"], page_number, "n0", quote=ev["quote"])
                current_chapter_title = ev["title"]
                current_part, part_kind = current_chapter, None
                numbered_sections.clear()
                seen_formulas_in_part.clear()
                continue

            if ev["type"] == "ROMAN_TOPIC":
                current_part = append(NodeKind.SECTION, ev["title"], page_number, current_chapter, quote=ev["quote"])
                part_kind = "A"
                numbered_sections.clear()
                seen_formulas_in_part.clear()
                continue

            line = ev["line"]
            raw = ev["raw"]
            position = ev["pos"]

            chapter = _CHAPTER.fullmatch(line)
            if chapter and len(line) <= 160:
                if part_kind == "B" and line.casefold().startswith("bài "):
                    continue  # An exercise is not a new chapter.
                number = chapter.group("number")
                if number.isdigit():
                    current_chapter = use_chapter(int(number), (line, page_number), quote=raw.strip())
                    if int(number) in chapter_order:
                        chapter_cursor = max(chapter_cursor, chapter_order.index(int(number)) + 1)
                else:
                    current_chapter = append(NodeKind.SECTION, line, page_number, "n0", quote=raw.strip())
                    current_chapter_title = line
                current_part, part_kind = current_chapter, None
                numbered_sections.clear()
                seen_formulas_in_part.clear()
                continue

            part = _PART.fullmatch(line)
            if part:
                kind = part.group("part").upper()
                if kind == "A" and chapter_cursor < len(chapter_order):
                    current_chapter = use_chapter(chapter_order[chapter_cursor])
                    chapter_cursor += 1
                current_part = append(NodeKind.SECTION, line, page_number, current_chapter, quote=raw.strip())
                part_kind = kind
                numbered_sections.clear()
                seen_formulas_in_part.clear()
                continue

            topic = _TOPIC.match(line)
            if topic and len(line) <= 160:
                chapter_num_str = topic.groupdict().get("chapter")
                if chapter_num_str and int(chapter_num_str) in chapter_sources:
                    current_chapter = use_chapter(int(chapter_num_str))
                parent = current_part if part_kind in ("A", "B") and current_part != "n0" else current_chapter
                append(NodeKind.SECTION, line, page_number, parent, quote=raw.strip())
                if line.casefold().startswith("dạng "):
                    part_kind = "B"
                    current_part = parent
                continue

            # Standalone uppercase sub-banners inside a chapter (e.g. "CÔNG THỨC NGUYÊN HÀM HAY GẶP")
            if (
                part_kind != "B"
                and _is_uppercase_vietnamese_heading(line)
                and len(line.split()) >= 3
                and _normalize_heading_key(line) not in _normalize_heading_key(current_chapter_title)
            ):
                dedup = _dedup_repeated_banner(line)
                current_part = append(NodeKind.SECTION, dedup, page_number, current_chapter, quote=raw.strip())
                part_kind = "A"
                numbered_sections.clear()
                seen_formulas_in_part.clear()
                continue

            # Definitions and theorems are siblings. Never attach following
            # paragraphs, examples, or answer choices as their content.
            if part_kind != "B" and _THEORY_HEADING.fullmatch(line) and len(line) <= 100:
                parent = numbered_sections[max(numbered_sections)][1] if numbered_sections else current_part
                next_line = _clean_line(lines[position + 1]) if position + 1 < len(lines) else ""
                is_note = bool(re.match(r"^(?:Nhận xét|Chú ý|Ghi nhớ|Lưu ý|Ý nghĩa)", line, re.I))
                target_kind = NodeKind.NOTE if is_note else NodeKind.CONCEPT
                display_line = line if not is_note or line.startswith("⚠️") else f"⚠️ {line}"
                if line.endswith(".") and next_line.isdigit() and len(next_line) <= 3:
                    append(target_kind, f"{display_line[:-1]} {next_line}", page_number, parent,
                           quote=f"{raw.strip()} {next_line}")
                else:
                    append(target_kind, display_line, page_number, parent, quote=raw.strip())
                continue

            numbered = _clean_numbered_heading(line)
            if part_kind != "B" and numbered is not None and len(line) <= 140:
                section_number, clean_heading = numbered
                depth = section_number.count(".") + 1
                parent = current_part
                for ancestor_depth in range(depth - 1, 0, -1):
                    ancestor = numbered_sections.get(ancestor_depth)
                    if ancestor and section_number.startswith(ancestor[0] + "."):
                        parent = ancestor[1]
                        break
                numbered_sections[depth] = (
                    section_number,
                    append(NodeKind.SECTION, clean_heading, page_number, parent, quote=raw.strip()),
                )
                for deeper in list(numbered_sections):
                    if deeper > depth:
                        del numbered_sections[deeper]
                continue

            if part_kind != "B" and _EXAMPLE_HEADING.fullmatch(line) and len(line) <= 100:
                parent = numbered_sections[max(numbered_sections)][1] if numbered_sections else current_part
                append(NodeKind.EXAMPLE, line, page_number, parent, quote=raw.strip())
                continue

            # A formula is only copied when the *whole page* has no PDF font
            # glyphs and the source line is already plain TeX-compatible text.
            if part_kind != "B" and not page_has_font_glyphs and _is_meaningful_formula(line):
                formula_key = re.sub(r"\s+", "", line).casefold()
                if formula_key not in seen_formulas_in_part:
                    seen_formulas_in_part.add(formula_key)
                    parent = numbered_sections[max(numbered_sections)][1] if numbered_sections else current_part
                    append(NodeKind.FORMULA, line, page_number, parent, latex=line, quote=raw.strip())

    if len(nodes) == 1:
        # A plain short note has no headings; keep one cited text line so the
        # teacher can still create the map, without inventing content.
        line, page_number = first_source
        append(NodeKind.CONCEPT, line[:120], page_number, "n0")

    prefilled = prefill_source_steps(nodes, page_texts)

    if content:
        try:
            from app.theory_maps.notebook import find_heading_block, notebook_index
            index = notebook_index(content, page_texts)
            all_blocks = [b for s in index.get("sections", []) for b in s.get("blocks", [])]
            for node in prefilled:
                best_block = find_heading_block(all_blocks, node.source_page, node.title)
                if best_block:
                    node.block_id = best_block.get("id")
                    if "top" in best_block and "bottom" in best_block:
                        node.bounding_box = {"top": best_block["top"], "bottom": best_block["bottom"]}
        except Exception:
            pass

    return prefilled
