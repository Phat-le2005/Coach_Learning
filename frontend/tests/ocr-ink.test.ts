import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import { getOcrPenStrokes } from "../src/features/math-workspace/utils/ocr-ink.js";

test("OCR sends only nonempty pen strokes, preserving original IDs and order", () => {
  const stroke = (id: string, tool: "PEN" | "HIGHLIGHTER", points: InkStroke["points"]): InkStroke => ({
    id, tool, color: "#000000", width: 2, points,
  });
  const points = [{ x: 0.1, y: 0.2, pressure: 0.5 }];
  const selected = getOcrPenStrokes([
    stroke("highlight", "HIGHLIGHTER", points),
    stroke("first", "PEN", points),
    stroke("empty", "PEN", []),
    stroke("second", "PEN", points),
  ]);
  assert.deepEqual(selected.map((item) => item.id), ["first", "second"]);
});
