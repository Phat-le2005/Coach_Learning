"""Unified Abstract Syntax Tree (AST) for Educational Mathematics PDFs.

Acts as the Single Source of Truth for both Mindmaps (TheoryNodes) and
Notebook Study Guides (Cards/Sections), guaranteeing structural parity.
"""

from collections import OrderedDict
import copy
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
import logging
import re
import threading
from typing import Any

from app.core.exceptions import ApplicationError
from app.theory_maps.heading_scorer import (
    HeadingLevel,
    PedagogicalRole,
    ScoredHeading,
    score_line_heading,
)
from app.theory_maps.layout_engine import (
    DocumentProfiler,
    TextLine,
    clean_line_text,
    extract_page_lines_2d,
    is_reliable_text,
)
from app.theory_maps.schemas import NodeKind, TheoryLearningStep, TheoryNode
from app.theory_maps.visual_layout import detect_document_visual_blocks, is_in_table_region

logger = logging.getLogger(__name__)

MAX_DRAFT_NODES = 400

_STEP = re.compile(r"^Bước\s+0?(?P<number>\d{1,2})(?:\s*[.:]\s*|\s+)(?P<instruction>.+)$", re.I)
_METHOD_TITLE = re.compile(r"^(?:Dạng\s+\d+\.\d+|(?:\d+\.\s+)?Bài toán\s+\d+)", re.I)


@dataclass
class ContentBlock:
    id: str
    page: int
    ordinal: int
    title: str
    source_quote: str
    kind: str
    top: float
    bottom: float
    latex: str | None = None


@dataclass
class TopicNode:
    id: str
    title: str
    source_page: int
    source_quote: str
    kind: str
    blocks: list[ContentBlock] = field(default_factory=list)


@dataclass
class ChapterNode:
    id: str
    number: int | None
    title: str
    source_page: int
    source_quote: str
    topics: list[TopicNode] = field(default_factory=list)


@dataclass
class DocumentAST:
    title: str
    chapters: list[ChapterNode] = field(default_factory=list)
    page_count: int = 1


