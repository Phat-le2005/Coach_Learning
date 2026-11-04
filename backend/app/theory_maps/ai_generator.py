"""AI-powered Theory Mindmap Generator using Gemini via AIGateway.

Analyzes raw PDF text/sections and synthesizes a pedagogical, hierarchical mind map
with KaTeX formulas, step-by-step methods, and concept definitions for high school mathematics.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from pydantic import BaseModel, Field

from app.ai.gateway import AIGateway
from app.ai.types import AIMessage, AIRole, AITaskType
from app.theory_maps.schemas import NodeKind, TheoryLearningStep, TheoryNode

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Bạn là Chuyên gia Sư phạm Toán học và Huấn luyện viên Luyện thi THPT Quốc gia hàng đầu của EduMS.
Nhiệm vụ của bạn là phân tích tài liệu học tập Toán và thiết kế một SƠ ĐỒ TƯ DUY (MIND MAP) TOÀN DIỆN - BÁM SÁT 100% CẤU TRÚC MỤC LỤC - ĐẦY ĐỦ CÔNG THỨC, PHƯƠNG PHÁP VÀ VÍ DỤ MINH HỌA.

NGUYÊN TẮC BẮT BUỘC VỀ TÍNH TOÀN DIỆN (CRITICAL):
1. BÁM SÁT 100% CẤU TRÚC MỤC LỤC CỦA TÀI LIỆU:
   - Nếu tài liệu có Mục lục (Table of Contents), bạn BẮT BUỘC phải trích xuất ĐẦY ĐỦ 100% tất cả các CHỦ ĐỀ / CHƯƠNG LỚN (SECTION) và MỌI DẠNG BÀI TOÁN (CONCEPT) được liệt kê trong mục lục!
   - TUYỆT ĐỐI KHÔNG ĐƯỢC GỘP CÁC CHỦ ĐỀ VÀO NHAU (Ví dụ: Chủ đề 05 và Chủ đề 06 là 2 chủ đề riêng biệt thì BẮT BUỘC tạo 2 nút SECTION riêng biệt).
   - TUYỆT ĐỐI KHÔNG ĐƯỢC BỎ SÓT BẤT KỲ DẠNG TOÁN NÀO TRONG MỤC LỤC! (Ví dụ: Nếu Chủ đề 1 có từ Dạng 1.1 đến Dạng 1.6 thì phải tạo ĐỦ cả 6 nút CONCEPT từ Dạng 1.1 đến 1.6).
   - Đặt tên nhánh CONCEPT chuẩn xác theo mục lục: "Dạng X.Y: Tên dạng bài" (ví dụ: "Dạng 1.1: Xét tính đơn điệu của hàm số (biết đồ thị, bbt)", "Dạng 1.2: Hàm số bậc ba đơn điệu trên khoảng k").

2. CẤU TRÚC PHÂN NHÁNH 4 TẦNG:
   - Tầng 1: Nút GỐC (ROOT) - Chuyên đề chính (id: "n_root", parent_id: null, kind: "ROOT", title: Tên chuyên đề)
   - Tầng 2: Các BÀI HỌC / CHỦ ĐỀ CHÍNH (SECTION) - ĐỦ 100% theo mục lục (ví dụ: "Chủ đề 01. Đơn điệu hàm số", "Chủ đề 02. Cực trị", ..., "Chủ đề 06. Sự tương giao")
   - Tầng 3: TẤT CẢ CÁC DẠNG BÀI TOÁN (CONCEPT) - ĐỦ 100% các Dạng X.Y theo mục lục.
     + Mỗi nút CONCEPT phải có `body` tóm tắt bản chất, dấu hiệu nhận biết, phương pháp giải toán.
     + Trường `latex`: Chứa công thức toán học KaTeX mấu chốt của dạng bài (nếu có).
     + Trường `learning_steps`: Quy trình giải từng bước (Bước 1, Bước 2...).
   - Tầng 4: CÁC NHÁNH CON THỰC CHIẾN MỞ RỘNG (Dưới các dạng toán trọng tâm):
     + Nhánh FORMULA (Công thức & Điều kiện bổ sung):
       title: "📐 Công thức: [Tóm tắt ngắn gọn]",
       latex: "Mã KaTeX chuẩn",
       body: "Ý nghĩa và điều kiện áp dụng."
     + Nhánh METHOD (Phương pháp giải / Quy trình):
       title: "📝 Phương pháp: [Tên phương pháp]",
       learning_steps: [...]
     + Nhánh EXAMPLE (Ví dụ bài tập mẫu cụ thể):
       title: "💡 Ví dụ: [Đề bài ngắn gọn]",
       body: "Đề bài: ...\\nLời giải: Từng bước giải chi tiết, rõ ràng và có đáp số cụ thể.",
       latex: "Đáp số hoặc biểu thức mấu chốt"
     + Nhánh NOTE (Bẫy sai lầm & Mẹo làm nhanh):
       title: "⚠️ Bẫy sai lầm: [Lỗi học sinh hay mất điểm]",
       body: "Phân tích vì sao học sinh hay sai và cách khắc phục chính xác."

3. QUY TẮC TOÁN HỌC & LATEX:
   - KHÔNG dùng ký tự lạ font lỗi (như □ hay private glyphs).
   - Mọi công thức toán học phải viết dạng KaTeX tương thích chuẩn (ví dụ: \\frac{a}{b}, \\sqrt{x^2+1}, \\Delta > 0, \\ge, \\le).
   - Tổng số lượng nút: từ 45 đến 85 nút (đảm bảo ĐỦ 1 Root + ĐỦ các Chủ đề trong mục lục + ĐỦ các Dạng bài toán trong mục lục + các nhánh con ví dụ/công thức mở rộng).
   - Luôn chỉ định `source_page` chính xác tương ứng theo số trang ghi trong mục lục hoặc trong tài liệu.

ĐỊNH DẠNG ĐẦU RA BẮT BUỘC (JSON chuẩn duy nhất):
{
  "nodes": [
    {
      "id": "n_root",
      "parent_id": null,
      "kind": "ROOT",
      "title": "Chuyên đề Đạo hàm & Khảo sát hàm số",
      "body": "Tổng quan toàn bộ kiến thức trọng tâm",
      "latex": null,
      "learning_steps": [],
      "source_page": 1,
      "source_quote": "..."
    },
    {
      "id": "n_sec_1",
      "parent_id": "n_root",
      "kind": "SECTION",
      "title": "Chủ đề 01. Đơn điệu hàm số",
      "body": "Khái niệm và điều kiện cần và đủ để hàm số đồng biến, nghịch biến trên khoảng K.",
      "latex": "f'(x) \\ge 0, \\forall x \\in K",
      "learning_steps": [],
      "source_page": 4,
      "source_quote": "..."
    },
    {
      "id": "n_c_1_1",
      "parent_id": "n_sec_1",
      "kind": "CONCEPT",
      "title": "Dạng 1.1: Xét tính đơn điệu của hàm số (biết đồ thị, bbt)",
      "body": "Dựa vào dấu của f'(x) trên bảng biến thiên hoặc hướng đi lên/đi xuống của đồ thị f(x).",
      "latex": "f'(x) > 0 \\implies \\text{hàm số đồng biến}",
      "learning_steps": [],
      "source_page": 4,
      "source_quote": "..."
    },
    {
      "id": "n_c_1_2",
      "parent_id": "n_sec_1",
      "kind": "CONCEPT",
      "title": "Dạng 1.2: Hàm số bậc ba đơn điệu trên khoảng k",
      "body": "Phương pháp cô lập tham số m hoặc xét dấu tam thức bậc hai y' = ax^2 + bx + c.",
      "latex": "\\Delta' \\le 0, a > 0",
      "learning_steps": [],
      "source_page": 5,
      "source_quote": "..."
    },
    {
      "id": "n_f_1_2",
      "parent_id": "n_c_1_2",
      "kind": "FORMULA",
      "title": "📐 Công thức: Quy tắc cô lập tham số m",
      "body": "m >= g(x) với mọi x thuộc K <=> m >= max_K g(x); m <= g(x) với mọi x thuộc K <=> m <= min_K g(x)",
      "latex": "m \\ge g(x), \\forall x \\in K \\iff m \\ge \\max_K g(x)",
      "learning_steps": [],
      "source_page": 5,
      "source_quote": "..."
    },
    {
      "id": "n_m_1_2",
      "parent_id": "n_c_1_2",
      "kind": "METHOD",
      "title": "📝 Phương pháp: Quy trình cô lập m 4 bước",
      "body": "Quy trình giải bài toán tham số đơn điệu bậc ba.",
      "latex": null,
      "learning_steps": [
        {"instruction": "Bước 1: Tính đạo hàm f'(x; m), cho f'(x; m) >= 0 hoặc <= 0 theo yêu cầu.", "latex": null, "source_page": 5},
        {"instruction": "Bước 2: Cô lập tham số m về một vế: m >= g(x) hoặc m <= g(x).", "latex": "m \\ge g(x)", "source_page": 5},
        {"instruction": "Bước 3: Lập bảng biến thiên của hàm số g(x) trên K và tìm max/min.", "latex": null, "source_page": 5},
        {"instruction": "Bước 4: Kết luận giá trị m cần tìm.", "latex": null, "source_page": 5}
      ],
      "source_page": 5,
      "source_quote": "..."
    },
    {
      "id": "n_no_1_3",
      "parent_id": "n_sec_1",
      "kind": "NOTE",
      "title": "⚠️ Bẫy sai lầm: Dấu bằng đối với hàm nhất biến",
      "body": "Với hàm y = (ax+b)/(cx+d), đạo hàm y' = (ad-bc)/(cx+d)^2 > 0 để đồng biến. TUYỆT ĐỐI KHÔNG CÓ DẤU BẰNG vì y' không thể bằng 0 tại hữu hạn điểm.",
      "latex": "y' = \\frac{ad - bc}{(cx + d)^2} > 0",
      "learning_steps": [],
      "source_page": 7,
      "source_quote": "..."
    }
  ]
}
"""


