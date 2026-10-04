"""PDF page-by-page text extraction using pypdf."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pypdf

from app.question_acquisition.models import QuestionAcquisitionExtractionStatus


@dataclass
class ExtractedPage:
    page_number: int
    text: str
    text_sha256: str
    char_count: int


@dataclass
class ExtractedPdfResult:
    page_count: int | None = None
    pages: list[ExtractedPage] = field(default_factory=list)
    extraction_status: QuestionAcquisitionExtractionStatus = QuestionAcquisitionExtractionStatus.PENDING
    warnings: list[str] = field(default_factory=list)
    error_message: str | None = None


class PdfExtractor:
    """Extracts text from PDF page by page without OCR."""

    @classmethod
    def extract_from_bytes(cls, data: bytes) -> ExtractedPdfResult:
        return cls.extract_from_stream(BytesIO(data))

    @classmethod
    def extract_from_file(cls, path: Path | str) -> ExtractedPdfResult:
        with open(path, "rb") as f:
            return cls.extract_from_stream(f)

    @classmethod
    def extract_from_stream(cls, stream: BinaryIO) -> ExtractedPdfResult:
        try:
            reader = pypdf.PdfReader(stream)
            if reader.is_encrypted:
                try:
                    # Attempt empty password decryption
                    decrypt_res = reader.decrypt("")
                    if decrypt_res == pypdf.errors.PasswordResult.NOT_DECRYPTED:
                        return ExtractedPdfResult(
                            page_count=None,
                            extraction_status=QuestionAcquisitionExtractionStatus.FAILED,
                            error_message="PDF is encrypted and cannot be opened.",
                        )
                except Exception as exc:
                    return ExtractedPdfResult(
                        page_count=None,
                        extraction_status=QuestionAcquisitionExtractionStatus.FAILED,
                        error_message=f"Encrypted PDF decryption failed: {exc}",
                    )

            page_count = len(reader.pages)
            if page_count == 0:
                return ExtractedPdfResult(
                    page_count=None,
                    extraction_status=QuestionAcquisitionExtractionStatus.FAILED,
                    error_message="PDF contains zero pages.",
                )

            extracted_pages: list[ExtractedPage] = []
            warnings: list[str] = []
            empty_page_count = 0

            for idx, page in enumerate(reader.pages, start=1):
                try:
                    raw_text = page.extract_text() or ""
                except Exception as exc:
                    raw_text = ""
                    warnings.append(f"Page {idx} text extraction error: {exc}")

                clean_text = raw_text.strip()
                char_count = len(clean_text)
                if char_count == 0:
                    empty_page_count += 1
                    warnings.append(f"Page {idx} has no extractable text.")

                text_sha256 = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
                extracted_pages.append(
                    ExtractedPage(
                        page_number=idx,
                        text=clean_text,
                        text_sha256=text_sha256,
                        char_count=char_count,
                    )
                )

            if empty_page_count == 0:
                status = QuestionAcquisitionExtractionStatus.COMPLETE
            else:
                status = QuestionAcquisitionExtractionStatus.PARTIAL

            return ExtractedPdfResult(
                page_count=page_count,
                pages=extracted_pages,
                extraction_status=status,
                warnings=warnings,
            )

        except Exception as exc:
            return ExtractedPdfResult(
                page_count=None,
                extraction_status=QuestionAcquisitionExtractionStatus.FAILED,
                error_message=f"Failed to parse PDF: {exc}",
            )