def build_unified_ast(
    title: str,
    page_texts: list[str],
    content: bytes | None = None,
) -> DocumentAST:
    """Build a unified hierarchical AST from PDF text and spatial layout."""
    if not page_texts or not any(p.strip() for p in page_texts):
        raise ApplicationError(422, "PDF_TEXT_REQUIRED", "A local draft needs source text.")

    profiler = DocumentProfiler(page_texts, content)
    ast = DocumentAST(title=title, page_count=len(page_texts))

    pdfium_doc = None
    if content:
        try:
            import pypdfium2 as pdfium
            pdfium_doc = pdfium.PdfDocument(content)
        except Exception as exc:
            logger.warning("Could not open PDF with pdfium: %s", exc)

    all_page_lines: list[list[TextLine]] = []
    try:
        for pno in range(1, len(page_texts) + 1):
            if pdfium_doc and pno <= len(pdfium_doc):
                page = pdfium_doc[pno - 1]
                lines = extract_page_lines_2d(page, pno, profiler)
                page.close()
            else:
                lines = [
                    TextLine(
                        page=pno,
                        text=clean_line_text(l),
                        raw_text=l.strip(),
                        top=50.0 + i * 20.0,
                        bottom=68.0 + i * 20.0,
                        left=50.0,
                        right=500.0,
                        height=18.0,
                    )
                    for i, l in enumerate(page_texts[pno - 1].splitlines())
                    if clean_line_text(l)
                ]
            all_page_lines.append(lines)
    finally:
        if pdfium_doc:
            try:
                pdfium_doc.close()
            except Exception:
                pass

    # Detect visual layout (tables, figures, banners)
    doc_visual_blocks = detect_document_visual_blocks(content) if content else {}

    # Score headings across all pages
    scored_by_page: list[list[ScoredHeading]] = []
    for pno, lines in enumerate(all_page_lines, 1):
        if pno in profiler.profile.contents_pages:
            scored_by_page.append([])
            continue
        page_scored: list[ScoredHeading] = []
        median_h = 10.0
        if lines:
            heights = sorted(l.height for l in lines if l.height > 2.0)
            if heights:
                median_h = heights[len(heights) // 2]
        for idx, line in enumerate(lines):
            # Suppress lines located within detected 2D table boxes to avoid splitting formulas
            if is_in_table_region(pno, line.top, line.bottom, doc_visual_blocks):
                continue
            sh = score_line_heading(line, lines, idx, median_h)
            if sh:
                page_scored.append(sh)
        scored_by_page.append(page_scored)

    # If TOC has chapters, register them
    toc_chapters: dict[int, ChapterNode] = {}
    for entry in profiler.profile.contents_outline:
        t = entry["title"]
        m = re.search(r"^(?:Chủ đề|Chương)\s+(\d+)\.?\s*(.+)$", t, re.I)
        if m:
            cnum = int(m.group(1))
            cname = f"Chủ đề {cnum:02d} · {m.group(2).strip()}"
            if cnum not in toc_chapters:
                toc_chapters[cnum] = ChapterNode(
                    id=f"chap-toc-{cnum}",
                    number=cnum,
                    title=cname,
                    source_page=entry["source_page"],
                    source_quote=t,
                )

    current_chapter: ChapterNode | None = None
    current_topic: TopicNode | None = None

    for pno, headings in enumerate(scored_by_page, 1):
        for h in headings:
            if h.level == HeadingLevel.CHAPTER:
                # Deduplicate repeated chapter headings on the same page
                if (
                    current_chapter
                    and current_chapter.source_page == pno
                    and (
                        h.clean_title.casefold() in current_chapter.title.casefold()
                        or current_chapter.title.casefold() in h.clean_title.casefold()
                    )
                ):
                    continue
                m = re.search(r"\b(\d+)\b", h.clean_title)
                chap_num = int(m.group(1)) if m else (len(ast.chapters) + 1)
                current_chapter = ChapterNode(
                    id=f"chap-{len(ast.chapters) + 1}",
                    number=chap_num,
                    title=h.clean_title,
                    source_page=pno,
                    source_quote=h.source_quote,
                )
                ast.chapters.append(current_chapter)
                current_topic = None
                continue

            # Check if this heading starts a new Topic/Method section
            is_new_topic = h.level in (HeadingLevel.TOPIC, HeadingLevel.SECTION) or h.role in (
                PedagogicalRole.METHOD, PedagogicalRole.THEORY,
            )
            if is_new_topic and h.role != PedagogicalRole.FORMULA:
                # Associate with TOC chapter if numbering matches
                method_num_match = re.search(r"Dạng\s+(\d+)\.\d+", h.clean_title, re.I)
                if method_num_match and toc_chapters:
                    cnum = int(method_num_match.group(1))
                    if cnum in toc_chapters:
                        if toc_chapters[cnum] not in ast.chapters:
                            ast.chapters.append(toc_chapters[cnum])
                        current_chapter = toc_chapters[cnum]

                if current_chapter is None:
                    current_chapter = ChapterNode(
                        id=f"chap-{len(ast.chapters) + 1}",
                        number=len(ast.chapters) + 1,
                        title=title,
                        source_page=pno,
                        source_quote=h.source_quote,
                    )
                    ast.chapters.append(current_chapter)

                topic_id = f"topic-{len(current_chapter.topics) + 1}"
                kind = "METHOD" if h.role == PedagogicalRole.METHOD else "THEORY"
                current_topic = TopicNode(
                    id=topic_id,
                    title=h.clean_title,
                    source_page=pno,
                    source_quote=h.source_quote,
                    kind=kind,
                )
                current_chapter.topics.append(current_topic)

            if current_topic is not None:
                block_id = f"p{pno}-b{len(current_topic.blocks)}"
                current_topic.blocks.append(ContentBlock(
                    id=block_id,
                    page=pno,
                    ordinal=len(current_topic.blocks),
                    title=h.clean_title,
                    source_quote=h.source_quote,
                    kind=h.role.value,
                    top=h.line.top,
                    bottom=h.line.bottom,
                    latex=h.latex,
                ))

    # Refine vertical bounding boxes of content blocks on each page
    for ch in ast.chapters:
        for top in ch.topics:
            for idx, blk in enumerate(top.blocks):
                if idx + 1 < len(top.blocks) and top.blocks[idx + 1].page == blk.page:
                    blk.bottom = max(blk.bottom, top.blocks[idx + 1].top - 2.0)
                else:
                    blk.bottom = max(blk.bottom, 780.0)

    # Deduplicate chapters that share the same source page and merge their topics
    dedup_chapters: list[ChapterNode] = []
    for ch in ast.chapters:
        if dedup_chapters and dedup_chapters[-1].source_page == ch.source_page:
            dedup_chapters[-1].topics.extend(ch.topics)
        else:
            dedup_chapters.append(ch)
    ast.chapters = dedup_chapters

    # Ensure 100% Page Coverage: attach fallback cards for pages without explicit headings
    covered_pages = set()
    for ch in ast.chapters:
        covered_pages.add(ch.source_page)
        for top in ch.topics:
            covered_pages.add(top.source_page)
            for blk in top.blocks:
                covered_pages.add(blk.page)

    for pno in range(1, len(page_texts) + 1):
        if pno in covered_pages or pno in profiler.profile.contents_pages:
            continue
        raw_page = page_texts[pno - 1].strip()
        if not raw_page or len(raw_page) < 5:
            continue

        active_chap = ast.chapters[0] if ast.chapters else None
        for ch in ast.chapters:
            if ch.source_page <= pno:
                active_chap = ch
        if active_chap is None:
            continue

        lower_page = raw_page.casefold()
        is_integral = any(kw in lower_page for kw in ("∫", "\\int", "nguyên hàm", "tích phân"))
        is_derivative = any(kw in lower_page for kw in ("đạo hàm", "bảng đạo hàm", "f'(x)", "y'"))
        is_formula = is_integral or is_derivative or any(kw in lower_page for kw in ("dx", "lna", "sin", "cos", "=", "lim", "x^"))
        t_kind = "THEORY"
        if is_integral:
            if any(kw in lower_page for kw in ("giải nhanh", "đặc biệt", "tính nhanh", "công thức nhanh")):
                t_title = f"⚡ Công thức giải nhanh nguyên hàm - tích phân (Trang {pno})"
                t_kind = "QUICK_TRICK"
            elif any(kw in lower_page for kw in ("phân thức", "hữu tỷ", "bậc nhất", "tam thức")):
                t_title = f"📐 Bảng nguyên hàm hàm phân thức hữu tỷ (Trang {pno})"
            elif any(kw in lower_page for kw in ("căn thức", "\\sqrt", "lượng giác", "sin", "cos", "tan")):
                t_title = f"📐 Bảng nguyên hàm căn thức & lượng giác mở rộng (Trang {pno})"
            elif any(kw in lower_page for kw in ("hàm hợp", "u(x)", "du", "f(u)")):
                t_title = f"📐 Bảng nguyên hàm các hàm hợp u(x) (Trang {pno})"
            else:
                t_title = f"📐 Bảng nguyên hàm các hàm số cơ bản (Trang {pno})"
        elif is_derivative:
            if any(kw in lower_page for kw in ("lượng giác", "sin", "cos", "tan", "cot")):
                t_title = f"📐 Bảng đạo hàm hàm lượng giác (Trang {pno})"
            elif any(kw in lower_page for kw in ("mũ", "logarit", "ln", "e^x", "a^x")):
                t_title = f"📐 Bảng đạo hàm hàm mũ & logarit (Trang {pno})"
            elif any(kw in lower_page for kw in ("hàm hợp", "u(x)")):
                t_title = f"📐 Bảng đạo hàm các hàm hợp (Trang {pno})"
            else:
                t_title = f"📐 Bảng công thức đạo hàm trọng tâm (Trang {pno})"
        elif is_formula:
            t_title = f"📐 Bảng công thức trọng tâm (Trang {pno})"
        elif len(first_line) >= 6 and is_reliable_text(first_line):
            t_title = f"{first_line} (Trang {pno})"
        else:
            t_title = f"Nội dung trọng tâm (Trang {pno})"

        # Provide cohesive single-page card preserving full tables and diagrams
        page_blocks = [
            ContentBlock(
                id=f"p{pno}-b0",
                page=pno,
                ordinal=0,
                title=t_title,
                source_quote=raw_page.splitlines()[0].strip()[:200],
                kind=t_kind,
                top=50.0,
                bottom=780.0,
            ),
        ]
        top_node = TopicNode(
            id=f"topic-p{pno}",
            title=t_title,
            source_page=pno,
            source_quote=raw_page.splitlines()[0].strip()[:200],
            kind=t_kind,
            blocks=page_blocks,
        )
        active_chap.topics.append(top_node)

    # Ensure every chapter has at least one topic representing its cover page
    for ch in ast.chapters:
        if not any(t.source_page == ch.source_page for t in ch.topics):
            ch.topics.insert(0, TopicNode(
                id=f"topic-ch{ch.number}-cover",
                title=ch.title,
                source_page=ch.source_page,
                source_quote=ch.source_quote,
                kind="THEORY",
                blocks=[
                    ContentBlock(
                        id=f"p{ch.source_page}-b0",
                        page=ch.source_page,
                        ordinal=0,
                        title=ch.title,
                        source_quote=ch.source_quote,
                        kind="THEORY",
                        top=50.0,
                        bottom=780.0,
                    )
                ],
            ))

    # Sort topics chronologically by source_page within every chapter using numeric id order
    for ch in ast.chapters:
        ch.topics.sort(key=lambda t: (t.source_page, int(re.search(r'\d+', t.id).group()) if re.search(r'\d+', t.id) else 0))

    # Fallback if no chapter or topic created
    if not ast.chapters:
        first_q = page_texts[0].splitlines()[0].strip() if page_texts[0].splitlines() else title
        ch = ChapterNode(id="chap-1", number=1, title=title, source_page=1, source_quote=first_q)
        top = TopicNode(id="topic-1", title="Lý thuyết", source_page=1, source_quote=first_q, kind="THEORY")
        ch.topics.append(top)
        ast.chapters.append(ch)

    return ast


def _prefill_learning_steps(
    nodes: list[TheoryNode],
    page_texts: list[str],
) -> None:
    """Pre-fill verified learning steps for exercise methods with source citations."""
    method_nodes = [
        n for n in nodes
        if _METHOD_TITLE.search(n.title)
        or n.kind == NodeKind.METHOD
        or any(kw in n.title.casefold() for kw in ("quy trình", "phương pháp", "các bước", "dạng"))
    ]
    by_page_and_title = {(n.source_page, n.title): n for n in method_nodes}

    candidates: dict[str, list[tuple[int, TheoryLearningStep] | None]] = {}
    active: TheoryNode | None = None

    for pno, page in enumerate(page_texts, 1):
        for raw in page.splitlines():
            cleaned = clean_line_text(raw)
            if _METHOD_TITLE.search(cleaned):
                active = by_page_and_title.get((pno, cleaned))
                continue
            # Also check if line matches any method node on this page
            matched_node = None
            for mn in method_nodes:
                if mn.source_page == pno and (mn.title.casefold() in cleaned.casefold() or cleaned.casefold() in mn.title.casefold()):
                    matched_node = mn
                    break
            if matched_node:
                active = matched_node
                continue

            if not active:
                continue
            match = _STEP.fullmatch(cleaned)
            if not match:
                continue
            num = int(match.group("number"))
            instr = match.group("instruction").strip()
            if not is_reliable_text(instr) or len(instr) < 4:
                continue
            candidates.setdefault(active.id, []).append((num, TheoryLearningStep(
                instruction=instr,
                source_page=pno,
                source_quote=raw.strip()[:500],
            )))

    for n in nodes:
        if n.reviewed or n.learning_steps:
            continue
        entries = candidates.get(n.id, [])
        if not entries or len(entries) > 12:
            continue
        numbered = sorted([e for e in entries if e is not None], key=lambda x: x[0])
        nums = [num for num, _ in numbered]
        # Accept sequential steps starting at 1
        if nums == list(range(1, len(numbered) + 1)):
            n.learning_steps = [step for _, step in numbered]


def _clean_token(s: str) -> str:
    cleaned = re.sub(r"\b[IVX]+\b", "", s)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split()).casefold()