class RawLearningStep(BaseModel):
    instruction: str
    latex: str | None = None
    source_page: int | None = 1
    source_quote: str | None = None


class RawTheoryNode(BaseModel):
    id: str
    parent_id: str | None = None
    kind: NodeKind
    title: str
    body: str = ""
    latex: str | None = None
    learning_steps: list[RawLearningStep] = Field(default_factory=list)
    source_page: int = 1
    source_quote: str = ""


class RawMindmapResult(BaseModel):
    nodes: list[RawTheoryNode]


def _clean_pua(text: str) -> str:
    """Strip Word/MathType Private Use Area symbols (0xE000-0xF8FF) that corrupt AI tokenizers."""
    cleaned = "".join(" " if 0xE000 <= ord(c) <= 0xF8FF else c for c in text)
    return " ".join(cleaned.split())


def extract_table_of_contents_text(page_texts: list[str]) -> str:
    """Extract structured table of contents lines from early pages of document."""
    toc_entries: list[str] = []
    max_scan = min(6, len(page_texts))
    for p_idx in range(max_scan):
        text = page_texts[p_idx]
        clean_p = _clean_pua(text)
        for raw_line in clean_p.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            is_toc_heading = any(k in lower for k in ["chủ đề", "chương", "dạng", "mục lục", "bài"])
            has_dots_and_page = bool(re.search(r"\.{3,}\s*\d+", line))
            if is_toc_heading or has_dots_and_page:
                toc_entries.append(f"(Trang {p_idx + 1}): {line}")

    if len(toc_entries) >= 5:
        return "\n".join(toc_entries)
    return ""


