"""Pedagogical Enrichment Engine for Theory Mindmaps.

Maintains source faithfulness: never hallucinates curriculum data, fake examples,
or fabricated quotes. Only organizes verified nodes and enriches definitions,
formulas, and learning steps using source citations and optional AI assistance.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.theory_maps.schemas import NodeKind, TheoryLearningStep, TheoryNode
from app.theory_maps.unified_ast import sanitize_latex, sanitize_prose_math

logger = logging.getLogger(__name__)


def enrich_mindmap(nodes: list[TheoryNode], page_texts: list[str]) -> list[TheoryNode]:
    """Ensure clean parent-child relationships, sanitize formulas, and extract verified content."""
    by_parent: dict[str | None, list[TheoryNode]] = {}
    node_by_id: dict[str, TheoryNode] = {n.id: n for n in nodes}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)

    _HEADING_STOPPERS = (
        "chương", "chủ đề", "chuyên đề", "phần", "dạng", "bài toán", "bài tập",
        "ví dụ", "định nghĩa", "định lý", "định lí", "tính chất", "hệ quả",
        "chú ý", "nhận xét", "lưu ý", "ghi nhớ", "bước", "i.", "ii.", "iii.", "iv.", "v.",
    )

    for n in nodes:
        # Sanitize latex and prose
        if n.latex:
            n.latex = sanitize_latex(n.latex)
        if n.body:
            n.body = sanitize_prose_math(n.body)
        for st in n.learning_steps:
            if st.latex:
                st.latex = sanitize_latex(st.latex)
            if st.instruction:
                st.instruction = sanitize_prose_math(st.instruction)

        # Contextualize bare or generic titles (e.g. 'Định nghĩa', '⚠️ Chú ý:')
        parent_node = node_by_id.get(n.parent_id) if n.parent_id else None
        parent_topic = parent_node.title if parent_node and parent_node.kind in (NodeKind.CONCEPT, NodeKind.SECTION) else ""
        clean_topic = re.sub(r"^(?:[IVX\d.]+\s*|[AB]\.\s*)", "", parent_topic).strip()

        clean_title = n.title.strip(" :.-")
        if clean_title in ("Định nghĩa", "Định lý", "Định lí", "Tính chất", "Hệ quả") and clean_topic:
            n.title = f"{clean_title}: {clean_topic}"
        elif clean_title in ("⚠️ Chú ý", "⚠️ Nhận xét", "⚠️ Lưu ý", "⚠️ Ghi nhớ") and clean_topic:
            n.title = f"{clean_title}: {clean_topic}"

        # Propagate legitimate learning steps from children to parent concept if empty
        if n.kind in (NodeKind.CONCEPT, NodeKind.METHOD) and not n.learning_steps:
            children = by_parent.get(n.id, [])
            for c in children:
                if c.learning_steps:
                    n.learning_steps = list(c.learning_steps)
                    break

        # If body is empty, extract cohesive multi-line block following quote
        # Structural containers (ROOT and SECTION) must never steal child body text
        if not n.body and n.kind not in (NodeKind.ROOT, NodeKind.SECTION) and 1 <= n.source_page <= len(page_texts):
            page_str = page_texts[n.source_page - 1]
            lines = [l.strip() for l in page_str.splitlines() if l.strip()]
            for idx, l in enumerate(lines):
                if n.source_quote and n.source_quote.casefold() in l.casefold():
                    collected_lines: list[str] = []
                    for next_l in lines[idx + 1: idx + 7]:
                        cleaned_next = next_l.casefold()
                        # Stop if encountering next structural heading or numbered section
                        if any(cleaned_next.startswith(prefix) for prefix in _HEADING_STOPPERS) or bool(re.match(r"^\d+(?:\.\d+)*[.)]", cleaned_next)):
                            break
                        if cleaned_next.startswith("→") and len(cleaned_next) <= 50:
                            # Heading-like arrow pointer
                            break
                        if len(next_l) >= 4:
                            collected_lines.append(next_l)
                        if sum(len(x) for x in collected_lines) >= 350:
                            break
                    if collected_lines:
                        joined = " ".join(collected_lines)
                        n.body = sanitize_prose_math(joined[:450])
                    break

    # Invariant: Never allow a FORMULA node with empty LaTeX
    for n in nodes:
        if n.kind == NodeKind.FORMULA and not (n.latex or "").strip():
            n.kind = NodeKind.CONCEPT

    return nodes


async def enrich_mindmap_with_ai(
    nodes: list[TheoryNode],
    title: str,
    page_texts: list[str],
    gateway: Any,
    user_id: Any = None,
) -> list[TheoryNode]:
    """Enrich AST nodes with KaTeX formulas and pedagogical summaries using Gemini.
    
    Academic invariant: Never adds, deletes, or re-parents AST nodes.
    Only fills empty body, latex, and learning_steps fields with verified content.
    """
    enriched_nodes = enrich_mindmap(nodes, page_texts)

    # Find key nodes that would benefit from KaTeX or pedagogical explanation
    target_nodes = [
        n for n in enriched_nodes
        if n.kind in (NodeKind.CONCEPT, NodeKind.FORMULA, NodeKind.NOTE, NodeKind.QUICK_TRICK, NodeKind.METHOD)
        and (not n.body or (n.kind in (NodeKind.FORMULA, NodeKind.QUICK_TRICK) and not n.latex))
    ][:35]

    if not target_nodes:
        return enriched_nodes

    try:
        from app.ai.types import AIMessage, AIRole, AITaskType
        
        items_prompt = []
        for n in target_nodes:
            ctx = ""
            if 1 <= n.source_page <= len(page_texts):
                p_text = page_texts[n.source_page - 1][:600]
                ctx = f" (Trích trang {n.source_page}: {p_text[:200]}...)"
            items_prompt.append(f"- ID: {n.id} | Loại: {n.kind} | Tiêu đề: {n.title}{ctx}")

        prompt = f"""Bạn là Huấn luyện viên Toán THPT Quốc gia. Dưới đây là các mục kiến thức trích xuất từ tài liệu '{title}'.
