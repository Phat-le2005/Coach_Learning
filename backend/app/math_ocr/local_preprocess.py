"""Deterministic alternate image scales for optional, student-reviewed OCR retries.

These variants are never used to silently replace the first OCR result. The
on-demand request keeps CPU work low on machines with limited RAM.
"""
from __future__ import annotations

from io import BytesIO


def alternative_formula_pngs(png: bytes) -> tuple[bytes, bytes]:
    from PIL import Image

    with Image.open(BytesIO(png)) as source:
        source.load()
        image = source.convert("RGB")

    results: list[bytes] = []
    for numerator, denominator in ((1, 2), (3, 2)):
        size = (
            max(1, image.width * numerator // denominator),
            max(1, image.height * numerator // denominator),
        )
        resized = image.resize(size, Image.Resampling.LANCZOS)
        buffer = BytesIO()
        resized.save(buffer, format="PNG")
        results.append(buffer.getvalue())
    return results[0], results[1]
