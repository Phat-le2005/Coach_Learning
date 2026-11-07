from pathlib import Path
import fitz

def extract_pages(pdf_path: str) -> list[dict]:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy PDF: {path}")

    pages = []
    with fitz.open(path) as doc:
        for page_index, page in enumerate(doc):
            text = page.get_text("text", sort=True)
            pages.append({
                "page": page_index + 1,
                "text": text,
                "width": page.rect.width,
                "height": page.rect.height,
            })
    return pages
