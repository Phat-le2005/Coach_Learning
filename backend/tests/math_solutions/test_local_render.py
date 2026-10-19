"""Rasterization regression: execute actual Pillow image path (never stub)."""
from io import BytesIO
from uuid import uuid4

import pytest

Image = pytest.importorskip("PIL.Image")
from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkPoint, InkStroke
from app.math_ocr.local_render import render_formula_png


def stroke(*coords, tool="PEN", width=2):
    return InkStroke(
        id=uuid4(), tool=tool, color="#000000", width=width,
        points=[InkPoint(x=x, y=y) for x, y in coords],
    )


def test_real_png_is_cropped_rgb_with_visible_ink():
    png = render_formula_png([stroke((0.30, 0.20), (0.33, 0.22))])
    assert png[:4] == bytes([137, 80, 78, 71])
    assert len(png) < 1_000_000
    image = Image.open(BytesIO(png))
    image.load()
    assert image.mode == "RGB"
    assert 1 <= image.width < 794
    assert 1 <= image.height < 1123
    pixels = list(image.getdata())
    assert any(pixel != (255, 255, 255) for pixel in pixels)
    assert any(pixel == (255, 255, 255) for pixel in pixels)


def test_highlighter_is_ignored_and_cannot_enlarge_crop():
    ink = stroke((0.30, 0.20), (0.32, 0.22))
    highlight = stroke((0.95, 0.95), (0.98, 0.98), tool="HIGHLIGHTER", width=24)
    plain = Image.open(BytesIO(render_formula_png([ink])))
    decorated = Image.open(BytesIO(render_formula_png([highlight, ink])))
    assert plain.size == decorated.size
    assert plain.tobytes() == decorated.tobytes()


def test_render_single_pen_dot_and_edge_bounds():
    for coords in [((0.0, 0.0),), ((1.0, 1.0),), ((0.5, 0.5),)]:
        image = Image.open(BytesIO(render_formula_png([stroke(*coords)])))
        assert image.width > 0 and image.height > 0
        assert any(pixel != (255, 255, 255) for pixel in image.getdata())


def test_no_pen_or_excessive_points_fails_closed():
    with pytest.raises(ApplicationError) as ex:
        render_formula_png([stroke((0.1, 0.1), tool="HIGHLIGHTER")])
    assert ex.value.code == "NO_PEN_STROKES_FOR_OCR"
    oversized = [stroke(*[(0.1, 0.1)] * 3000) for _ in range(6)]
    with pytest.raises(ApplicationError) as ex2:
        render_formula_png(oversized)
    assert ex2.value.code == "OCR_STROKES_TOO_LARGE"
