from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import re

@dataclass(frozen=True, slots=True)
class ExtractedMaterialItem:
    content: str
    content_hash: str
    order_index: int
    page_start: int | None = None
    page_end: int | None = None
    confident: bool = False

@dataclass(frozen=True, slots=True)
class MaterialExtractionResult:
    items: tuple[ExtractedMaterialItem, ...]
    page_count: int | None
    text_empty: bool = False

class TeacherMaterialExtractor:
    _MARKER = re.compile(r"(?im)^\s*(?:Câu|Bài)\s+\d+[\s.:)]*")

    def extract(self, data: bytes, mime_type: str) -> MaterialExtractionResult:
        if mime_type == "text/plain":
            text = data.decode("utf-8-sig", errors="replace")
            return self._segment(text, None)
        if mime_type != "application/pdf": raise ValueError("Unsupported material MIME type")
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data)); pages = [(page.extract_text() or "").strip() for page in reader.pages]
        text = "\n".join(x for x in pages if x)
        if not text.strip(): return MaterialExtractionResult((), len(reader.pages), True)
        return self._segment(text, len(reader.pages))

    def _segment(self, text: str, pages: int | None) -> MaterialExtractionResult:
        text = text.strip()
        if not text: return MaterialExtractionResult((), pages, True)
        matches = list(self._MARKER.finditer(text)); parts: list[str]
        confident = len(matches) >= 2
        if matches:
            parts = [text[m.start():(matches[i+1].start() if i+1 < len(matches) else len(text))].strip() for i, m in enumerate(matches)]
            prefix = text[:matches[0].start()].strip()
            if prefix: parts[0] = prefix + "\n" + parts[0]
        else: parts = [text]
        items = tuple(ExtractedMaterialItem(content=x, content_hash=sha256(x.encode("utf-8")).hexdigest(), order_index=i, confident=confident) for i, x in enumerate(parts) if x)
        return MaterialExtractionResult(items, pages, False)