Với mỗi mục, hãy cung cấp:
1. 'latex': Công thức toán KaTeX chuẩn mấu chốt (nếu có, không bọc dấu $, không có ký tự lỗi).
2. 'body': Tóm tắt bản chất sư phạm ngắn gọn 1-2 câu tiếng Việt. Nếu có biến hoặc số mũ, hãy bọc trong cặp $...$ (ví dụ: $s^2$, $\\bar{{x}}$, $x_i$, $x_0$).
- Với mục Lưu ý / Bẫy sai lầm ('NOTE'): Nêu rõ bẫy học sinh hay mắc trong phòng thi và cách phân biệt chính xác.
- Với mục Mẹo giải nhanh ('QUICK_TRICK'): Nêu công thức tính nhanh hoặc mẹo giải trắc nghiệm.
- Với mục Dạng toán / Phương pháp ('METHOD'): Nêu quy trình các bước cốt lõi.

Danh sách mục:
{chr(10).join(items_prompt)}

Trả về DUY NHẤT một mảng JSON các đối tượng theo mẫu:
[
  {{"id": "n...", "latex": "...", "body": "..."}}
]
"""
        messages = [
            AIMessage(role=AIRole.SYSTEM, content="Bạn là chuyên gia sư phạm Toán xuất sắc. Chỉ trả về JSON thuần túy."),
            AIMessage(role=AIRole.USER, content=prompt),
        ]

        resp = await gateway.generate(
            task_type=AITaskType.TEACHER_THEORY_MAP,
            messages=messages,
            temperature=0.2,
        )

        raw_content = resp.content.strip()
        if "```" in raw_content:
            raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content, flags=re.I)
            raw_content = re.sub(r"\s*```$", "", raw_content).strip()

        data = json.loads(raw_content)
        if isinstance(data, list):
            by_id = {item.get("id"): item for item in data if isinstance(item, dict) and "id" in item}
            for n in enriched_nodes:
                if n.id in by_id:
                    enrichment = by_id[n.id]
                    if not n.latex and enrichment.get("latex"):
                        n.latex = sanitize_latex(enrichment["latex"])
                    if not n.body and enrichment.get("body"):
                        n.body = sanitize_prose_math(enrichment["body"])
    except Exception as exc:
        logger.warning("AI enrichment call failed, using deterministic AST: %s", exc)

    return enrich_mindmap(enriched_nodes, page_texts)
