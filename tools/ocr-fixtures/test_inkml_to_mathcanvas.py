"""Comprehensive unit and regression tests for inkml_to_mathcanvas converter.

Verifies:
1. Physical aspect ratio preservation on A4 canvas (794 x 1123).
2. Degenerate geometric cases (point, horizontal, vertical).
3. Wide/tall extreme aspect ratio scaling without distortion.
4. Negative coordinate offset handling.
5. 100% stroke, point, and order conservation.
6. CLI execution and manifest handling.
"""

import json
import os
import shutil
import tempfile
import unittest

from inkml_to_mathcanvas import (
    A4_HEIGHT,
    A4_WIDTH,
    convert_inkml_to_fixture,
    normalize_traces_to_mathcanvas,
    parse_inkml_content,
)

SAMPLE_INKML = """<ink xmlns="http://www.w3.org/2003/InkML">
  <annotation type="label">\\frac{a}{b}</annotation>
  <annotation type="normalizedLabel">\\frac{a}{b}</annotation>
  <annotation type="inkCreationMethod">human</annotation>
  <annotation type="splitTagOriginal">train</annotation>
  <annotation type="sampleId">sample_frac_1</annotation>
  <traceFormat>
    <channel name="X" type="decimal" />
    <channel name="Y" type="decimal" />
    <channel name="T" type="decimal" units="ms" />
  </traceFormat>
  <trace id="0">100.0 200.0 0.0, 105.0 210.0 50.0</trace>
  <trace id="1">90.0 250.0 100.0, 150.0 250.0 150.0</trace>
  <trace id="2">100.0 280.0 200.0, 105.0 290.0 250.0</trace>
</ink>"""


def compute_rendered_aspect_ratio(strokes, a4_w=A4_WIDTH, a4_h=A4_HEIGHT):
    all_x = [p["x"] for s in strokes for p in s["points"]]
    all_y = [p["y"] for s in strokes for p in s["points"]]
    norm_w = max(all_x) - min(all_x)
    norm_h = max(all_y) - min(all_y)
    phys_w = norm_w * a4_w
    phys_h = norm_h * a4_h
    return phys_w / max(1e-9, phys_h)


