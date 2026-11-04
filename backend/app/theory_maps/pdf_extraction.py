"""Local PDF extraction with an optional Docling fallback for textless pages."""

from io import BytesIO

from pypdf import PdfReader

from app.core.exceptions import ApplicationError

MAX_PAGES = 80
MAX_TEXT_CHARS = 320_000


def analyze_page_statuses(page_texts: list[str]) -> list[dict]:
    """Classify the extraction state of each page to maintain source transparency."""
    statuses = []
    for index, page in enumerate(page_texts, 1):
        stripped = page.strip()
        pua_count = sum(0xE000 <= ord(char) <= 0xF8FF for char in page)
        has_replacement = "\ufffd" in page
        
        if not stripped:
            status = "EMPTY"
        elif has_replacement or pua_count >= 8:
            status = "HAS_PUA_MATH"
        else:
            status = "PROCESSED_NATIVE"

        statuses.append({
            "page": index,
            "status": status,
            "char_count": len(page),
            "pua_count": pua_count,
            "has_replacement": has_replacement,
        })
    return statuses


def unreliable_text_pages(page_texts: list[str]) -> list[int]:
    """Flag likely font-encoded math; never guess the intended symbols."""
    return [index for index, page in enumerate(page_texts, 1)
            if not page.strip() or "\ufffd" in page or sum(0xE000 <= ord(char) <= 0xF8FF for char in page) >= 8]


def _docling_pages(content: bytes, page_count: int) -> list[str]:
    try:
        from docling.datamodel.base_models import InputFormat, DocumentStream
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise ApplicationError(422, "PDF_OCR_NOT_CONFIGURED",
                               "A PDF page has no text layer. Install the optional local Docling OCR worker or use a text PDF.") from exc
    try:
        options = PdfPipelineOptions(do_ocr=True, do_table_structure=False,
                                     do_formula_enrichment=False, document_timeout=600)
        converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
        document = converter.convert(DocumentStream(name="theory.pdf", stream=BytesIO(content)),
                                     max_num_pages=MAX_PAGES, max_file_size=len(content)).document
        return [document.export_to_text(page_no=page, traverse_pictures=True).strip()
                for page in range(1, page_count + 1)]
    except Exception as exc:
        raise ApplicationError(422, "PDF_OCR_FAILED", "Local PDF OCR could not read this document.") from exc


def read_pdf_pages(content: bytes) -> list[str]:
    """Validate the original PDF and read its native layer without requiring OCR."""
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ApplicationError(422, "ENCRYPTED_PDF", "Encrypted PDFs are not supported.")
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise ApplicationError(422, "PDF_PAGE_LIMIT", f"PDF must contain 1–{MAX_PAGES} pages.")
        native = []
        for page in reader.pages:
            try:
                native.append((page.extract_text() or "").strip())
            except Exception:
                # A broken text layer must not prevent reading the original page.
                native.append("")
    except ApplicationError:
        raise
    except Exception as exc:
        raise ApplicationError(422, "PDF_PARSE_FAILED", "PDF text could not be read.") from exc
    return native


def extract_page_texts(content: bytes) -> list[str]:
    native = read_pdf_pages(content)
    has_empty = any(not page for page in native)
    all_empty = all(not page for page in native)
    
    if has_empty:
        try:
            ocr = _docling_pages(content, len(native))
            native = [text or ocr[index] for index, text in enumerate(native)]
        except ApplicationError:
            # If all pages are empty and OCR fails, raise. If only some pages are empty
            # (e.g. blank page or cover), preserve the readable pages.
            if all_empty:
                raise
    if all(not page for page in native):
        raise ApplicationError(422, "PDF_TEXT_REQUIRED", "The PDF needs readable text for cited map nodes.")
    if sum(map(len, native)) > MAX_TEXT_CHARS:
        raise ApplicationError(422, "PDF_TEXT_LIMIT", "PDF contains too much text for this review flow.")
    return native
