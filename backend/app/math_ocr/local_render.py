"""Rasterize normalized EduMS handwriting to a tight, high-contrast PNG.

Only PEN strokes are mathematical content. Cropping avoids wasting the model
input on a blank A4 sheet. Pillow is an optional dependency for local OCR.
"""
from __future__ import annotations

from io import BytesIO

from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkStroke

WIDTH, HEIGHT = 794, 1123
MAX_PNG_BYTES = 1_000_000


def render_formula_png(strokes: list[InkStroke]) -> bytes:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise ApplicationError(
            503, "OCR_LOCAL_DEPENDENCY_MISSING",
            "Local OCR requires Pillow. Install the optional OCR dependencies.",
        ) from exc
    pens = [s for s in strokes if s.tool == "PEN"]
    if not pens:
        raise ApplicationError(422, "NO_PEN_STROKES_FOR_OCR", "Select pen strokes for OCR.")
    if len(pens) > 400 or sum(len(s.points) for s in pens) > 15000:
        raise ApplicationError(413, "OCR_STROKES_TOO_LARGE", "Too many strokes selected.")

    xmin, ymin, xmax, ymax = WIDTH, HEIGHT, 0.0, 0.0
    for stroke in pens:
        for p in stroke.points:
            x, y = min(p.x * WIDTH, WIDTH - 1), min(p.y * HEIGHT, HEIGHT - 1)
            xmin, ymin = min(xmin, x), min(ymin, y)
            xmax, ymax = max(xmax, x), max(ymax, y)
    margin = 24
    left, top = max(0, int(xmin) - margin), max(0, int(ymin) - margin)
    right = min(WIDTH, int(xmax) + margin + 1)
    bottom = min(HEIGHT, int(ymax) + margin + 1)
    image = Image.new("RGB", (max(1, right - left), max(1, bottom - top)), "white")
    canvas = ImageDraw.Draw(image)
    for stroke in pens:
        coords = [
            (round(min(p.x * WIDTH, WIDTH - 1) - left),
             round(min(p.y * HEIGHT, HEIGHT - 1) - top))
            for p in stroke.points
        ]
        # Preserve pen thickness approximately, clamp tiny/nonsensical values.
        thickness = max(2, min(12, int(round(stroke.width * 1.5))))
        if len(coords) == 1:
            x, y = coords[0]
            radius = max(1, thickness // 2)
            canvas.ellipse((x - radius, y - radius, x + radius, y + radius), fill="black")
        else:
            canvas.line(coords, fill="black", width=thickness, joint="curve")
            radius = max(1, thickness // 2)
            for x, y in (coords[0], coords[-1]):
                canvas.ellipse((x - radius, y - radius, x + radius, y + radius), fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image_bytes = buffer.getvalue()
    if len(image_bytes) > MAX_PNG_BYTES:
        raise ApplicationError(413, "OCR_IMAGE_TOO_LARGE", "OCR image is too large.")
    return image_bytes
