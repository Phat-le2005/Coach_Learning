"""
Nhận diện cấu trúc toán học ở mức MVP.

Các bộ nhận diện ở đây là heuristic:
- Phân đoạn lời giải thành các dòng/bước ứng viên.
- Phát hiện dòng có dấu hiệu công thức.
- Phát hiện bảng biến thiên theo từ khóa/ký hiệu.
- Phát hiện vùng có khả năng là hình/đồ thị dựa trên block ảnh của PDF.
Không tự khẳng định nội dung toán học nếu chưa được kiểm chứng.
"""
import re
import unicodedata
from typing import Any

STEP_START_RE = re.compile(
    r"^\s*(?:(?:Bước|Step)\s*)?(\d+)[.)]\s+|^\s*[-•]\s+|^\s*(?:Ta có|Suy ra|Do đó|Vậy|Mặt khác|Từ đó)\b",
    re.IGNORECASE,
)
EQUATION_HINT_RE = re.compile(
    r"(=|\\frac|\\sqrt|\\int|\\sum|≤|≥|≠|→|⇒|\\leq|\\geq|\\cdot|\\times)"
)
MATH_SYMBOL_RE = re.compile(r"[=+\-*/^√∫∑≤≥≠→⇒]")
VARIATION_HINTS = (
    "bảng biến thiên", "đồng biến", "nghịch biến",
    "cực đại", "cực tiểu", "tiệm cận"
)
FIGURE_HINTS = (
    "hình vẽ", "hình bên", "đồ thị", "tam giác", "đường tròn",
    "hình chóp", "hình lăng trụ", "tọa độ"
)

def _clean_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip()
            for line in text.splitlines() if line.strip()]


def clean_text(text: str) -> str:
    """Normalize extracted PDF text while retaining readable line breaks."""
    text = unicodedata.normalize("NFC", text.replace("\\n", "\n"))
    lines = _clean_lines(text)
    return "\n".join(lines)


def extract_math_elements(text: str) -> list[dict[str, Any]]:
    """Expose formula/table candidates as structured JSON without guessing."""
    lines = _clean_lines(text)
    elements: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        if EQUATION_HINT_RE.search(line) or MATH_SYMBOL_RE.search(line):
            elements.append({
                "element_id": f"formula-{index}",
                "type": "formula",
                "source_text": line,
                "latex": line,
                "needs_review": True,
            })

    for index, line in enumerate(lines, start=1):
        if "|" in line or len(re.findall(r"\[[^]]+[,;][^]]+\)", line)) >= 2:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 2:
                cells = re.split(r"\s{2,}", line)
            if len(cells) >= 2:
                elements.append({
                    "element_id": f"table-{index}",
                    "type": "table",
                    "headers": cells,
                    "rows": [],
                    "source_text": line,
                    "needs_review": True,
                })
    return elements

def split_solution_steps(solution_text: str) -> list[dict[str, Any]]:
    """
    Tách thành các bước ứng viên dựa trên xuống dòng, số thứ tự,
    từ nối suy luận và dòng biểu thức. Đây chưa phải suy luận chứng minh.
    """
    lines = _clean_lines(solution_text)
    if not lines:
        return []

    groups: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        starts_new = bool(STEP_START_RE.search(line))
        equation_line = bool(EQUATION_HINT_RE.search(line) or MATH_SYMBOL_RE.search(line))

        # Tạo nhóm mới khi có nhãn bước/từ nối; các dòng công thức được giữ
        # cùng nhóm nếu không có dấu hiệu bắt đầu bước mới.
        if current and starts_new:
            groups.append(current)
            current = []
        current.append(line)

        # Nếu một dòng là biểu thức độc lập, đóng nhóm để tránh gộp nhiều phép biến đổi.
        if equation_line and len(line) < 180:
            groups.append(current)
            current = []

    if current:
        groups.append(current)

    steps = []
    for index, group in enumerate(groups, start=1):
        raw = "\n".join(group)
        steps.append({
            "step_index": index,
            "raw_text": raw,
            "contains_equation": bool(EQUATION_HINT_RE.search(raw) or MATH_SYMBOL_RE.search(raw)),
            "step_label_detected": bool(STEP_START_RE.search(group[0])),
            "operation_candidate": infer_operation(raw),
            "verification_status": "needs_review",
        })
    return steps

def infer_operation(text: str) -> str:
    """Gợi ý loại phép biến đổi, không kết luận tính đúng sai."""
    t = text.lower()
    if any(x in t for x in ("đạo hàm", "y'=", "f'(x)", r"\frac{d")):
        return "differentiate"
    if any(x in t for x in ("nguyên hàm", "tích phân", r"\int")):
        return "integrate"
    if any(x in t for x in ("thế", "thay", "thay vào")):
        return "substitution"
    if any(x in t for x in ("phân tích", "nhân tử")):
        return "factorization"
    if "=" in text or "⇒" in text or "suy ra" in t:
        return "algebraic_transformation"
    return "explanation"

def detect_math_regions(page: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Phân loại vùng văn bản ở mức trang. BBox chính xác cần dùng get_text('dict')
    và đối chiếu với ảnh trang; ở đây trả về vùng theo dòng, không phải bbox.
    """
    text = page.get("text", "")
    lines = _clean_lines(text)
    regions = []

    for i, line in enumerate(lines):
        low = line.lower()
        kind = None
        if any(hint in low for hint in VARIATION_HINTS):
            kind = "variation_table_candidate"
        elif any(hint in low for hint in FIGURE_HINTS):
            kind = "figure_or_graph_reference"
        elif EQUATION_HINT_RE.search(line) or MATH_SYMBOL_RE.search(line):
            kind = "formula_candidate"

        if kind:
            regions.append({
                "region_id": f"p{page['page']}-r{i+1}",
                "page": page["page"],
                "kind": kind,
                "text": line,
                "confidence": 0.55,
                "review_required": True,
            })
    return regions

def extract_pdf_image_blocks(pdf_path: str) -> list[dict[str, Any]]:
    """Liệt kê block ảnh nhúng trong PDF; chưa tự hiểu nội dung ảnh."""
    import fitz
    images = []
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            page_dict = page.get_text("dict")
            for block_index, block in enumerate(page_dict.get("blocks", [])):
                if block.get("type") == 1:
                    images.append({
                        "image_id": f"p{page_index+1}-img{block_index+1}",
                        "page": page_index + 1,
                        "bbox": block.get("bbox"),
                        "width": block.get("width"),
                        "height": block.get("height"),
                        "kind": "unclassified_image",
                        "review_required": True,
                    })
    return images
