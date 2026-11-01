"""Unit tests for inkml_to_mathcanvas converter."""

import unittest
from inkml_to_mathcanvas import (
    parse_inkml_content,
    normalize_traces_to_mathcanvas,
    convert_inkml_to_fixture,
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


class TestInkmlToMathcanvas(unittest.TestCase):
    def test_parse_inkml_content(self):
        parsed = parse_inkml_content(SAMPLE_INKML)
        self.assertEqual(parsed["annotations"]["label"], r"\frac{a}{b}")
        self.assertEqual(parsed["annotations"]["inkCreationMethod"], "human")
        self.assertEqual(len(parsed["raw_traces"]), 3)
        self.assertEqual(parsed["raw_traces"][0]["id"], "0")
        self.assertEqual(len(parsed["raw_traces"][0]["points"]), 2)
        # Check first point coords
        pt0 = parsed["raw_traces"][0]["points"][0]
        self.assertEqual(pt0[0], 100.0)
        self.assertEqual(pt0[1], 200.0)
        self.assertEqual(pt0[2], 0.0)

    def test_normalize_traces_aspect_ratio_and_bounds(self):
        parsed = parse_inkml_content(SAMPLE_INKML)
        strokes = normalize_traces_to_mathcanvas(parsed["raw_traces"])

        self.assertEqual(len(strokes), 3)
        self.assertEqual(strokes[0]["tool"], "PEN")
        self.assertEqual(strokes[0]["width"], 2)

        # Stroke point count preservation
        self.assertEqual(len(strokes[0]["points"]), 2)
        self.assertEqual(len(strokes[1]["points"]), 2)
        self.assertEqual(len(strokes[2]["points"]), 2)

        # Coordinate bounds within [0, 1]
        for s in strokes:
            for p in s["points"]:
                self.assertGreaterEqual(p["x"], 0.0)
                self.assertLessEqual(p["x"], 1.0)
                self.assertGreaterEqual(p["y"], 0.0)
                self.assertLessEqual(p["y"], 1.0)
                self.assertEqual(p["pressure"], 0.5)

        # Aspect ratio preservation:
        # Original: x spans [90, 150] -> 60, y spans [200, 290] -> 90. Ratio = 60 / 90 = 2/3
        orig_xs = [p[0] for t in parsed["raw_traces"] for p in t["points"]]
        orig_ys = [p[1] for t in parsed["raw_traces"] for p in t["points"]]
        orig_ratio = (max(orig_xs) - min(orig_xs)) / (max(orig_ys) - min(orig_ys))

        conv_xs = [p["x"] for s in strokes for p in s["points"]]
        conv_ys = [p["y"] for s in strokes for p in s["points"]]
        conv_ratio = (max(conv_xs) - min(conv_xs)) / (max(conv_ys) - min(conv_ys))

        self.assertAlmostEqual(orig_ratio, conv_ratio, places=4)

    def test_convert_inkml_to_fixture_structure(self):
        fixture = convert_inkml_to_fixture(SAMPLE_INKML, source_path="test/sample.inkml")

        self.assertEqual(fixture["fixtureKind"], "INKML_EXTERNAL")
        self.assertEqual(fixture["schemaVersion"], 1)
        self.assertEqual(fixture["sampleId"], "sample_frac_1")
        self.assertEqual(fixture["provenance"]["inkCreationMethod"], "human")
        self.assertEqual(fixture["stats"]["numSourceStrokes"], 3)
        self.assertEqual(fixture["stats"]["numConvertedStrokes"], 3)
        self.assertEqual(fixture["stats"]["numSourcePoints"], 6)
        self.assertEqual(fixture["stats"]["numConvertedPoints"], 6)


if __name__ == "__main__":
    unittest.main()
