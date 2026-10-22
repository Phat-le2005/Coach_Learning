import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import { recognizeHandwrittenMath, toModelStrokes } from "../src/features/math-workspace/utils/handwritten-ocr.js";

const makeStroke = (tool: InkStroke["tool"], x: number, y: number): InkStroke => ({
  id: tool + x,
  tool,
  color: "#000000",
  width: 2,
  points: [{ x, y, pressure: 0.5 }],
});

test("CoMER input preserves pen order and page geometry without question hints", () => {
  const result = toModelStrokes([
    makeStroke("HIGHLIGHTER", 0.1, 0.2),
    makeStroke("PEN", 0.25, 0.5),
    makeStroke("PEN", 0.75, 1.2),
  ]);
  assert.equal(result.length, 2);
  assert.deepEqual(result.map((stroke) => stroke.points[0]), [
    { x: 198.5, y: 561.5 },
    { x: 595.5, y: 1123 },
  ]);
  assert.deepEqual(result.map((stroke) => stroke.lineWidth), [3, 3]);
});

test("empty ink abstains without loading model or inventing a formula", async () => {
  await assert.rejects(recognizeHandwrittenMath([]), /OCR_NOT_RECOGNIZED/);
});