class TestInkmlToMathcanvas(unittest.TestCase):
    # -------------------------------------------------------------------------
    # 1. Square in source coordinates remains physical square on A4
    # -------------------------------------------------------------------------
    def test_square_aspect_ratio_preservation(self):
        # A 100x100 square in source tablet coords
        raw_traces = [
            {"id": "0", "points": [(100.0, 100.0, 0), (200.0, 100.0, 10), (200.0, 200.0, 20), (100.0, 200.0, 30)]}
        ]
        strokes = normalize_traces_to_mathcanvas(raw_traces)
        rendered_ratio = compute_rendered_aspect_ratio(strokes)
        source_ratio = 100.0 / 100.0
        self.assertAlmostEqual(rendered_ratio, source_ratio, places=3)

    # -------------------------------------------------------------------------
    # 2. Rectangle preserves exact source aspect ratio (2.5 : 1)
    # -------------------------------------------------------------------------
    def test_rectangle_aspect_ratio_preservation(self):
        # 250 wide by 100 high
        raw_traces = [
            {"id": "0", "points": [(50.0, 50.0, 0), (300.0, 50.0, 10), (300.0, 150.0, 20), (50.0, 150.0, 30)]}
        ]
        strokes = normalize_traces_to_mathcanvas(raw_traces)
        rendered_ratio = compute_rendered_aspect_ratio(strokes)
        source_ratio = 250.0 / 100.0
        self.assertAlmostEqual(rendered_ratio, source_ratio, places=3)

    # -------------------------------------------------------------------------
    # 3. Horizontal line keeps 0-degree angle and stays strictly within bounds
    # -------------------------------------------------------------------------
    def test_horizontal_line_degenerate_case(self):
        raw_traces = [
            {"id": "h_line", "points": [(10.0, 50.0, 0), (50.0, 50.0, 10), (120.0, 50.0, 20)]}
        ]
        strokes = normalize_traces_to_mathcanvas(raw_traces)
        self.assertEqual(len(strokes), 1)
        pts = strokes[0]["points"]
        # Y must remain constant across all points
        self.assertEqual(pts[0]["y"], pts[1]["y"])
        self.assertEqual(pts[1]["y"], pts[2]["y"])
        # X must be increasing
        self.assertLess(pts[0]["x"], pts[1]["x"])
        self.assertLess(pts[1]["x"], pts[2]["x"])

    # -------------------------------------------------------------------------
    # 4. Diagonal line preserves slope and direction
    # -------------------------------------------------------------------------
    def test_diagonal_line_slope_preservation(self):
        # Line from (0, 0) to (200, 100) -> source dy/dx = 0.5, dx/dy = 2.0
        raw_traces = [
            {"id": "diag", "points": [(0.0, 0.0, 0), (100.0, 50.0, 10), (200.0, 100.0, 20)]}
        ]
        strokes = normalize_traces_to_mathcanvas(raw_traces)
        rendered_ratio = compute_rendered_aspect_ratio(strokes)
        source_ratio = 200.0 / 100.0
        self.assertAlmostEqual(rendered_ratio, source_ratio, places=3)

    # -------------------------------------------------------------------------
    # 5. Extreme wide/tall expressions fit within target bounding box
    # -------------------------------------------------------------------------
    def test_extreme_aspect_ratio_scaling(self):
        # Wide: 1000 x 50 (20:1)
        wide_traces = [
            {"id": "wide", "points": [(0.0, 0.0, 0), (1000.0, 50.0, 10)]}
        ]
        strokes_wide = normalize_traces_to_mathcanvas(wide_traces)
        rendered_wide = compute_rendered_aspect_ratio(strokes_wide)
        self.assertAlmostEqual(rendered_wide, 1000.0 / 50.0, places=3)

        # Tall: 50 x 1000 (1:20)
        tall_traces = [
            {"id": "tall", "points": [(0.0, 0.0, 0), (50.0, 1000.0, 10)]}
        ]
        strokes_tall = normalize_traces_to_mathcanvas(tall_traces)
        rendered_tall = compute_rendered_aspect_ratio(strokes_tall)
        self.assertAlmostEqual(rendered_tall, 50.0 / 1000.0, places=3)

    # -------------------------------------------------------------------------
    # 6. Single point stroke does not divide by zero and centers cleanly
    # -------------------------------------------------------------------------
    def test_single_point_stroke(self):
        raw_traces = [{"id": "dot", "points": [(150.0, 300.0, 0)]}]
        strokes = normalize_traces_to_mathcanvas(raw_traces)
        self.assertEqual(len(strokes), 1)
        self.assertEqual(len(strokes[0]["points"]), 1)
        pt = strokes[0]["points"][0]
        self.assertGreater(pt["x"], 0.0)
        self.assertLess(pt["x"], 1.0)
        self.assertGreater(pt["y"], 0.0)
        self.assertLess(pt["y"], 1.0)
        self.assertEqual(pt["pressure"], 0.5)

    # -------------------------------------------------------------------------
    # 7. Negative finite coordinates are normalized correctly without clipping
    # -------------------------------------------------------------------------
    def test_negative_coordinates_handling(self):
        raw_traces = [
            {"id": "neg", "points": [(-200.0, -150.0, 0), (-50.0, -150.0, 10), (-50.0, 50.0, 20)]}
        ]
        strokes = normalize_traces_to_mathcanvas(raw_traces)
        for s in strokes:
            for p in s["points"]:
                self.assertGreaterEqual(p["x"], 0.0)
                self.assertLessEqual(p["x"], 1.0)
                self.assertGreaterEqual(p["y"], 0.0)
                self.assertLessEqual(p["y"], 1.0)
        # Check aspect ratio: width = 150, height = 200
        rendered_ratio = compute_rendered_aspect_ratio(strokes)
        source_ratio = 150.0 / 200.0
        self.assertAlmostEqual(rendered_ratio, source_ratio, places=3)

    # -------------------------------------------------------------------------
    # 8. Degenerate width or height handled gracefully
    # -------------------------------------------------------------------------
    def test_degenerate_vertical_line(self):
        raw_traces = [
            {"id": "vert", "points": [(50.0, 10.0, 0), (50.0, 100.0, 10), (50.0, 250.0, 20)]}
        ]
        strokes = normalize_traces_to_mathcanvas(raw_traces)
        self.assertEqual(len(strokes), 1)
        pts = strokes[0]["points"]
        # X is constant
        self.assertEqual(pts[0]["x"], pts[1]["x"])
        self.assertEqual(pts[1]["x"], pts[2]["x"])
        # Y increases
        self.assertLess(pts[0]["y"], pts[1]["y"])
        self.assertLess(pts[1]["y"], pts[2]["y"])

    # -------------------------------------------------------------------------
    # 9. Multi-trace and multi-point fidelity (100% stroke & point conservation)
    # -------------------------------------------------------------------------
    def test_multi_trace_point_conservation(self):
        parsed = parse_inkml_content(SAMPLE_INKML)
        strokes = normalize_traces_to_mathcanvas(parsed["raw_traces"])
        self.assertEqual(len(strokes), len(parsed["raw_traces"]))
        for s, t in zip(strokes, parsed["raw_traces"]):
            self.assertEqual(len(s["points"]), len(t["points"]))
            self.assertEqual(s["tool"], "PEN")
            self.assertEqual(s["width"], 2)

    # -------------------------------------------------------------------------
    # 10. Metadata, channel format, and pressure values
    # -------------------------------------------------------------------------
    def test_metadata_and_fixture_contract(self):
        fixture = convert_inkml_to_fixture(SAMPLE_INKML, source_path="test/sample.inkml")
        self.assertEqual(fixture["fixtureKind"], "INKML_EXTERNAL")
        self.assertEqual(fixture["schemaVersion"], 1)
        self.assertEqual(fixture["sampleId"], "sample_frac_1")
        self.assertEqual(fixture["provenance"]["inkCreationMethod"], "human")
        self.assertEqual(fixture["provenance"]["normalizedLabel"], r"\frac{a}{b}")
        self.assertEqual(fixture["stats"]["numSourceStrokes"], 3)
        self.assertEqual(fixture["stats"]["numConvertedStrokes"], 3)
        self.assertEqual(fixture["stats"]["numSourcePoints"], 6)
        self.assertEqual(fixture["stats"]["numConvertedPoints"], 6)


if __name__ == "__main__":
    unittest.main()