def _find_exact_page_quote(page_text: str, candidate_quote: str, title: str) -> str:
    norm_cand = " ".join(candidate_quote.split()).casefold()
    norm_title = " ".join(title.split()).casefold()
    clean_cand = _clean_token(candidate_quote)
    clean_title = _clean_token(title)

    best_match = None
    best_len = 0

    for raw in page_text.splitlines():
        norm_raw = " ".join(raw.split()).casefold()
        if not norm_raw:
            continue
        if norm_cand and (norm_cand in norm_raw or norm_raw in norm_cand):
            return raw.strip()
        if norm_title and (norm_title in norm_raw or norm_raw in norm_title):
            return raw.strip()
        clean_raw = _clean_token(raw)
        if clean_cand and len(clean_cand) >= 5 and (clean_cand in clean_raw or clean_raw in clean_cand):
            if len(clean_raw) > best_len:
                best_len = len(clean_raw)
                best_match = raw.strip()
        elif clean_title and len(clean_title) >= 5 and (clean_title in clean_raw or clean_raw in clean_title):
            if len(clean_raw) > best_len:
                best_len = len(clean_raw)
                best_match = raw.strip()

    if best_match:
        return best_match

    # Fallback to first non-empty line of the page to guarantee source citation invariant
    for raw in page_text.splitlines():
        if raw.strip():
            return raw.strip()
    return candidate_quote.strip()


