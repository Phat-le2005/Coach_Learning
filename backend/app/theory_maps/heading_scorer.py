"""Multi-signal pedagogical heading scorer.

Combines typographic height, geometric position, numbering hierarchies,
and Vietnamese pedagogical markers into a deterministic scoring model.
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any

from app.theory_maps.layout_engine import TextLine, is_reliable_text


class HeadingLevel(str, Enum):
    DOCUMENT_ROOT = "ROOT"
    CHAPTER = "CHAPTER"
    TOPIC = "TOPIC"
    SECTION = "SECTION"
    SUBSECTION = "SUBSECTION"
    CARD = "CARD"


class PedagogicalRole(str, Enum):
    CHAPTER = "CHAPTER"
    METHOD = "METHOD"
    THEORY = "THEORY"
    STEP = "STEP"
    NOTE = "NOTE"
    EXAMPLE = "EXAMPLE"
    FORMULA = "FORMULA"
    QUICK_TRICK = "QUICK_TRICK"
    OTHER = "OTHER"


@dataclass
class ScoredHeading:
    line: TextLine
    title: str
    clean_title: str
    source_quote: str
    level: HeadingLevel
    role: PedagogicalRole
    score: float
    parent_hint: str | None = None
    latex: str | None = None


_CHAPTER_PREFIX = re.compile(
    r"^(?:Chủ đề|Chương|Chuyên đề|Bài|Phần)\s+(?P<number>\d+|[IVX]+)(?:[.:]\s*|\s+[·\-]\s*|\s+)(?P<name>.+)$",
    re.I,
)
_CHAPTER_WORD_ONLY = re.compile(r"^(?:Chủ đề|Chương|Chuyên đề|Phần)$", re.I)
_CHAPTER_NUM_ONLY = re.compile(r"^(?:\d{1,2}|[IVX]{1,5})$")

_METHOD_PREFIX = re.compile(
    r"^(?:Dạng\s+(?P<ch>\d+)\.(?P<top>\d+)\.?\s*|(?:\d+\.\s+)?Bài toán\s+\d+\b\.?\s*)(?P<name>.*)$",
    re.I,
)
_PART_PREFIX = re.compile(r"^(?P<part>[AB])\.\s+(?:LÝ THUYẾT(?: CHUNG)?|CÁC DẠNG BÀI TẬP)\.?$", re.I)

_ROMAN_PREFIX = re.compile(r"^(?P<roman>I|II|III|IV|V|VI|VII|VIII|IX|X)(?:[.:)\s]+)\s*(?P<name>.+)$")
_ROMAN_SUFFIX = re.compile(r"^(?P<name>.+?)\s*(?P<roman>II|III|IV|V|VI|VII|VIII|IX|X)$")
_ROMAN_SUFFIX_I = re.compile(r"^(?P<name>.+[BCDĐGHKLMNPQRSTVXỊÌÍỈĨ\s])(?P<roman>I)$")

_NUMBERED = re.compile(r"^(?P<num>\d+(?:\.\d+)*)[.)]\s+(?P<name>[^\W\d_].*)$")

_THEORY_KEYWORD = re.compile(
    r"^(?:Định nghĩa|Định lí|Định lý|Tính chất|Hệ quả)(?:\s+\d+)?[.:]?\s*(?P<extra>.*)$",
    re.I,
)
_NOTE_KEYWORD = re.compile(
    r"^(?:Nhận xét|Chú ý|Ghi nhớ|Lưu ý|Ý nghĩa)(?:\s+\d+)?[.:]?\s*(?P<extra>.*)$",
    re.I,
)
_QUICK_TRICK_KEYWORD = re.compile(
    r"^(?:(?:Một số\s+)?công thức giải nhanh|Mẹo giải nhanh|Tính chất đặc biệt|Phương pháp giải nhanh|Bấm máy(?: casio)?|Công thức tính nhanh)(?:\s+\d+)?[.:]?\s*(?P<extra>.*)$",
    re.I,
)
_STEP_KEYWORD = re.compile(r"^Bước\s+0?(?P<num>\d{1,2})(?:\s*[.:]\s*|\s+)(?P<text>.+)$", re.I)
_EXAMPLE_KEYWORD = re.compile(r"^Ví dụ(?:\s+\d+(?:\.\d+)*)?[.:]?\s*(?P<extra>.*)$", re.I)

_TRIVIAL_FORMULAS = {
    "y=f(x)", "y=g(x)", "y=h(x)", "y=ƒ(x)", "x=x0", "y=y0",
    "x=a", "x=b", "x=c", "x=0", "y=0",
}


def _has_diacritic(text: str) -> bool:
    return any(ord(c) > 127 and c.isalpha() for c in text)


def _is_uppercase_vietnamese_heading(text: str) -> bool:
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) < 3 or len(cleaned) > 140:
        return False
    if cleaned != cleaned.upper() or not _has_diacritic(cleaned):
        return False
    if any(op in cleaned for op in ("=", "≠", "<", ">", "≤", "≥", "⊂", "∈", "∫", "→")):
        return False
    if cleaned.startswith(("TRANG ", "BƯỚC ", "CÁCH ", "TỔ TOÁN", "BẢN ĐỒ", "CHƯƠNG")):
        return False
    return True


def score_line_heading(
    line: TextLine,
    page_lines: list[TextLine],
    line_index: int,
    median_height: float,
) -> ScoredHeading | None:
    """Evaluate multiple signals to score if line is a structural heading."""
    if line.is_repeated_header_or_footer:
        return None
    raw = line.raw_text
    txt = line.text
    if len(txt) > 200 or not is_reliable_text(txt):
        return None

    score = 0.0

    # 1. Typographic signal
    rel_height = line.height / max(1.0, median_height)
    if rel_height >= 1.4:
        score += 5.0
    elif rel_height >= 1.2:
        score += 3.0

    # 2. Multi-line Chapter detection (e.g. CHƯƠNG \n 4 \n CÔNG THỨC...)
    if _CHAPTER_WORD_ONLY.fullmatch(txt) and line_index + 2 < len(page_lines):
        next_1 = page_lines[line_index + 1].text
        next_2 = page_lines[line_index + 2].text
        if _CHAPTER_NUM_ONLY.fullmatch(next_1) and _is_uppercase_vietnamese_heading(next_2):
            combined_title = f"{txt.title()} {next_1}. {next_2}"
            if line_index + 3 < len(page_lines) and _is_uppercase_vietnamese_heading(page_lines[line_index + 3].text):
                extra = page_lines[line_index + 3].text
                if extra != next_2:
                    combined_title = f"{combined_title} - {extra}"
            return ScoredHeading(
                line=line,
                title=combined_title,
                clean_title=combined_title,
                source_quote=page_lines[line_index + 2].raw_text,
                level=HeadingLevel.CHAPTER,
                role=PedagogicalRole.CHAPTER,
                score=15.0,
            )

    # 2b. Multi-line or Standalone Large Uppercase Vietnamese Chapter Banners
    is_roman_line = any(txt.startswith(r + " ") or txt.startswith(r + ".") for r in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"))
    if not is_roman_line and _is_uppercase_vietnamese_heading(txt) and (rel_height >= 1.4 or line.height >= 14.0):
        # Check if this line is continuation of a previous banner
        if line_index > 0:
            prev_l = page_lines[line_index - 1]
            if _is_uppercase_vietnamese_heading(prev_l.text) and (prev_l.height >= 14.0 or prev_l.height / max(1.0, median_height) >= 1.4):
                return None

        combined_title = txt
        combined_quote = raw
        if line_index + 1 < len(page_lines):
            next_l = page_lines[line_index + 1]
            if _is_uppercase_vietnamese_heading(next_l.text) and (next_l.height >= 13.0 or next_l.height / max(1.0, median_height) >= 1.3):
                # If next_l has Roman prefix like 'I VECTƠ...', strip the Roman prefix for the chapter name
                cleaned_next = re.sub(r"^[IVX]+\s+", "", next_l.text)
                if txt.upper() in cleaned_next.upper():
                    combined_title = cleaned_next
                else:
                    combined_title = f"{txt} {cleaned_next}"
                combined_quote = f"{raw} {next_l.raw_text}"

        level = HeadingLevel.CHAPTER if not combined_title.upper().startswith(("CÁC CÔNG THỨC", "BẢNG CÔNG THỨC")) else HeadingLevel.TOPIC
        role = PedagogicalRole.CHAPTER if level == HeadingLevel.CHAPTER else PedagogicalRole.THEORY
        return ScoredHeading(
            line=line,
            title=combined_title,
            clean_title=combined_title,
            source_quote=combined_quote,
            level=level,
            role=role,
            score=14.0 + score,
        )

    # 3. Explicit Chapter single line
    chap_match = _CHAPTER_PREFIX.fullmatch(txt)
    if chap_match and len(txt) <= 140:
        return ScoredHeading(
            line=line,
            title=txt,
            clean_title=txt,
            source_quote=raw,
            level=HeadingLevel.CHAPTER,
            role=PedagogicalRole.CHAPTER,
            score=12.0 + score,
        )

    # 4. Part prefix (A. LÝ THUYẾT CHUNG, B. CÁC DẠNG BÀI TẬP)
    part_match = _PART_PREFIX.fullmatch(txt)
    if part_match:
        return ScoredHeading(
            line=line,
            title=txt,
            clean_title=txt,
            source_quote=raw,
            level=HeadingLevel.TOPIC,
            role=PedagogicalRole.THEORY,
            score=10.0,
        )

    # 5. Roman Numeral Topic (e.g. "I. BẢNG ĐẠO HÀM" or "GIÁ TRỊ LỚN NHẤT...III")
    for pat in (_ROMAN_SUFFIX, _ROMAN_SUFFIX_I, _ROMAN_PREFIX):
        rmatch = pat.fullmatch(txt)
        if rmatch:
            roman = rmatch.group("roman").strip()
            name = rmatch.group("name").strip(" .:-")
            if _is_uppercase_vietnamese_heading(name):
                display = f"{roman}. {name}"
                return ScoredHeading(
                    line=line,
                    title=display,
                    clean_title=display,
                    source_quote=raw,
                    level=HeadingLevel.TOPIC,
                    role=PedagogicalRole.THEORY,
                    score=11.0 + score,
                )

    # 6. Method / Problem Type (e.g. Dạng 1.1, Bài toán 1)
    method_match = _METHOD_PREFIX.match(txt)
    if method_match and len(txt) <= 140:
        return ScoredHeading(
            line=line,
            title=txt,
            clean_title=txt,
            source_quote=raw,
            level=HeadingLevel.SECTION,
            role=PedagogicalRole.METHOD,
            score=10.0 + score,
        )

    # 7. Pedagogical theory markers (Định nghĩa, Định lý, Tính chất...)
    theory_match = _THEORY_KEYWORD.match(txt)
    if theory_match and len(txt) <= 90:
        clean = txt.strip()
        extra = (theory_match.group("extra") or "").strip()
        # Enhance general "Định lý" with next number if separated
        if clean.endswith(".") and line_index + 1 < len(page_lines):
            nxt = page_lines[line_index + 1].text
            if nxt.isdigit() and len(nxt) <= 3:
                clean = f"{clean[:-1]} {nxt}"
                raw = f"{raw} {nxt}"
        elif not extra and line_index + 1 < len(page_lines):
            nxt = page_lines[line_index + 1].text.strip()
            if 3 <= len(nxt) <= 70 and not any(op in nxt for op in ("=", "∫", "dx", "•")):
                clean = f"{clean}: {nxt}"
                raw = f"{raw} {page_lines[line_index + 1].raw_text}"
        return ScoredHeading(
            line=line,
            title=clean,
            clean_title=clean,
            source_quote=raw,
            level=HeadingLevel.SUBSECTION,
            role=PedagogicalRole.THEORY,
            score=8.0 + score,
        )

    # 8. Notes / Observations (Nhận xét, Chú ý, Ghi nhớ, Ý nghĩa)
    note_match = _NOTE_KEYWORD.match(txt)
    if note_match and len(txt) <= 90:
        clean = txt.strip()
        extra = (note_match.group("extra") or "").strip()
        if not extra and line_index + 1 < len(page_lines):
            nxt = page_lines[line_index + 1].text.strip()
            # Do NOT attach next line if it is an arrow transition, special symbol, or another heading
            if (
                3 <= len(nxt) <= 70
                and not any(op in nxt for op in ("=", "∫", "dx", "•", "→", "►", "■", "□"))
                and not _NOTE_KEYWORD.match(nxt)
                and not _THEORY_KEYWORD.match(nxt)
                and not _METHOD_PREFIX.match(nxt)
            ):
                clean = f"{clean}: {nxt}"
                raw = f"{raw} {page_lines[line_index + 1].raw_text}"
        display_title = clean if clean.startswith("⚠️") else f"⚠️ {clean}"
        return ScoredHeading(
            line=line,
            title=display_title,
            clean_title=display_title,
            source_quote=raw,
            level=HeadingLevel.CARD,
            role=PedagogicalRole.NOTE,
            score=7.0 + score,
        )

    # 8b. Quick Tricks & Special Formulas (Mẹo giải nhanh, Công thức tính nhanh)
    quick_match = _QUICK_TRICK_KEYWORD.match(txt)
    if quick_match and len(txt) <= 120:
        clean = txt.strip()
        display_title = clean if clean.startswith("⚡") else f"⚡ {clean}"
        return ScoredHeading(
            line=line,
            title=display_title,
            clean_title=display_title,
            source_quote=raw,
            level=HeadingLevel.CARD,
            role=PedagogicalRole.QUICK_TRICK,
            score=8.5 + score,
        )

    # 8c. Step Procedure (Bước 1, Bước 2...)
    step_match = _STEP_KEYWORD.match(txt)
    if step_match and len(txt) <= 150:
        num = step_match.group("num")
        instruction = step_match.group("text").strip()
        display_title = f"Bước {num}: {instruction}"
        return ScoredHeading(
            line=line,
            title=display_title,
            clean_title=display_title,
            source_quote=raw,
            level=HeadingLevel.CARD,
            role=PedagogicalRole.STEP,
            score=6.5 + score,
        )

    # 9. Numbered section (1. ..., 2. ..., 1.1. ...)
    num_match = _NUMBERED.fullmatch(txt)
    if num_match and len(txt) <= 130:
        sec_num = num_match.group("num")
        sec_name = num_match.group("name").strip()
        # Reject multiple choice answers like "1. A.", "1. B", "10. D."
        if re.fullmatch(r"[A-D][.:)]?", sec_name):
            return None
        # Clean trailing garbled math
        sec_name = re.sub(r"\)[a-zA-Z0-9\s+\-=*/',;]+$", ")", sec_name).strip()
        words = sec_name.split()
        if 2 <= len(words) <= 18:
            prefix = f"{sec_num}." if not txt.startswith(f"{sec_num})") else f"{sec_num})"
            clean = f"{prefix} {sec_name}"
            depth = sec_num.count(".") + 1
            lvl = HeadingLevel.SECTION if depth == 1 else HeadingLevel.SUBSECTION
            return ScoredHeading(
                line=line,
                title=clean,
                clean_title=clean,
                source_quote=raw,
                level=lvl,
                role=PedagogicalRole.THEORY,
                score=7.0 + score,
            )

    # 10. Examples
    ex_match = _EXAMPLE_KEYWORD.fullmatch(txt)
    if ex_match and len(txt) <= 90:
        return ScoredHeading(
            line=line,
            title=txt,
            clean_title=txt,
            source_quote=raw,
            level=HeadingLevel.CARD,
            role=PedagogicalRole.EXAMPLE,
            score=6.0 + score,
        )

    # 11. Plain Formula filter (strict: only genuine standalone display math, NEVER running prose, indices, or table fragments)
    _PROSE_INDICATORS = (
        "được gọi là", "gọi là", "khi đó", "sao cho", "nếu", "với mọi",
        "tại điểm", "người ta", "hàm số", "đồ thị", "tính đạo hàm",
        "liên tục", "tồn tại", "kí hiệu", "bằng cách", "khoảng", "đoạn",
        "quy tắc", "bước", "nghịch biến", "đồng biến", "cực trị", "tiệm cận",
        "đường thẳng", "phương trình", "tọa độ", "cho hàm", "giả sử",
        "xét hàm", "ta có", "suy ra", "tương đương", "thỏa mãn", "nghiệm",
    )
    lower_txt = txt.casefold()
    if "=" in txt and len(txt) <= 110 and not any(op in txt for op in ("\uf028", "\uf8eb", "\uf8ec", "\uf8ed", "\uf8f6", "\uf8f7", "\uf8f8", "□", "•", "→")):
        if not any(indicator in lower_txt for indicator in _PROSE_INDICATORS):
            # Must not be an index list like (i = 1, 2, ..., n) or domain condition
            if re.search(r"\(?[a-zA-Z]\s*=\s*\d+[\s,.]+", txt) and "..." in txt:
                return None
            # Must not be multiple '=' without formula structure like 'x = a x = b'
            if txt.count("=") > 1 and not any(f in txt for f in ("lim", "int", "∫", "sin", "cos", "tan", "ln", "log", "e^")):
                return None
            # Reject broken formula fragments with empty parentheses or detached primes (e.g. "' tan ' cos = u")
            if re.search(r"\(\s*\)", txt) or re.match(r"^['\"`]", txt) or re.search(r"['\"`]\s*=", txt) or re.search(r"=\s*['\"`]", txt):
                return None
            if "tan" in txt and "cos" in txt and "'" in txt and "(" not in txt:
                return None
            lhs, _, rhs = txt.partition("=")
            lhs_s, rhs_s = lhs.strip(), rhs.strip()
            # Must look like a real mathematical identity (few words, math operators)
            words = [w for w in re.split(r"[^\w]+", txt) if w and not w.isnumeric()]
            if len(words) <= 5 and any(c.isalnum() for c in lhs_s) and any(c.isalnum() for c in rhs_s):
                compact = re.sub(r"\s+", "", txt).casefold()
                if compact not in _TRIVIAL_FORMULAS and not re.fullmatch(r"[xy]=[xyabc01]\d*", compact):
                    if not re.search(r"\bS\d+\b", txt) and lhs_s.casefold() not in ("dx", "du", "dt", "x", "y"):
                        if any(tok in txt for tok in ("'", "+", "-", "*", "/", "^", "lim", "sin", "cos", "ln", "int", "sqrt")):
                            return ScoredHeading(
                                line=line,
                                title=txt,
                                clean_title=txt,
                                source_quote=raw,
                                level=HeadingLevel.CARD,
                                role=PedagogicalRole.FORMULA,
                                score=5.0,
                                latex=txt,
                            )

    return None
