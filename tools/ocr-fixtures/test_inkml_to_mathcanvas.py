#!/usr/bin/env python3
"""Offline smoke tests for the external InkML sample converter."""
import unittest

from inkml_to_mathcanvas import read_inkml, to_mathcanvas


class InkMlConverterTests(unittest.TestCase):
    def test_single_handwritten_trace_and_label(self):
        sample = b'''<ink xmlns="http://www.w3.org/2003/InkML">
           <annotation type="normalizedLabel">x+1</annotation>
           <trace id="0">3 10, 8 12, 13 10</trace>
           <trace id="1">15 20, 20 18, 25 20</trace>
        </ink>'''
        traces, label = read_inkml(sample)
        self.assertEqual(label, "x+1")
        self.assertEqual(len(traces), 2)
        strokes = to_mathcanvas(traces)
        self.assertEqual([s["id"] for s in strokes], ["inkml-0", "inkml-1"])
        self.assertTrue(all(s["tool"] == "PEN" for s in strokes))
        self.assertTrue(all(0 <= p["x"] <= 1 and 0 <= p["y"] <= 1
                            for s in strokes for p in s["points"]))

    def test_empty_trace_is_rejected(self):
        sample = b'<ink xmlns="http://www.w3.org/2003/InkML"><trace id="0">not numbers</trace></ink>'
        with self.assertRaisesRegex(ValueError, "no supported XY traces"):
            read_inkml(sample)


if __name__ == "__main__":
    unittest.main()