_NUMBERED_PREFIX = re.compile(r"^(?P<num>\d+(?:\.\d+)*)[.)]\s+(?P<name>.*)$")
_ROMAN_SEC_PREFIX = re.compile(r"^(?P<roman>[IVX]+)(?:\.|\s+)\s*(?P<name>[A-ZÀ-Ỹ].+)$")


def sanitize_latex(latex: str | None) -> str | None:
    if not latex:
        return None
    val = latex.strip()
    if val.startswith("$$") and val.endswith("$$") and len(val) >= 4:
        val = val[2:-2].strip()
    elif val.startswith("\\[") and val.endswith("\\]") and len(val) >= 4:
        val = val[2:-2].strip()
    elif val.startswith("$") and val.endswith("$") and len(val) >= 2:
        val = val[1:-1].strip()
    # Strip illegal internal $ or broken characters
    val = val.replace("$y =", "=").replace("$", "").replace("□", "")
    # Balance braces
    open_c = val.count("{")
    close_c = val.count("}")
    if open_c > close_c:
        val += "}" * (open_c - close_c)
    elif close_c > open_c:
        val = "{" * (close_c - open_c) + val
    return val.strip() or None


def sanitize_prose_math(text: str) -> str:
    if not text:
        return ""
    val = text
    val = re.sub(r"\b([xyz])_ngang\b", r"$\\bar{\1}$", val, flags=re.I)
    val = re.sub(r"\b([A-Z])_ngang\b", r"$\\overline{\1}$", val)
    val = re.sub(r"\b([xyn])_([ijk0-9])\b", r"$\1_{\2}$", val)
    val = re.sub(r"\b([sR])\^2\b", r"$\1^2$", val)
    val = re.sub(r"\s+!=\s+", r" $\\neq$ ", val)
    return val