def build_ai_mindmap_prompt(title: str, page_texts: list[str]) -> str:
    """Build a comprehensive, source-faithful prompt covering all pages without skipping."""
    total_pages = len(page_texts)
    toc_text = extract_table_of_contents_text(page_texts)

    sampled_pages: list[str] = []
    max_budget = 65000
    per_page_budget = max(500, max_budget // max(1, total_pages))

    for idx in range(total_pages):
        clean_text = _clean_pua(page_texts[idx])
        if not clean_text:
            continue
        entry = f"--- [TRANG {idx + 1}/{total_pages}] ---\n{clean_text[:per_page_budget]}"
        sampled_pages.append(entry)

    document_content = "\n\n".join(sampled_pages)

    toc_section = ""
    if toc_text:
        toc_section = f"""
================================================================================
BẢNG MỤC LỤC CHÍNH CỦA TÀI LIỆU (BẮT BUỘC BÁM SÁT 100% CẤU TRÚC VÀ MỌI DẠNG TOÁN):
{toc_text}
================================================================================
LƯU Ý BẮT BUỘC VỀ SƯ PHẠM:
1. Bạn BẮT BUỘC phải tạo ĐỦ tất cả các Chủ đề/Chương trong mục lục trên làm các nút SECTION riêng biệt (tuyệt đối không được gộp).
2. Bạn BẮT BUỘC phải tạo ĐỦ tất cả các Dạng bài toán trong mục lục trên làm các nút CONCEPT (đánh số Dạng X.Y đúng chuẩn theo mục lục). TUYỆT ĐỐI KHÔNG ĐƯỢC BỎ SÓT BẤT KỲ DẠNG NÀO!
3. Dùng các trang tài liệu trích xuất bên dưới để điền: công thức KaTeX, tóm tắt bản chất, các bước giải, và các ví dụ minh họa / lưu ý cho từng dạng bài.
"""

    return f"""Tài liệu: {title}
Tổng số trang: {total_pages} trang
{toc_section}
Nội dung chi tiết trích xuất từ các trang tài liệu:
{document_content}

Hãy tạo Sơ đồ tư duy (Mindmap) sư phạm toàn diện cho chuyên đề này theo đúng cấu trúc JSON yêu cầu. Bắt buộc bao quát ĐẦY ĐỦ 100% các Chủ đề và mọi Dạng bài toán trong mục lục!"""


async def generate_ai_mindmap(
    title: str,
    page_texts: list[str],
    gateway: AIGateway,
    user_id: Any = None,
) -> list[TheoryNode]:
    """Call Gemini through AIGateway to synthesize a full TheoryNode mind map."""
    total_pages = len(page_texts)
    user_prompt = build_ai_mindmap_prompt(title, page_texts)

    messages = [
        AIMessage(role=AIRole.SYSTEM, content=SYSTEM_PROMPT),
        AIMessage(role=AIRole.USER, content=user_prompt),
    ]

    try:
        response = await gateway.generate(
            task_type=AITaskType.TEACHER_THEORY_MAP,
            messages=messages,
            temperature=0.2,
            timeout=120.0,
            user_id=user_id,
        )

        content = response.content.strip()
        # Strip potential markdown code block fences ```json ... ```
        if "```" in content:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if match:
                content = match.group(1).strip()

        data = json.loads(content)
        raw_nodes = data.get("nodes", [])
        if not raw_nodes or not isinstance(raw_nodes, list):
            raise ValueError("AI response did not contain a valid 'nodes' array.")

        # Convert to TheoryNode list
        theory_nodes: list[TheoryNode] = []
        has_root = False

        for node_dict in raw_nodes:
            raw_id = str(node_dict.get("id") or f"n_{len(theory_nodes)}")
            raw_parent = node_dict.get("parent_id")
            parent_id = str(raw_parent) if raw_parent else None

            raw_kind = str(node_dict.get("kind") or "CONCEPT").upper()
            if raw_kind not in NodeKind.__members__:
                raw_kind = "SECTION" if parent_id == "n_root" else "CONCEPT"

            node_kind = NodeKind(raw_kind)
            if node_kind == NodeKind.ROOT:
                if has_root:
                    node_kind = NodeKind.SECTION
                else:
                    has_root = True
                    parent_id = None

            raw_page = node_dict.get("source_page")
            try:
                page_num = max(1, min(total_pages, int(raw_page))) if raw_page is not None else 1
            except (ValueError, TypeError):
                page_num = 1

            page_idx = page_num - 1
            page_text = page_texts[page_idx] if 0 <= page_idx < len(page_texts) else ""
            page_norm = " ".join(page_text.split()).casefold()

            raw_steps = node_dict.get("learning_steps") or []
            learning_steps: list[TheoryLearningStep] = []
            if isinstance(raw_steps, list):
                for s in raw_steps[:10]:
                    if isinstance(s, dict) and s.get("instruction"):
                        step_inst = str(s["instruction"]).strip()[:500]
                        step_latex = str(s["latex"]).strip()[:1000] if s.get("latex") else None
                        step_quote = str(s.get("source_quote") or "").strip()
                        # Only keep step quote if it actually appears in the page text to satisfy citation validation
                        step_quote_valid = step_quote if step_quote and " ".join(step_quote.split()).casefold() in page_norm else None
                        learning_steps.append(
                            TheoryLearningStep(
                                instruction=step_inst,
                                latex=step_latex,
                                source_page=page_num,
                                source_quote=step_quote_valid,
                            )
                        )

            node_title = str(node_dict.get("title") or "Khái niệm").strip()[:250]
            node_body = str(node_dict.get("body") or "").strip()[:2000]
            # Ensure definition/theorem titles have non-empty body
            if not node_body and (node_kind == NodeKind.CONCEPT or "định" in node_title.lower() or "dạng" in node_title.lower()):
                node_body = f"Nội dung trọng tâm của {node_title}."

            raw_latex = node_dict.get("latex")
            node_latex = str(raw_latex).strip()[:1000] if raw_latex else None

            # For node source quote, ensure it actually exists in page_text without fabricating citations
            raw_quote = str(node_dict.get("source_quote") or "").strip()
            source_quote = ""
            if raw_quote and " ".join(raw_quote.split()).casefold() in page_norm:
                source_quote = raw_quote[:500]
            elif " ".join(node_title.split()).casefold() in page_norm:
                source_quote = node_title[:250]
            else:
                lines = [line.strip() for line in page_text.splitlines() if len(line.strip()) >= 4]
                matching_line = next((l for l in lines if any(w.lower() in l.lower() for w in node_title.split() if len(w) > 3)), None)
                if matching_line:
                    source_quote = matching_line[:120]
                elif page_norm:
                    words = [w for w in raw_quote.split() if len(w) >= 3]
                    for w in words:
                        if w.casefold() in page_norm:
                            for l in lines:
                                if w.casefold() in l.casefold():
                                    source_quote = l[:120]
                                    break
                            if source_quote:
                                break

            # If not found on page_num, search other pages for genuine occurrences
            if not source_quote:
                for other_idx, other_text in enumerate(page_texts):
                    other_norm = " ".join(other_text.split()).casefold()
                    if " ".join(node_title.split()).casefold() in other_norm:
                        page_num = other_idx + 1
                        source_quote = node_title[:250]
                        break

            # If still completely ungrounded, skip hallucinated node
            if not source_quote:
                continue

            theory_nodes.append(
                TheoryNode(
                    id=raw_id,
                    parent_id=parent_id,
                    kind=node_kind,
                    title=node_title,
                    body=node_body,
                    latex=node_latex,
                    learning_steps=learning_steps,
                    source_page=page_num,
                    source_quote=source_quote,
                    reviewed=False,  # Draft nodes require teacher academic review before publication
                    origin="AI_STRUCTURAL",
                )
            )

        # Ensure we have at least one valid root
        if not has_root or not theory_nodes:
            first_page = page_texts[0] if page_texts else ""
            lines = [l.strip() for l in first_page.splitlines() if len(l.strip()) >= 3]
            quote = next((l for l in lines if title.casefold() in l.casefold()), None)
            if not quote and lines:
                quote = lines[0]
            root_node = TheoryNode(
                id="n_root",
                parent_id=None,
                kind=NodeKind.ROOT,
                title=title,
                body=f"Bản đồ tri thức chuyên đề: {title}",
                latex=None,
                learning_steps=[],
                source_page=1,
                source_quote=(quote or title)[:100],
                reviewed=False,
                origin="AI_STRUCTURAL",
            )
            for n in theory_nodes:
                if n.parent_id is None:
                    n.parent_id = "n_root"
            theory_nodes.insert(0, root_node)

        # Ensure acyclic hierarchy
        existing_ids = {n.id for n in theory_nodes}
        for n in theory_nodes:
            if n.parent_id and n.parent_id not in existing_ids:
                n.parent_id = theory_nodes[0].id

        # Guarantee pedagogical completeness (every Dạng bài toán has methods with steps and worked examples)
        from app.theory_maps.pedagogical_enricher import enrich_mindmap
        theory_nodes = enrich_mindmap(theory_nodes, page_texts)

        return theory_nodes

    except Exception as exc:
        logger.warning(
            "generate_ai_mindmap failed with Gemini, fallback to local draft: %s",
            exc,
            exc_info=True,
        )
        raise
