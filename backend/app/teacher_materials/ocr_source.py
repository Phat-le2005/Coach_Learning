"""Validate uploads and wrap a still image in a lossless, single-page PDF."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from app.core.exceptions import ApplicationError

MAX_IMAGE_PIXELS = 25_000_000
OCR_DPI = 240


@dataclass(frozen=True)
class OcrSource:
    pdf: bytes
    page_count: int
    kind: str = "PDF"
    mime_type: str = "application/pdf"
    image_name: str | None = None


def normalize_source(filename: str, data: bytes) -> OcrSource:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ApplicationError(415, "INVALID_PDF", "Vui lòng chọn một tệp PDF hợp lệ.")
        from pypdf import PdfReader
        try:
            pdf = PdfReader(BytesIO(data))
            if pdf.is_encrypted or not len(pdf.pages):
                raise ValueError("Encrypted or empty PDF")
            return OcrSource(data, len(pdf.pages))
        except Exception as exc:
            raise ApplicationError(422, "UNREADABLE_PDF", "Không đọc được PDF. Hãy chọn PDF không khóa mật khẩu.") from exc
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise ApplicationError(415, "UNSUPPORTED_OCR_SOURCE", "OCR bài tập hỗ trợ PDF và ảnh PNG/JPG/JPEG.")

    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in {"PNG", "JPEG"} or getattr(source, "n_frames", 1) != 1:
                raise ApplicationError(415, "UNSUPPORTED_OCR_IMAGE", "Hãy chọn ảnh tĩnh PNG hoặc JPG/JPEG.")
            if source.width * source.height > MAX_IMAGE_PIXELS or max(source.size) > 20_000:
                raise ApplicationError(413, "OCR_IMAGE_TOO_LARGE", "Ảnh quá lớn. Hãy dùng ảnh không quá 25 triệu điểm ảnh.")
            source.load()
            mime = "image/png" if source.format == "PNG" else "image/jpeg"
            name = "source.original.png" if source.format == "PNG" else "source.original.jpg"
            oriented = ImageOps.exif_transpose(source).convert("RGBA")
            background = Image.new("RGBA", oriented.size, "white")
            rgb = Image.alpha_composite(background, oriented).convert("RGB")
            pdf = image_pdf(rgb)
        return OcrSource(pdf, 1, "IMAGE", mime, name)
    except ApplicationError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ApplicationError(422, "UNREADABLE_OCR_IMAGE", "Không đọc được ảnh. Hãy chọn lại ảnh PNG hoặc JPG/JPEG hợp lệ.") from exc


def image_pdf(image) -> bytes:
    # Avoid Pillow's PDF writer, which recompresses RGB pages as lossy JPEG.
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject
    writer = PdfWriter()
    width, height = image.size
    page_width, page_height = width * 72 / OCR_DPI, height * 72 / OCR_DPI
    page = writer.add_blank_page(width=page_width, height=page_height)
    pixels = DecodedStreamObject()
    pixels.set_data(image.tobytes())
    pixels.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"),
                   NameObject("/Width"): NumberObject(width), NameObject("/Height"): NumberObject(height),
                   NameObject("/ColorSpace"): NameObject("/DeviceRGB"), NameObject("/BitsPerComponent"): NumberObject(8)})
    encoded = pixels.flate_encode()
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): DictionaryObject({
        NameObject("/SourceImage"): writer._add_object(encoded)})})
    content = DecodedStreamObject()
    content.set_data(f"q {page_width:.8f} 0 0 {page_height:.8f} 0 0 cm /SourceImage Do Q".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