def _format_procedure_title(parent_title: str, step_count: int) -> str:
    clean = re.sub(r"^(?:[IVX\d.]+\s*|[AB]\.\s*)", "", parent_title).strip(" :.-")
    if not clean or clean.casefold() in ("lý thuyết", "phương pháp", "dạng"):
        return f"📝 Quy trình các bước thực hiện ({step_count} bước)"
    if len(clean) > 42:
        m = re.search(r"(khảo sát(?:\s+sự\s+biến\s+thiên)?(?:\s+và\s+vẽ\s+đồ\s+thị)?|cực trị|tiệm cận|đồng biến|nghịch biến|đạo hàm|tích phân|nguyên hàm|thể tích|khoảng cách|phương trình tiếp tuyến)", clean, re.I)
        if m:
            clean = m.group(1).strip()
        else:
            clean = clean[:38] + "..."
    return f"📝 Quy trình {clean} ({step_count} bước)"


def export_mindmap_nodes(
    ast: DocumentAST,
    page_texts: list[str],
) -> list[TheoryNode]:
    """Convert DocumentAST to a validated list of TheoryNodes with numbered hierarchy."""
    root_page = 1
    root_quote = page_texts[0].splitlines()[0].strip() if page_texts[0].splitlines() else ast.title
    for pno, p in enumerate(page_texts, 1):
        for raw in p.splitlines():
            cl = clean_line_text(raw)
            if is_reliable_text(cl) and len(cl) <= 200:
                root_page = pno
                root_quote = raw.strip()
                break
        if root_quote != ast.title:
            break

    nodes: list[TheoryNode] = [
        TheoryNode(
            id="n0",
            kind=NodeKind.ROOT,
            title=ast.title,
            body=f"Hệ thống toàn bộ kiến thức lý thuyết và công thức trọng tâm: {ast.title}",
            source_page=root_page,
            source_quote=root_quote[:500],
            origin="SOURCE_EXTRACTION",
        )
    ]

    numbered_stack: dict[int, tuple[str, str]] = {}

    def add_node(kind: NodeKind, title: str, page: int, default_parent: str, quote: str,
                 latex: str | None = None, body: str = "", block_id: str | None = None,
                 top: float | None = None, bottom: float | None = None) -> str:
        if len(nodes) >= MAX_DRAFT_NODES:
            raise ApplicationError(422, "LOCAL_MAP_TOO_LARGE", "Too many headings for one draft.")

        parent_id = default_parent
        m = _NUMBERED_PREFIX.match(title)
        if m and kind in (NodeKind.SECTION, NodeKind.CONCEPT, NodeKind.METHOD):
            sec_num = m.group("num")
            depth = sec_num.count(".") + 1
            for ancestor_depth in range(depth - 1, 0, -1):
                ancestor = numbered_stack.get(ancestor_depth)
                if ancestor and sec_num.startswith(ancestor[0] + "."):
                    parent_id = ancestor[1]
                    break
            nid = f"n{len(nodes)}"
            numbered_stack[depth] = (sec_num, nid)
            for d in list(numbered_stack):
                if d > depth:
                    del numbered_stack[d]
        else:
            if numbered_stack and kind in (
                NodeKind.CONCEPT, NodeKind.EXAMPLE, NodeKind.FORMULA,
                NodeKind.NOTE, NodeKind.METHOD, NodeKind.QUICK_TRICK,
            ):
                parent_id = numbered_stack[max(numbered_stack)][1]
            nid = f"n{len(nodes)}"

        bbox = {"top": top, "bottom": bottom} if top is not None and bottom is not None else None
        page_str = page_texts[page - 1] if 1 <= page <= len(page_texts) else ""
        exact_quote = _find_exact_page_quote(page_str, quote, title)
        nodes.append(TheoryNode(
            id=nid,
            parent_id=parent_id,
            kind=kind,
            title=title[:250],
            body=sanitize_prose_math(body),
            source_page=page,
            source_quote=exact_quote[:500],
            latex=sanitize_latex(latex),
            reviewed=False,
            origin="SOURCE_EXTRACTION",
            block_id=block_id,
            bounding_box=bbox,
        ))
        return nid

    for ch in ast.chapters:
        ch_b_id = f"p{ch.source_page}-b0"
        ch_id = add_node(
            kind=NodeKind.SECTION,
            title=ch.title,
            page=ch.source_page,
            default_parent="n0",
            quote=ch.source_quote,
            block_id=ch_b_id,
            top=50.0,
            bottom=780.0,
        )
        numbered_stack.clear()
        current_roman_sec_id = ch_id
        for top in ch.topics:
            m_roman = _ROMAN_SEC_PREFIX.match(top.title)
            m_num = _NUMBERED_PREFIX.match(top.title)
            top_first_b = top.blocks[0] if top.blocks else None
            top_b_id = top_first_b.id if top_first_b else f"p{top.source_page}-b0"
            top_top = top_first_b.top if top_first_b else 50.0
            top_bot = top_first_b.bottom if top_first_b else 780.0

            if m_roman:
                top_kind = NodeKind.SECTION
                top_id = add_node(
                    kind=top_kind,
                    title=top.title,
                    page=top.source_page,
                    default_parent=ch_id,
                    quote=top.source_quote,
                    block_id=top_b_id,
                    top=top_top,
                    bottom=top_bot,
                )
                current_roman_sec_id = top_id
                numbered_stack.clear()
            else:
                top_kind = (
                    NodeKind.SECTION if m_num
                    else NodeKind.METHOD if top.kind == "METHOD" or top.title.startswith(("🎯", "📝", "Dạng "))
                    else NodeKind.NOTE if top.kind == "NOTE" or top.title.startswith("⚠️")
                    else NodeKind.CONCEPT
                )
                top_id = add_node(
                    kind=top_kind,
                    title=top.title,
                    page=top.source_page,
                    default_parent=current_roman_sec_id,
                    quote=top.source_quote,
                    block_id=top_b_id,
                    top=top_top,
                    bottom=top_bot,
                )
            # Group multi-step procedures (Bước 1, Bước 2, Bước 3...) into a single METHOD node
            step_blocks = [
                b for b in top.blocks
                if b.kind == "STEP" or bool(re.match(r"^Bước\s+\d+", b.title, re.I))
            ]
            non_step_blocks = [
                b for b in top.blocks
                if b not in step_blocks
            ]

            if step_blocks:
                parsed_steps: list[TheoryLearningStep] = []
                for sb in step_blocks:
                    m = re.match(r"^Bước\s+\d+[\s.:]+(?P<instr>.+)$", sb.title, re.I)
                    instruction = m.group("instr").strip() if m else sb.title
                    parsed_steps.append(TheoryLearningStep(
                        instruction=instruction,
                        source_page=sb.page,
                        source_quote=sb.source_quote,
                        latex=sb.latex,
                    ))

                if top_kind == NodeKind.METHOD:
                    for n in nodes:
                        if n.id == top_id:
                            n.learning_steps = parsed_steps
                            break
                else:
                    proc_title = _format_procedure_title(top.title, len(step_blocks))
                    body_summary = "Quy trình thực hiện: " + "; ".join(
                        f"Bước {i+1}: {st.instruction}" for i, st in enumerate(parsed_steps)
                    )
                    min_top = min((sb.top for sb in step_blocks if sb.top is not None), default=50.0)
                    max_bottom = max((sb.bottom for sb in step_blocks if sb.bottom is not None), default=400.0)

                    proc_id = add_node(
                        kind=NodeKind.METHOD,
                        title=proc_title,
                        page=step_blocks[0].page,
                        default_parent=top_id,
                        quote=step_blocks[0].source_quote,
                        body=body_summary,
                        block_id=step_blocks[0].id,
                        top=min_top,
                        bottom=max_bottom,
                    )
                    for n in nodes:
                        if n.id == proc_id:
                            n.learning_steps = parsed_steps
                            break

            for blk in non_step_blocks:
                if blk.title == top.title:
                    continue
                has_latex = bool((blk.latex or "").strip())
                bkind = (
                    NodeKind.FORMULA if (blk.kind == "FORMULA" or blk.title.startswith("📐")) and has_latex
                    else NodeKind.QUICK_TRICK if blk.kind == "QUICK_TRICK" or blk.title.startswith("⚡")
                    else NodeKind.METHOD if blk.kind == "METHOD" or blk.title.startswith(("🎯", "📝", "Dạng "))
                    else NodeKind.EXAMPLE if blk.kind == "EXAMPLE" or blk.title.startswith("💡")
                    else NodeKind.NOTE if blk.kind == "NOTE" or blk.title.startswith("⚠️")
                    else NodeKind.CONCEPT
                )
                add_node(
                    kind=bkind,
                    title=blk.title,
                    page=blk.page,
                    default_parent=top_id,
                    quote=blk.source_quote,
                    latex=blk.latex,
                    block_id=blk.id,
                    top=blk.top,
                    bottom=blk.bottom,
                )

    _prefill_learning_steps(nodes, page_texts)

    # Invariant: Never allow a FORMULA node with empty LaTeX
    parent_ids = {n.parent_id for n in nodes if n.parent_id is not None}
    for n in nodes:
        if n.kind == NodeKind.FORMULA and not (n.latex or "").strip():
            n.kind = NodeKind.CONCEPT
        if n.kind != NodeKind.ROOT and n.id not in parent_ids and not (
            n.body.strip() or (n.latex or "").strip() or n.learning_steps
        ):
            n.body = f"Xem nội dung kiến thức chi tiết tại trang {n.source_page} của tài liệu PDF gốc."

    return nodes


