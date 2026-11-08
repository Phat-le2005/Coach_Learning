from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfReader

from app.core.exceptions import ApplicationError
from app.teacher_materials.ocr_source import normalize_source


def image_bytes(fmt="PNG", *, exif=None):
    image = Image.new("RGB", (80, 40), (25, 110, 195))
    output = BytesIO()
    image.save(output, fmt, **({"exif": exif} if exif else {}))
    return output.getvalue()


@pytest.mark.parametrize("filename,fmt,mime", [("question.png", "PNG", "image/png"), ("question.JPG", "JPEG", "image/jpeg"), ("question.jpeg", "JPEG", "image/jpeg")])
def test_images_use_one_page_and_keep_decoded_pixels(filename, fmt, mime):
    data = image_bytes(fmt)
    source = normalize_source(filename, data)
    assert source.kind == "IMAGE" and source.page_count == 1 and source.mime_type == mime
    reader = PdfReader(BytesIO(source.pdf))
    assert len(reader.pages) == 1
    embedded = reader.pages[0].images[0].image.convert("RGB")
    with Image.open(BytesIO(data)) as original:
        assert embedded.size == original.size
        assert embedded.tobytes() == original.convert("RGB").tobytes()


def test_image_exif_rotation_and_transparency_are_readable_on_white():
    exif = Image.Exif()
    exif[274] = 6
    source = normalize_source("phone.jpg", image_bytes("JPEG", exif=exif))
    assert PdfReader(BytesIO(source.pdf)).pages[0].images[0].image.size == (40, 80)
    transparent = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    transparent.putpixel((1, 1), (20, 30, 40, 255))
    output = BytesIO(); transparent.save(output, "PNG")
    source = normalize_source("transparent.png", output.getvalue())
    embedded = PdfReader(BytesIO(source.pdf)).pages[0].images[0].image.convert("RGB")
    assert embedded.getpixel((0, 0)) == (255, 255, 255)
    assert embedded.getpixel((1, 1)) == (20, 30, 40)


@pytest.mark.parametrize("filename,data", [("fake.png", b"not-an-image"), ("fake.pdf", image_bytes()), ("animation.gif", image_bytes("GIF")), ("disguised.png", image_bytes("GIF"))])
def test_spoofed_and_unsupported_images_do_not_enter_ocr(filename, data):
    with pytest.raises(ApplicationError):
        normalize_source(filename, data)


def test_oversized_image_is_rejected_before_decoding(monkeypatch):
    monkeypatch.setattr("app.teacher_materials.ocr_source.MAX_IMAGE_PIXELS", 100)
    with pytest.raises(ApplicationError) as exc:
        normalize_source("large.png", image_bytes())
    assert exc.value.status_code == 413