def export_notebook_index(
    ast: DocumentAST,
    content: bytes,
    page_texts: list[str],
) -> dict[str, Any]:
    """Convert DocumentAST to structured notebook sections with visual block slices."""
    sections: list[dict[str, Any]] = []
    total_blocks = 0

    for ch in ast.chapters:
        for top in ch.topics:
            sec_blocks = []
            step_blocks = [
                b for b in top.blocks
                if b.kind == "STEP" or bool(re.match(r"^Bước\s+\d+", b.title, re.I))
            ]
            non_step_blocks = [
                b for b in top.blocks
                if b not in step_blocks
            ]

            if step_blocks:
                min_top = min((sb.top for sb in step_blocks if sb.top is not None), default=50.0)
                max_bottom = max((sb.bottom for sb in step_blocks if sb.bottom is not None), default=400.0)
                sec_blocks.append({
                    "id": step_blocks[0].id,
                    "page": step_blocks[0].page,
                    "ordinal": len(sec_blocks),
                    "kind": "METHOD",
                    "title": _format_procedure_title(top.title, len(step_blocks)),
                    "top": min_top,
                    "bottom": max_bottom,
                })
                total_blocks += 1

            for blk in non_step_blocks:
                sec_blocks.append({
                    "id": blk.id,
                    "page": blk.page,
                    "ordinal": len(sec_blocks),
                    "kind": blk.kind,
                    "title": blk.title,
                    "top": blk.top,
                    "bottom": blk.bottom,
                })
                total_blocks += 1

            if not sec_blocks:
                sec_blocks.append({
                    "id": f"p{top.source_page}-b0",
                    "page": top.source_page,
                    "ordinal": 0,
                    "kind": "THEORY",
                    "title": top.title,
                    "top": 50.0,
                    "bottom": 750.0,
                })
                total_blocks += 1

            sections.append({
                "id": f"section-{len(sections) + 1}",
                "title": top.title,
                "chapter_number": ch.number,
                "chapter_title": ch.title,
                "blocks": sec_blocks,
            })

    return {
        "sections": sections,
        "total_blocks": total_blocks,
        "page_count": ast.page_count,
    }
